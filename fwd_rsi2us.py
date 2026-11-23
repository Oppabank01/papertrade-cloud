#!/usr/bin/env python3
"""Forward paper test of Connors' RSI(2) dip buying on US index ETFs (SPY, QQQ, IWM), opened 23 Nov 2026. Fake money only.

Rule on Yahoo daily bars: RSI(2) of the close below 5 -> buy at the next open; sell at the next open after a close above the
5-day average of closes, or after 10 bars. A third of the start per ETF, each third compounds on its own, 0.01% per side.
Backtest 2005-2026: SPY 574 trades +0.32%/trade (random entry days with the same average hold +0.12%, p 0.003), since 2020
+0.43%; QQQ 563 +0.44% (p 0.007); IWM 581 +0.23% (p 0.14, weakest). About 25 trades a year per ETF, so 50 trades take months.
fwd_rsi2.py runs the same idea on coins. Threshold 5 chosen by me from 2 tried (with and without a 200-day trend filter).
  state_fwd_rsi2us.json        the rule
  state_fwd_rsi2us_twin.json   control: random entry days (1 in 9 free days), same exit rule
  python3 fwd_rsi2us.py"""
import random
import fwd_overnight as O
from byttrade import iso, load, save

COST, TH, MAXB, TWIN_P = 0.0001, 5, 10, 1 / 9
SYMS = O.SYMS
ACCOUNTS = {"state_fwd_rsi2us.json": ("rule", "หุ้นสหรัฐ RSI(2) ต่ำกว่า 5 ซื้อ SPY QQQ IWM ตอนเปิดวันถัดไป ขายเมื่อปิดเหนือเส้นเฉลี่ย 5 วัน (backtest ชนะวันสุ่ม p 0.003)"),
            "state_fwd_rsi2us_twin.json": ("random", "หุ้นสหรัฐ RSI(2) ตัวควบคุม: ซื้อวันสุ่ม ออกด้วยกฎเดียวกัน")}


def rsi2(b, i):
    g = sum(max(b[j]["c"] - b[j - 1]["c"], 0) for j in (i - 1, i))
    l = sum(max(b[j - 1]["c"] - b[j]["c"], 0) for j in (i - 1, i))
    return 100.0 if l == 0 else 100 - 100 / (1 + g / l)


def step(s, sym, bars, mode, rng):
    if not isinstance(s.get("seen"), dict):
        s["seen"] = {}
    seen, sl = s["seen"], s.setdefault("sleeve", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        sl[sym] = s["start_usd"] / len(SYMS)
        return
    for i in range(5, len(bars) - 1):                 # act on closed bar i at the open of bar i+1
        x, nxt = bars[i], bars[i + 1]
        if not x["closed"] or x["t"] <= seen[sym]:
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p:
            p["n"] += 1
            if x["c"] > sum(y["c"] for y in bars[i - 4:i + 1]) / 5 or p["n"] >= MAXB:
                s["pos"].pop(sym)
                ret = nxt["o"] / p["entry"] - 1
                pnl = p["usd"] * ret - p["usd"] * COST - p["usd"] * (1 + ret) * COST
                sl[sym] += pnl
                s["cash"] += p["usd"] + pnl
                s["log"].append(dict(kind="sell", t=iso(nxt["t"]), coin=sym, side="long", px=nxt["o"], usd=p["usd"], ret=round(ret, 6),
                                     pnl=pnl, cost_side=COST, why="ปิดเหนือเส้นเฉลี่ย 5 วัน" if p["n"] < MAXB else "ครบ 10 วัน"))
            continue
        go = rsi2(bars, i) < TH if mode == "rule" else rng.random() < TWIN_P
        if not go:
            continue
        usd = sl[sym]
        s["cash"] -= usd
        why = f"RSI(2) {rsi2(bars, i):.1f}" if mode == "rule" else "วันสุ่ม"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / nxt["o"], entry=nxt["o"], last=nxt["o"], usd=usd, n=0, t=iso(nxt["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nxt["t"]), coin=sym, side="long", px=nxt["o"], usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, bars = random.Random(), {}
    for sym in SYMS:
        try:
            bars[sym] = O.fetch(sym)
        except Exception as e:
            print("fwd_rsi2us fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        for sym, b in bars.items():
            step(s, sym, b, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
