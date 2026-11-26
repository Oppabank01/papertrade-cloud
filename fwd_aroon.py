#!/usr/bin/env python3
"""Forward paper test of the Aroon trend agent (ezmal2003-commits/btc-aroon-paper, GitHub 19 Oct 2026: "BTC Aroon Trend
Agents, paper trading dashboard", Aroon 14 with UP when the oscillator is above +50 and DOWN below -50) on BTC, ETH, SOL,
BNB, XRP (opened 27 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too).
Fake money only.

On closed 4h Binance bars, long only, the repo's Aroon: over the last N bars, Aroon Up = 100 x (N - bars since the highest
high) / N and Aroon Down the same with the lowest low (first extreme wins a tie, as np.argmax); oscillator = Up - Down.
BUY when flat and the oscillator is above HI, SELL when holding and it is below LO; both fill at the next real open.
The repo's cooldown of 2 bars is left out (long-only on/off state needs none). One position per coin, one fifth of the
start per coin, 0.35% per side.
  state_fwd_aroon.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_aroon_twin.json  control: random entry bars (TWIN_P per free bar), same SELL exit
  python3 fwd_aroon.py"""
import random
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: the five majors the other 4h accounts use
N, HI, LO = 14, 50, -50        # the repo's defaults
TWIN_P = 1 / 25                # my choice: the backtest twin's rate (2 x 400 BTC trades / 20,314 4h bars)
# also mine: 4h bars (repo default is 1h), fills at the next open, long only, size one fifth of the start per coin
LABEL = ("Aroon 14 4 ชม. (ezmal2003-commits/btc-aroon-paper) BTC ETH SOL BNB XRP: ซื้อเมื่อ Aroon oscillator เกิน +50 "
         "ขายเมื่อต่ำกว่า -50 (backtest Binance 4 ชม. 2017 ถึง 26 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 400 ไม้ +0.15% ต่อไม้ "
         "มัธยฐาน -1.70% ชนะ 33% ETH 406 ไม้ +0.57% SOL 286 ไม้ +0.29% BNB 393 ไม้ +1.51% XRP 364 ไม้ +0.71% ตัวแฝดเข้าสุ่ม "
         "+0.00 ถึง +1.40% ใกล้หรือดีกว่า ตั้งแต่ 2025 -0.25 ถึง -1.42% ต่อไม้ permutation 200 รอบบน 6,000 แท่งล่าสุด "
         "กริด 3 แบบ p 0.373/0.453/0.950/0.542/0.129)")
ACCOUNTS = {"state_fwd_aroon.json": ("rule", LABEL),
            "state_fwd_aroon_twin.json": ("random", "Aroon 14 4 ชม. ตัวควบคุม: เข้าแท่งสุ่ม ออกเมื่อ oscillator ต่ำกว่า -50 แบบเดียวกัน")}


def signals(b):
    """per bar 'buy', 'sell' or None: Aroon(N) oscillator crossing HI while flat or LO while holding"""
    out, hold = [], False
    for i in range(len(b)):
        s = None
        if i >= N - 1:
            w = b[i - N + 1:i + 1]
            ih = max(range(N), key=lambda j: (w[j]["h"], -j))
            il = min(range(N), key=lambda j: (w[j]["l"], j))
            osc = 100 * (ih + 1) / N - 100 * (il + 1) / N   # = 100 x (N - bars since) / N for each side
            if not hold and osc > HI:
                s, hold = "buy", True
            elif hold and osc < LO:
                s, hold = "sell", False
        out.append(s)
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    sg = signals(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p:
            if x["t"] >= p["entry_t"] and sg[i] == "sell":
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "Aroon oscillator ต่ำกว่า -50")
            continue
        ok = sg[i] == "buy" if mode == "rule" else rng.random() < TWIN_P
        if not ok:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "Aroon oscillator เกิน +50" if mode == "rule" else "สุ่มแท่ง"
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / en, entry=en, last=en, usd=usd, entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=en, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_aroon fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
