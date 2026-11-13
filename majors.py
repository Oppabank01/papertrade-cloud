#!/usr/bin/env python3
"""Daily-bar paper accounts on big coins (14 Nov 2026), fake money only: the candidates that survived the backtest zoo
(Projects/PaperTrade/reports/backtest-zoo-2026-11-14.md) plus its buy-and-hold control. Binance TH USDT pairs,
closed daily bars (close 07:00 Thai time), 0.1% fee + 0.05% slippage per side, fills at the latest price.

  vt6     every week: coin above SMA50 gets (1/6) x min(1, 30% / annualised 30-day vol), else 0; rest in USDT
  trend6  six fixed sleeves, each holds its coin while the close is above SMA50, else USDT
  btc50   BTC while the close is above SMA50, else USDT
  hold6   1/6 in each coin, rebalanced weekly (control)

  python3 majors.py init 10000   # THB per account, creates missing accounts only
  python3 majors.py run          # once a day (cloud.sh daily block)
  python3 majors.py report
"""
import json
import math
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://api.binance.th/api/v1"
COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]
COST = 0.0015
TH = timezone(timedelta(hours=7))
HERE = Path(__file__).parent
ACCOUNTS = {"vt6": "เหรียญใหญ่ ตามเทรนด์คุมความผันผวน 6 เหรียญ", "trend6": "เหรียญใหญ่ ตามเทรนด์ SMA50 6 ช่อง",
            "btc50": "BTC เหนือ SMA50", "hold6": "เหรียญใหญ่ 6 ตัว ถือเฉยๆ (ตัวควบคุม)"}


def get(path):
    with urllib.request.urlopen(API + path, timeout=20) as r:
        return json.load(r)


def closes(coin):
    now = time.time() * 1000
    return [float(x[4]) for x in get(f"/klines?symbol={coin}USDT&interval=1d&limit=60") if x[6] < now]


def sma50(c):
    return sum(c[-50:]) / 50


def vol30(c):
    r = [math.log(c[i] / c[i - 1]) for i in range(len(c) - 30, len(c))]
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1) * 365)


def targets(name, c):
    """Target weight per coin for the weekly accounts."""
    if name == "hold6":
        return {k: 1 / 6 for k in COINS}
    return {k: (1 / 6) * min(1, 0.30 / vol30(c[k])) if c[k][-1] > sma50(c[k]) else 0 for k in COINS}


def path(name):
    return HERE / f"state_major_{name}.json"


def equity(s, px):
    """Cash + coins (+ idle sleeve cash for the sleeve accounts)."""
    return s["cash"] + sum(s.get("sleeve", {}).values()) + sum(q * px[k] for k, q in s["qty"].items())


def note(s, coin, usd, px, why):
    s["log"].append(dict(t=datetime.now(TH).isoformat(timespec="seconds"), coin=coin, usd=round(usd, 2), px=px, why=why))


def trade(s, coin, usd, px, why):
    """Buy (usd > 0) or sell (usd < 0) `usd` worth of coin at px, cost on the traded amount."""
    if abs(usd) < 1:
        return
    s["qty"][coin] = s["qty"].get(coin, 0) + usd * (1 - COST) / px if usd > 0 else s["qty"][coin] + usd / px
    s["cash"] += -usd if usd > 0 else -usd * (1 - COST)
    note(s, coin, usd, px, why)


def step(name, s, c, px, today):
    if name in ("trend6", "btc50"):                          # sleeves: all in or all out of each coin on the signal
        for k in (["BTC"] if name == "btc50" else COINS):
            above, held = c[k][-1] > sma50(c[k]), s["qty"].get(k, 0) > 0
            if above and not held:
                note(s, k, s["sleeve"][k], px[k], "เหนือ SMA50")
                s["qty"][k], s["sleeve"][k] = s["sleeve"][k] * (1 - COST) / px[k], 0
            elif held and not above:
                s["sleeve"][k], s["qty"][k] = s["qty"][k] * px[k] * (1 - COST), 0
                note(s, k, -s["sleeve"][k], px[k], "หลุด SMA50")
        return
    week = datetime.fromisoformat(today).isocalendar()[:2]
    if s.get("week") == list(week):
        return
    s["week"] = list(week)
    eq, tw = equity(s, px), targets(name, c)
    for k in sorted(COINS, key=lambda k: tw[k] * eq - s["qty"].get(k, 0) * px[k]):   # sells first, then buys
        trade(s, k, tw[k] * eq - s["qty"].get(k, 0) * px[k], px[k], f"ปรับน้ำหนักเป็น {tw[k]:.1%}")


def cmd_init(thb):
    usd = float(thb) / float(get("/ticker/price?symbol=USDTTHB")["price"])
    for name, label in ACCOUNTS.items():
        if not path(name).exists():
            s = dict(label=label, start_usd=usd, start_thb=float(thb), cash=usd, qty={}, log=[], history=[])
            if name in ("trend6", "btc50"):     # the money lives in per-coin sleeves instead of shared cash
                coins = ["BTC"] if name == "btc50" else COINS
                s.update(cash=0, sleeve={k: usd / len(coins) for k in coins})
            path(name).write_text(json.dumps(s, ensure_ascii=False, indent=1))
            print(f"init {name}")


def cmd_run():
    c = {k: closes(k) for k in COINS}
    px = {k: float(get(f"/ticker/price?symbol={k}USDT")["price"]) for k in COINS}
    today = datetime.now(TH).date().isoformat()
    for name in ACCOUNTS:
        if not path(name).exists():
            continue
        s = json.loads(path(name).read_text())
        if s.get("day") == today:
            continue
        step(name, s, c, px, today)
        s["day"] = today
        s["history"].append(dict(day=today, usd=round(equity(s, px), 2)))
        path(name).write_text(json.dumps(s, ensure_ascii=False, indent=1))


def cmd_report():
    px = {k: float(get(f"/ticker/price?symbol={k}USDT")["price"]) for k in COINS}
    for name in ACCOUNTS:
        if path(name).exists():
            s = json.loads(path(name).read_text())
            print(f"{equity(s, px) / s['start_usd'] - 1:+7.1%}  {name:7s} {s['label']}")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmds = {"init": lambda: cmd_init(a[1]), "run": cmd_run, "report": cmd_report}
    if not a or a[0] not in cmds:
        sys.exit(__doc__)
    cmds[a[0]]()
