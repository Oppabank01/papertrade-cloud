#!/usr/bin/env python3
"""Forward paper test of the WaveTrend zone rule (uegeersoy/wavetrend-bot, GitHub 19 Oct 2026: alerts when LazyBear's
WaveTrend WT1, channel 10 and average 21, enters the zone at -65 or +65; the repo runs it on daily forex) on BTC, ETH, SOL,
BNB, XRP 4h bars (opened 27 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak
ideas too). Fake money only.

On closed 4h Binance bars, long only: ap = (h+l+c)/3, esa = EMA10(ap), d = EMA10(|ap-esa|), ci = (ap-esa)/(0.015 d),
WT1 = EMA21(ci), EMAs seeded with the first value of the bars this script is given (as the repo's pandas ewm adjust=False).
BUY = WT1 crosses down into the lower zone (previous bar above -65, this bar at or below), SELL = WT1 crosses up into the
upper zone (previous below +65, this at or above); both fill at the next open. One position per coin, one fifth of the
start per coin, 0.35% per side.
  state_fwd_wt.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_wt_twin.json  control: random entry bars (TWIN_P per free bar), same SELL exit
  python3 fwd_wt.py"""
import random
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: the five majors the other 4h accounts use
N1, N2, LO, HI = 10, 21, -65, 65   # from the repo
TWIN_P = 1 / 250               # my choice: about the rule's entry rate per free 4h bar in the backtest (1 in 170 to 330)
# also mine: 4h crypto bars instead of daily forex (I tried daily and 4h, and SELL at 0 instead of +65: 4 settings),
# buying on the lower-zone entry and selling on the upper-zone entry, fills at the next open, size one fifth of the start
LABEL = ("WaveTrend 4 ชม. (uegeersoy/wavetrend-bot) BTC ETH SOL BNB XRP: ซื้อเมื่อ WT1 10/21 ลงไปถึง -65 ขายเมื่อขึ้นถึง +65 "
         "(backtest Binance 4 ชม. 2017 ถึง 26 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 41 ไม้ +0.59% ต่อไม้ มัธยฐาน +0.87% ชนะ 51% "
         "ETH 42 ไม้ +3.98% SOL 29 ไม้ +3.59% BNB 40 ไม้ +5.54% XRP 41 ไม้ +4.11% ตัวแฝดเข้าสุ่ม 1 ใน 250 แท่งออกแบบเดียวกัน "
         "+0.50/+0.70/+5.63/+4.51/+2.05% ใกล้กัน แพ้ถือเฉยๆ ทุกเหรียญ permutation 200 รอบบน 6,000 แท่งล่าสุด กริด 2 แบบ "
         "p 0.169/0.333/0.114/0.299/0.532)")
ACCOUNTS = {"state_fwd_wt.json": ("rule", LABEL),
            "state_fwd_wt_twin.json": ("random", "WaveTrend 4 ชม. ตัวควบคุม: เข้าแท่งสุ่ม ออกเมื่อ WT1 ขึ้นถึง +65 แบบเดียวกัน")}


def ema(v, n):
    a, e, out = 2 / (n + 1), v[0], []
    for x in v:
        e += a * (x - e)
        out.append(e)
    return out


def wt1(b):
    ap = [(x["h"] + x["l"] + x["c"]) / 3 for x in b]
    esa = ema(ap, N1)
    d = ema([abs(a - e) for a, e in zip(ap, esa)], N1)
    return ema([(a - e) / (0.015 * dd) if dd else 0.0 for a, e, dd in zip(ap, esa, d)], N2)


def signals(b):
    """per bar 'buy' (WT1 enters the lower zone), 'sell' (enters the upper zone) or None"""
    if not b:
        return []
    w, out = wt1(b), [None]
    for i in range(1, len(b)):
        out.append("buy" if w[i - 1] > LO >= w[i] else "sell" if w[i - 1] < HI <= w[i] else None)
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
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "WaveTrend ขึ้นถึง +65")
            continue
        ok = sg[i] == "buy" if mode == "rule" else rng.random() < TWIN_P
        if not ok:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "WaveTrend ลงถึง -65" if mode == "rule" else "สุ่มแท่ง"
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
            print("fwd_wt fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
