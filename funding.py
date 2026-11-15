#!/usr/bin/env python3
"""Funding-carry paper accounts (14 Nov 2026), fake money only. Each coin sleeve holds spot and shorts the same
amount of Hyperliquid perp, so price moves cancel and the sleeve earns the hourly funding longs pay shorts.
Backtest Jul 2023 to Nov 2026 (scratch, Hyperliquid funding history): always-on ~15%/yr before costs, falling to
~3-5% in 2026; the 7-day filter ~11-12%/yr after costs with max drawdown under 5%. Not modelled: basis moves,
liquidation of the short leg, exchange risk. 0.3% of the sleeve per switch (both legs in or out).

  fund7   BTC ETH SOL sleeves, carry on while the trailing 7-day mean funding is above zero
  fundon  same sleeves, carry always on (control)
  fundtop3_500  (15 Nov) 500 THB, the 3 coins with the highest 7-day mean funding among the 15 biggest perps, re-picked daily
  fundhi_500    (15 Nov) 500 THB, every top-15 perp whose 7-day mean funding is above 10%/yr, up to 5, equal weight

  python3 funding.py init 10000   # THB per account, creates missing accounts only
  python3 funding.py run          # every cloud round; steps each account once a day
  python3 funding.py report
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HL = "https://api.hyperliquid.xyz/info"
COINS = ["BTC", "ETH", "SOL"]
COST = 0.003
WEEK_MS = 7 * 86400 * 1000
TH = timezone(timedelta(hours=7))
HERE = Path(__file__).parent
ACCOUNTS = {"fund7": "เก็บค่า funding BTC ETH SOL เปิดเมื่อค่าเฉลี่ย 7 วันเป็นบวก",
            "fundon": "เก็บค่า funding BTC ETH SOL เปิดตลอด (ตัวควบคุม)"}
PICK = {"fundtop3_500": ("เก็บ funding 3 เหรียญที่ค่าเฉลี่ย 7 วันสูงสุดใน 15 perp ใหญ่ เลือกใหม่ทุกวัน", 3, 0.0),
        "fundhi_500": ("เก็บ funding ทุกเหรียญใน 15 perp ใหญ่ที่ค่าเฉลี่ย 7 วันเกิน 10%/ปี (สูงสุด 5)", 5, 0.10 / 8760)}


def path(name):
    return HERE / f"state_fund_{name}.json"


def rates(coin, since_ms):
    """[(time_ms, hourly funding rate)] from since_ms, oldest first."""
    out, t = [], since_ms
    while True:
        body = json.dumps({"type": "fundingHistory", "coin": coin, "startTime": t}).encode()
        req = urllib.request.Request(HL, body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.load(r)
        out += [(x["time"], float(x["fundingRate"])) for x in d]
        if len(d) < 500:
            return out
        t = d[-1]["time"] + 1
        time.sleep(1)


def want_on(name, hist, now_ms):
    if name == "fundon":
        return True
    week = [r for t, r in hist if t > now_ms - WEEK_MS]
    return bool(week) and sum(week) / len(week) > 0


def step(name, s, hist, now_ms, today):
    """Accrue funding since the last step under the old on/off state, then switch where the filter says so."""
    for k in COINS:
        if s["on"][k]:
            for t, r in hist[k]:
                if s["last_t"] < t <= now_ms:
                    s["sleeve"][k] *= 1 + r
        on = want_on(name, hist[k], now_ms)
        if on != s["on"][k]:
            s["sleeve"][k] *= 1 - COST
            s["on"][k] = on
            s["log"].append(dict(t=datetime.now(TH).isoformat(timespec="seconds"), coin=k,
                                 why="เปิด carry" if on else "ปิด carry", usd=round(s["sleeve"][k], 2)))
    s["last_t"], s["day"] = now_ms, today
    s["history"].append(dict(day=today, usd=round(sum(s["sleeve"].values()), 2)))


def universe():
    """The 15 Hyperliquid perps with the largest open interest in USD."""
    req = urllib.request.Request(HL, json.dumps({"type": "metaAndAssetCtxs"}).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        meta, ctxs = json.load(r)
    return [k for _, k in sorted(((float(x["openInterest"]) * float(x["markPx"]), u["name"]) for u, x in zip(meta["universe"], ctxs)), reverse=True)[:15]]


def pick_target(name, hist, now_ms, pool):
    n, floor = PICK[name][1:]
    mean = {}
    for k in pool:
        week = [r for t, r in hist.get(k, []) if t > now_ms - WEEK_MS]
        if week:
            mean[k] = sum(week) / len(week)
    return [k for m, k in sorted(((m, k) for k, m in mean.items() if m > floor), reverse=True)[:n]]


def pick_step(name, s, hist, now_ms, today, pool):
    """Accrue funding on held sleeves, drop coins that left the pick, buy the new ones with an equal share each."""
    for k in s["sleeve"]:
        for t, r in hist.get(k, []):
            if s["last_t"] < t <= now_ms:
                s["sleeve"][k] *= 1 + r
    target, n = pick_target(name, hist, now_ms, pool), PICK[name][1]
    stamp = datetime.now(TH).isoformat(timespec="seconds")
    for k in [k for k in s["sleeve"] if k not in target]:
        s["cash"] += s["sleeve"].pop(k) * (1 - COST)
        s["log"].append(dict(t=stamp, coin=k, why="ปิด carry", usd=round(s["cash"], 2)))
    eq = s["cash"] + sum(s["sleeve"].values())
    for k in [k for k in target if k not in s["sleeve"]]:
        spend = min(s["cash"], eq / n)
        s["cash"] -= spend
        s["sleeve"][k] = spend * (1 - COST)
        s["log"].append(dict(t=stamp, coin=k, why="เปิด carry", usd=round(spend, 2)))
    s["last_t"], s["day"] = now_ms, today
    s["history"].append(dict(day=today, usd=round(s["cash"] + sum(s["sleeve"].values()), 2)))


def cmd_init(thb):
    with urllib.request.urlopen("https://api.binance.th/api/v1/ticker/price?symbol=USDTTHB", timeout=20) as r:
        usd = float(thb) / float(json.load(r)["price"])
    now_ms = int(time.time() * 1000)
    for name, label in ACCOUNTS.items():
        if not path(name).exists():
            s = dict(label=label, start_usd=usd, start_thb=float(thb), sleeve={k: usd / len(COINS) for k in COINS},
                     on={k: False for k in COINS}, last_t=now_ms, log=[], history=[])
            path(name).write_text(json.dumps(s, ensure_ascii=False, indent=1))
            print(f"init {name}")
    for name, (label, _, _) in PICK.items():
        if not path(name).exists():
            s = dict(label=label, start_usd=usd * 500 / float(thb), start_thb=500.0, cash=usd * 500 / float(thb), sleeve={},
                     last_t=now_ms, log=[], history=[])
            path(name).write_text(json.dumps(s, ensure_ascii=False, indent=1))
            print(f"init {name}")


def cmd_run():
    today = datetime.now(TH).date().isoformat()
    todo = [n for n in (*ACCOUNTS, *PICK) if path(n).exists() and json.loads(path(n).read_text()).get("day") != today]
    if not todo:
        return
    now_ms = int(time.time() * 1000)
    pool = universe() if any(n in PICK for n in todo) else []
    held = {k for n in todo if n in PICK for k in json.loads(path(n).read_text())["sleeve"]}
    hist = {k: rates(k, now_ms - WEEK_MS - 86400 * 1000) for k in {*COINS, *pool, *held}}
    for name in todo:
        s = json.loads(path(name).read_text())
        if name in PICK:
            pick_step(name, s, hist, now_ms, today, pool)
        else:
            step(name, s, hist, now_ms, today)
        path(name).write_text(json.dumps(s, ensure_ascii=False, indent=1))


def cmd_report():
    for name in ACCOUNTS:
        if path(name).exists():
            s = json.loads(path(name).read_text())
            on = " ".join(k for k in COINS if s["on"][k]) or "ไม่มี"
            print(f"{sum(s['sleeve'].values()) / s['start_usd'] - 1:+7.2%}  {name:7s} {s['label']}  (เปิดอยู่: {on})")
    for name in PICK:
        if path(name).exists():
            s = json.loads(path(name).read_text())
            print(f"{(s['cash'] + sum(s['sleeve'].values())) / s['start_usd'] - 1:+7.2%}  {name} {s['label']}  (ถือ: {' '.join(s['sleeve']) or 'ไม่มี'})")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmds = {"init": lambda: cmd_init(a[1]), "run": cmd_run, "report": cmd_report}
    if not a or a[0] not in cmds:
        sys.exit(__doc__)
    cmds[a[0]]()
