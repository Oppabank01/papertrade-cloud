#!/usr/bin/env python3
"""Forward paper test of Wilder's Parabolic SAR (dev.to howiprompt series, 2026: "how our AI agents evolved ParabolicSAR on
SOLUSDT/BNBUSDT", posts give no fixed rule so this is the textbook SAR) on BTC, ETH, SOL, BNB, XRP (opened 27 Nov 2026 by
the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too). Fake money only.

On closed 4h Binance bars, long only: SAR seeded on the first two bars (trend up if the second close is above the first),
SAR += AF x (EP - SAR), clamped by the two previous lows (up) or highs (down); trend flips when the bar's low breaks the SAR
(up) or its high breaks it (down), the SAR jumps to the extreme point and AF resets; AF grows by STEP up to AF_MAX on each
new extreme. BUY = SAR flips below price, SELL = SAR flips above price; both fill at the next real open. The SAR runs over
the bars this script is given. One position per coin, one fifth of the start per coin, 0.35% per side.
  state_fwd_psar.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_psar_twin.json  control: random entry bars (TWIN_P per free bar), same SELL exit
  python3 fwd_psar.py"""
import random
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: the five majors the other 4h accounts use
AF0, STEP, AF_MAX = 0.02, 0.02, 0.2   # my choice: Wilder's textbook values (the posts give no numbers)
TWIN_P = 1 / 13                # my choice: the backtest twin's rate (2 x 779 BTC trades / 20,314 4h bars)
# also mine: 4h bars, fills at the next open, long only, size one fifth of the start per coin
LABEL = ("Parabolic SAR 4 ชม. (dev.to howiprompt) BTC ETH SOL BNB XRP: SAR ของ Wilder 0.02/0.02/0.2 ซื้อเมื่อ SAR พลิกลง"
         "ใต้ราคา ขายเมื่อพลิกขึ้น (backtest Binance 4 ชม. 2017 ถึง 26 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 779 ไม้ -0.22% ต่อไม้ "
         "มัธยฐาน -1.47% ชนะ 33% ETH 783 ไม้ -0.41% SOL 563 ไม้ +0.15% BNB 759 ไม้ +0.42% XRP 660 ไม้ +0.01% ตัวแฝดเข้าสุ่ม "
         "-0.43 ถึง +0.63% ใกล้กัน ตั้งแต่ 2025 -0.37 ถึง -1.00% ต่อไม้ permutation 200 รอบบน 6,000 แท่งล่าสุด กริด 3 แบบ "
         "p 0.637/0.308/0.403/0.433/0.075)")
ACCOUNTS = {"state_fwd_psar.json": ("rule", LABEL),
            "state_fwd_psar_twin.json": ("random", "Parabolic SAR 4 ชม. ตัวควบคุม: เข้าแท่งสุ่ม ออกเมื่อ SAR พลิกขึ้นแบบเดียวกัน")}


def signals(b):
    """per bar 'buy', 'sell' or None from Parabolic SAR judged on the closed bar's high and low"""
    out = [None, None]
    if len(b) < 3:
        return [None] * len(b)
    up = b[1]["c"] > b[0]["c"]
    sar = b[0]["l"] if up else b[0]["h"]
    ep = b[1]["h"] if up else b[1]["l"]
    af = AF0
    for i in range(2, len(b)):
        h, l = b[i]["h"], b[i]["l"]
        sar = sar + af * (ep - sar)
        sig = None
        if up:
            sar = min(sar, b[i - 1]["l"], b[i - 2]["l"])
            if l < sar:
                up, sar, ep, af, sig = False, ep, l, AF0, "sell"
            elif h > ep:
                ep, af = h, min(af + STEP, AF_MAX)
        else:
            sar = max(sar, b[i - 1]["h"], b[i - 2]["h"])
            if h > sar:
                up, sar, ep, af, sig = True, ep, h, AF0, "buy"
            elif l < ep:
                ep, af = l, min(af + STEP, AF_MAX)
        out.append(sig)
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
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "Parabolic SAR พลิกขึ้นเหนือราคา")
            continue
        ok = sg[i] == "buy" if mode == "rule" else rng.random() < TWIN_P
        if not ok:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "Parabolic SAR พลิกลงใต้ราคา" if mode == "rule" else "สุ่มแท่ง"
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
            print("fwd_psar fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
