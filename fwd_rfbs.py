#!/usr/bin/env python3
"""Forward paper test of littleboyck/futu-indicators "RF_BS" (GitHub, 21 Nov 2026: VuManChu's TradingView "Range Filter -
B&S Signals" ported to Futu/moomoo, shown on 4h charts) on BTC, ETH, SOL, BNB, XRP (opened 26 Nov 2026 by the scout;
backtest in LABEL, opened at any p because the user asked to try weak ideas too). Fake money only.

On closed 4h Binance bars, long only, as rf_bs.py with its code defaults (period 20, multiplier 3.5, source close):
d = |close - previous close|, smoothed by EMA(20) then EMA(39) (both seeded with their first value), range = 3.5 x that;
the filter ratchets: it rises to close - range when that is above it, falls to close + range when that is below it.
Direction is the sign of the filter's last change. BUY = direction up and close above the filter, the first such bar
after a SELL state; SELL = direction down and close below the filter, the first such bar after a BUY state.
BUY -> long at the next open, SELL -> out at the next open. Indicators run over the bars this script is given.
One position per coin, one fifth of the start per coin, 0.35% per side.
  state_fwd_rfbs.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_rfbs_twin.json  control: random entry bars (TWIN_P per free bar), same SELL exit
  python3 fwd_rfbs.py"""
import random
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: the five majors the other daily-rule accounts use
N, QTY = 20, 3.5               # rf_bs.py input_parameter defaults (its README table says 3.82 and hl2; the code wins)
TWIN_P = 1 / 42                # my choice: the backtest twin's rate (2 x 243 BTC trades / 20,311 4h bars, flat about half the time)
# also mine: fills at the next open, long only (the indicator also marks SELL as a short), size one fifth of the start per coin
LABEL = ("Range Filter B&S 4 ชม. (littleboyck/futu-indicators พอร์ต VuManChu) BTC ETH SOL BNB XRP: เส้นกรองขยับตามระยะ "
         "3.5 เท่าของค่าเฉลี่ยการขยับ ซื้อเมื่อเส้นกรองหันขึ้นและปิดเหนือเส้นครั้งแรก ขายเมื่อหันลงและปิดใต้เส้น "
         "(backtest Binance 4 ชม. 2017 ถึง 26 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 243 ไม้ +0.86% ต่อไม้ มัธยฐาน -2.42% ชนะ 33% "
         "ETH 234 ไม้ +1.11% SOL 160 ไม้ +2.62% BNB 231 ไม้ +2.49% XRP 222 ไม้ +0.60% ตัวแฝดเข้าสุ่มดีกว่าทุกเหรียญ "
         "+0.9 ถึง +4.0% ตั้งแต่ 2025 -0.59 ถึง -1.48% ต่อไม้ permutation 200 รอบบน 6,000 แท่งล่าสุด กริด 4 แบบ "
         "(ช่วง 20/50 x เท่า 2/3.5) p 0.582/0.403/0.249/0.189/0.353)")
ACCOUNTS = {"state_fwd_rfbs.json": ("rule", LABEL),
            "state_fwd_rfbs_twin.json": ("random", "Range Filter B&S 4 ชม. ตัวควบคุม: เข้าแท่งสุ่ม ออกเมื่อเส้นกรองให้สัญญาณขายแบบเดียวกัน")}


def signals(b):
    """per bar 'buy', 'sell' or None, as rf_bs.py on the close"""
    k1, k2 = 2 / (N + 1), 2 / (2 * N)          # EMA(N) and EMA(2N-1)
    e1 = e2 = filt = prevf = None
    fd, ci, out = 0, 0, [None]
    for i in range(1, len(b)):
        x = b[i]["c"]
        d = abs(x - b[i - 1]["c"])
        e1 = d if e1 is None else e1 + (d - e1) * k1
        e2 = e1 if e2 is None else e2 + (e1 - e2) * k2
        r = e2 * QTY
        if filt is None:
            filt = x
        else:
            if x - r > filt:
                filt = x - r
            if x + r < filt:
                filt = x + r
        if prevf is not None:
            fd = 1 if filt > prevf else -1 if filt < prevf else fd
        prevf = filt
        lc, sc = fd > 0 and x > filt, fd < 0 and x < filt
        pc, ci = ci, 1 if lc else -1 if sc else ci
        out.append("buy" if lc and pc == -1 else "sell" if sc and pc == 1 else None)
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
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "เส้นกรองหันลง ปิดใต้เส้น")
            continue
        ok = sg[i] == "buy" if mode == "rule" else rng.random() < TWIN_P
        if not ok:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "เส้นกรองหันขึ้น ปิดเหนือเส้น" if mode == "rule" else "สุ่มแท่ง"
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
            print("fwd_rfbs fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
