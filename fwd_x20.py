#!/usr/bin/env python3
"""Lottery ladder: the honest version of the "$100 to $2,000 in a day" posts, opened 23 Nov 2026. Fake money only.

Each attempt stakes 1/50 of the start as margin on a 50x BTC perp bet (Binance 1 h bars): +2% from entry doubles the
margin, -2% wipes it (liquidation, checked first when a bar touches both). After a win the whole margin rolls into a new
bet at the next bar's open. The attempt ends at x20 or at zero, and counts as one trade. Fees: 0.045% taker per side on
50x notional plus 0.2% for funding, so a win pays x1.953 and five wins in a row reach x28.
Why: our 4,885 paper memecoin sells average -9.6% after costs and only 17 reached x2, so a bootstrap of 20,000 runs never
reached x10. A fair coin ladder reaches x20 about 1 time in 25 to 30, which is how most of those posts happen: many try,
the few who hit post. This account measures how often it really hits and what it costs per hit.
Backtest Jan 2023 to Nov 2026 (Binance 1 h): 0.63 attempts a day, bets won 51% (trend) / 52% (coin flip), x20 hit 35 of 902
attempts (3.9%) and 34 of 879, about +10% per attempt's stake for both: a near-fair lottery in a rising market, no edge from
the side rule. Ending with nothing on 96% of attempts is the normal result, not a failure of the code.
  state_fwd_x20.json        side = direction of the last 24 h (BTC open now vs 24 h ago)
  state_fwd_x20_twin.json   control: side by coin flip
  python3 fwd_x20.py"""
import random
import byttrade as B
from byttrade import iso, load, save

LEV, MOVE, TARGET, UNITS = 50, 0.02, 20, 50
FEE = 0.00045 * 2 * LEV + 0.002
ACCOUNTS = {"state_fwd_x20.json": ("trend", "ลอตเตอรี่ x20: BTC 50x ทบทั้งหมดทุกไม้จนถึง x20 หรือหมด ฝั่งตาม 24 ชม. ล่าสุด (รอบละ 1/50 ของทุน แบบโพสต์โม้)"),
            "state_fwd_x20_twin.json": ("random", "ลอตเตอรี่ x20 ตัวควบคุม: ฝั่งโยนเหรียญ")}


def fetch():
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=1h")
    try:
        return B.fetch("BTCUSDT")
    finally:
        B.URL = old


def step(s, bars, mode, rng):
    if s.get("seen") is None:
        s["seen"] = [x for x in bars if x["closed"]][-1]["t"]
        return
    unit = s["start_usd"] / UNITS
    for i in range(24, len(bars)):
        x = bars[i]
        if not x["closed"] or x["t"] <= s["seen"]:
            continue
        s["seen"] = x["t"]
        lad = s.get("lad")
        if lad is None:
            if s["cash"] < unit * 0.99:
                continue                                  # lottery budget spent
            s["cash"] -= unit
            lad = s["lad"] = dict(v=1.0, wins=0, entry=None, side=0, t=iso(x["t"]))
            s["log"].append(dict(kind="buy", t=iso(x["t"]), coin="BTC", side="lottery", px=x["o"], usd=unit, why="เริ่มรอบใหม่"))
        if lad["entry"] is None:
            lad["side"] = (1 if x["o"] > bars[i - 24]["o"] else -1) if mode == "trend" else rng.choice((1, -1))
            lad["entry"] = x["o"]
        up, dn = x["h"] / lad["entry"] - 1, x["l"] / lad["entry"] - 1
        lose = dn <= -MOVE if lad["side"] > 0 else up >= MOVE
        win = up >= MOVE if lad["side"] > 0 else dn <= -MOVE
        if lose:
            s["log"].append(dict(kind="sell", t=iso(x["t"]), coin="BTC", side="lottery", px=x["c"], usd=unit, ret=-1.0, pnl=-unit,
                                 cost_side=FEE / 2, why=f"ล้างพอร์ตหลังชนะ {lad['wins']} ไม้"))
            s["lad"] = None
        elif win:
            lad["v"] *= 2 - FEE
            lad["wins"] += 1
            lad["entry"] = None
            if lad["v"] >= TARGET:
                s["cash"] += unit * lad["v"]
                s["log"].append(dict(kind="sell", t=iso(x["t"]), coin="BTC", side="lottery", px=x["c"], usd=unit, ret=round(lad["v"] - 1, 6),
                                     pnl=unit * (lad["v"] - 1), cost_side=FEE / 2, why=f"ถึง x{lad['v']:.1f} ใน {lad['wins']} ไม้"))
                s["lad"] = None


def main():
    rng = random.Random()
    try:
        bars = fetch()
    except Exception as e:
        print("fwd_x20 fetch failed", type(e).__name__)
        return
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        step(s, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
