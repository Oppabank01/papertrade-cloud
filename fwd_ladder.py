#!/usr/bin/env python3
"""Forward paper test of the closest mechanical version of meller_ai's paid-course dip indicator (X, 10 Nov 2026:
"Orange Buy under every dip, Red Close at every top, averaging lines at -4%, -8%, -12%") on AVAX, BTC, ETH, SOL
(opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too).
Fake money only.

On closed 4h Binance bars: a close under the lower Bollinger band (20, 2) buys one unit at the next open; one more
unit is added each time a bar's low touches -4%, -8%, -12% from that first fill (filled at the level, or at the open
if the bar gaps below it); everything is sold at the next open after a close over the upper band. No stop (the post
shows none). One ladder per coin, a quarter of the start per coin split in 4 equal units, 0.35% per side.
  state_fwd_ladder.json       AVAX, BTC, ETH, SOL
  state_fwd_ladder_twin.json  control: random first fill (TWIN_P per free bar), same ladder and exit
  python3 fwd_ladder.py"""
import math
import random
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["AVAXUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT"]   # AVAX is the coin in the post; the other three are my choice
BB_N, BB_K = 20, 2.0           # my choice: the post names no indicator, so the usual Bollinger band stands in for "dip"/"top"
LADDER = (0.04, 0.08, 0.12)    # the post's averaging lines
UNITS = 1 + len(LADDER)        # my choice: equal units, first fill plus one per line
TWIN_P = 1 / 40                # my choice: close to the rule's rate (about 1 ladder per 60-90 bars) but busier
LABEL = ("ช้อนเติมไม้ -4/-8/-12% (ใกล้ที่สุดกับอินดิเคเตอร์คอร์สเสียเงินในโพสต์ meller_ai) 4 ชม. AVAX BTC ETH SOL: ปิดใต้ BB ล่าง (20,2) "
         "ซื้อ 1 ส่วน เติมส่วนละเท่ากันที่ -4/-8/-12% จากไม้แรก ขายหมดเมื่อปิดเหนือ BB บน ไม่มี stop (backtest Binance 4 ชม. ถึง 2026 "
         "หลังหัก 0.35%/ข้าง AVAX 142 รอบ +2.20% BTC 229 รอบ +1.67% ETH 230 รอบ +1.95% SOL 154 รอบ +3.62% ต่อรอบ ชนะ 72-77% "
         "แต่ตัวแฝดเข้าสุ่มได้ +2.17/+1.27/+1.57/+3.25% และ permutation 200 รอบ p 0.985/0.995/1.000/0.930 กำไรมาจากการถือรอขึ้นโดยไม่มี stop)")
ACCOUNTS = {"state_fwd_ladder.json": ("rule", LABEL),
            "state_fwd_ladder_twin.json": ("random", "ช้อนเติมไม้ ตัวควบคุม: ไม้แรกเข้าแท่งสุ่ม เติมและออกแบบเดียวกัน")}


def band(b, i):
    w = [x["c"] for x in b[i - BB_N + 1:i + 1]]
    mu = sum(w) / BB_N
    sd = math.sqrt(sum((v - mu) ** 2 for v in w) / BB_N)
    return mu - BB_K * sd, mu + BB_K * sd


def buy(s, sym, px, t, why):
    usd = s["start_usd"] / len(SYMS) / UNITS
    if s["cash"] < usd * (1 + COST):
        return False
    s["cash"] -= usd + usd * COST
    p = s["pos"].get(sym)
    if p is None:
        p = s["pos"][sym] = dict(side="long", d=1, qty=0.0, entry=px, last=px, usd=0.0, fills=[], entry_t=t, t=iso(t), why=why)
    p["qty"] += usd / px
    p["usd"] += usd
    p["fills"].append(px)
    s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side="long", px=px, usd=usd, why=why))
    return True


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = p["qty"] * px / p["usd"] - 1
    s["cash"] += p["qty"] * px - p["qty"] * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         fills=len(p["fills"]), pnl=p["usd"] * ret - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < BB_N - 1:
            continue
        seen[sym] = x["t"]
        if sym in s["pos"]:
            p = s["pos"][sym]
            e0 = p["fills"][0]
            for d in LADDER[len(p["fills"]) - 1:]:
                if x["l"] <= e0 * (1 - d):
                    buy(s, sym, min(x["o"], e0 * (1 - d)), x["t"], f"เติมไม้ที่ -{d:.0%}")
            if x["c"] > band(bars, i)[1]:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "ปิดเหนือ BB บน")
            continue
        if mode == "rule":
            go, why = x["c"] < band(bars, i)[0], "ปิดใต้ BB ล่าง"
        else:
            go, why = rng.random() < TWIN_P, "สุ่มแท่ง"
        if go:
            buy(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], why)
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_ladder fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
