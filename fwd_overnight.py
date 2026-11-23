#!/usr/bin/env python3
"""Forward paper test of the overnight drift in US index ETFs (SPY, QQQ, IWM), opened 23 Nov 2026. Fake money only.

Rule: buy at the close, sell at the next open, every trading day (out of the market during the session). A third of the start
per ETF, each third compounds on its own. 0.01% per side (zero commission, auction spread about 0.5 bp; my guess).
Backtest on Yahoo daily bars, before costs: SPY since 2010 overnight +320% vs intraday +98%, since 2024 overnight +49% vs
intraday +1%; QQQ since 2024 +68% vs -10%; IWM since 2020 +198% vs -44%. At 2 bp a round trip the overnight leg still beat
the intraday leg every year since 2019 except 2023 (and 2022 for IWM it lost less), but it trails buy-and-hold for SPY/QQQ.
Known effect (Lou, Polk, Skouras 2019, "A tug of war"); who pays: buyers who want in at the open and sellers at the close.
  state_fwd_overnight.json        the rule (close -> next open)
  state_fwd_overnight_twin.json   control: the other half of the day (open -> close), same ETFs and cost
Trades are booked once both prices are final, so a trade shows up the morning after (no decision depends on them: always in).
  python3 fwd_overnight.py"""
import json, time, urllib.request
from byttrade import iso, load, save

COST = 0.0001
SYMS = ["SPY", "QQQ", "IWM"]
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}?range=3mo&interval=1d"
ACCOUNTS = {"state_fwd_overnight.json": ("night", "หุ้นสหรัฐช่วงตลาดปิด: ซื้อ SPY QQQ IWM ตอนปิดตลาด ขายตอนเปิดวันถัดไป ทุกวัน (backtest ช่วงกลางคืนชนะช่วงกลางวันเกือบทุกปี)"),
            "state_fwd_overnight_twin.json": ("day", "หุ้นสหรัฐตัวควบคุม: ถือเฉพาะช่วงตลาดเปิด (เปิดถึงปิด) ETF เดียวกัน")}


def fetch(sym):
    r = json.loads(urllib.request.urlopen(urllib.request.Request(URL.format(sym), headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())
    r = r["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    bars = [dict(t=t * 1000, o=o, h=h, l=l, c=c) for t, o, h, l, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"]) if o and c]
    now = time.time() * 1000
    for i, x in enumerate(bars):            # final once a later bar exists or 7 h after the open (close is 6.5 h after)
        x["closed"] = i + 1 < len(bars) or now > x["t"] + 7 * 3600 * 1000
    return bars


def step(s, sym, bars, mode):
    if not isinstance(s.get("seen"), dict):
        s["seen"] = {}
    seen, sl = s["seen"], s.setdefault("sleeve", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        sl[sym] = s["start_usd"] / len(SYMS)
        return
    for i in range(1, len(bars)):
        x, prev = bars[i], bars[i - 1]
        if not x["closed"] or x["t"] <= seen[sym]:
            continue
        seen[sym] = x["t"]
        a, b, ta = (prev["c"], x["o"], prev["t"]) if mode == "night" else (x["o"], x["c"], x["t"])
        usd = sl[sym]
        ret = b / a - 1
        pnl = usd * ret - usd * COST - usd * (1 + ret) * COST
        sl[sym] += pnl
        s["cash"] += pnl
        why = "ปิดตลาด -> เปิดวันถัดไป" if mode == "night" else "เปิด -> ปิด"
        s["log"].append(dict(kind="buy", t=iso(ta), coin=sym, side="long", px=a, usd=usd, why=why))
        s["log"].append(dict(kind="sell", t=iso(x["t"]), coin=sym, side="long", px=b, usd=usd, ret=round(ret, 6), pnl=pnl, cost_side=COST, why=why))


def main():
    bars = {}
    for sym in SYMS:
        try:
            bars[sym] = fetch(sym)
        except Exception as e:
            print("fwd_overnight fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        for sym, b in bars.items():
            step(s, sym, b, mode)
        save(f, s)


if __name__ == "__main__":
    main()
