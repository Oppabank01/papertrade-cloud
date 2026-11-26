#!/usr/bin/env python3
"""Forward paper test of the Vortex indicator as a strategy (VertQuant/Vortex_Botes_Siepman, GitHub 22 Oct 2026: MT4
indicator after Botes & Siepman 2010, EMA-smoothed VM+/VM- over ATR with a confirmed-threshold arrow) on BTC, ETH, SOL,
BNB, XRP (opened 27 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too).
Fake money only.

On closed 4h Binance bars, long only, the repo's formula: VM+ = |high - previous low|, VM- = |low - previous high|, each an
EMA(N) seeded with its first value; ATR = simple mean of the last N true ranges (MT4 iATR); diff = (EMA VM+ - EMA VM-) / ATR.
BUY when flat and diff crosses above +TH (the up arrow), SELL when holding and diff crosses below -TH (the down arrow); both
fill at the next real open. One position per coin, one fifth of the start per coin, 0.35% per side.
  state_fwd_vortex.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_vortex_twin.json  control: random entry bars (TWIN_P per free bar), same SELL exit
  python3 fwd_vortex.py"""
import random
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: the five majors the other 4h accounts use
N, TH = 14, 0.15               # the repo's defaults
TWIN_P = 1 / 19                # my choice: the backtest twin's rate (2 x 522 BTC trades / 20,314 4h bars)
# also mine: 4h bars (the indicator has no timeframe), arrows used as long entry/exit, fills at the next open, long only
LABEL = ("Vortex 14/0.15 4 ชม. (VertQuant/Vortex_Botes_Siepman) BTC ETH SOL BNB XRP: ซื้อเมื่อ VI+ ลบ VI- ขึ้นเกิน +0.15 "
         "ขายเมื่อลงต่ำกว่า -0.15 (backtest Binance 4 ชม. 2017 ถึง 26 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 522 ไม้ +0.20% ต่อไม้ "
         "มัธยฐาน -1.71% ชนะ 31% ETH 532 ไม้ +0.58% SOL 360 ไม้ +1.35% BNB 515 ไม้ +1.09% XRP 485 ไม้ +0.52% ตัวแฝดเข้าสุ่ม "
         "+0.10 ถึง +1.64% ใกล้กัน ตั้งแต่ 2025 -0.54 ถึง -0.91% ต่อไม้ ทบต้นแพ้ถือเฉยๆ ทุกเหรียญ permutation 200 รอบบน "
         "6,000 แท่งล่าสุด กริด 3 แบบ p 0.602/0.478/0.234/0.318/0.174)")
ACCOUNTS = {"state_fwd_vortex.json": ("rule", LABEL),
            "state_fwd_vortex_twin.json": ("random", "Vortex 14/0.15 4 ชม. ตัวควบคุม: เข้าแท่งสุ่ม ออกเมื่อ VI+ ลบ VI- ลงต่ำกว่า -0.15 แบบเดียวกัน")}


def signals(b):
    """per bar 'buy', 'sell' or None from the repo's confirmed-threshold arrows"""
    a = 2 / (N + 1)
    out, hold, eu, ed, trs, prev = [None], False, None, None, [], None
    for i in range(1, len(b)):
        ru, rd = abs(b[i]["h"] - b[i - 1]["l"]), abs(b[i]["l"] - b[i - 1]["h"])
        eu = ru if eu is None else a * ru + (1 - a) * eu
        ed = rd if ed is None else a * rd + (1 - a) * ed
        trs.append(max(b[i]["h"], b[i - 1]["c"]) - min(b[i]["l"], b[i - 1]["c"]))
        s = None
        if len(trs) >= N:
            atr = sum(trs[-N:]) / N
            d = (eu - ed) / atr if atr else 0.0
            if prev is not None:
                if not hold and d > TH and prev <= TH:
                    s, hold = "buy", True
                elif hold and d < -TH and prev >= -TH:
                    s, hold = "sell", False
            prev = d
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
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "VI+ ลบ VI- ลงต่ำกว่า -0.15")
            continue
        ok = sg[i] == "buy" if mode == "rule" else rng.random() < TWIN_P
        if not ok:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "VI+ ลบ VI- ขึ้นเกิน +0.15" if mode == "rule" else "สุ่มแท่ง"
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
            print("fwd_vortex fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
