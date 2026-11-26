#!/usr/bin/env python3
"""Forward paper test of Heikin Ashi + Supertrend (ipankaj-v/nifty-heikinashi-supertrend, GitHub 17 Nov 2026: "nifty heikin
ashi super trend alert and paper trade", repo is only a Laravel skeleton so the rule is the common TradingView one) on BTC,
ETH, SOL, BNB, XRP (opened 27 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak
ideas too). Fake money only.

On closed 4h Binance bars, long only: Heikin Ashi bars (close = (o+h+l+c)/4, open = mean of the previous HA open and close,
seeded with (o+c)/2, high/low include the HA open and close); Supertrend(10, 3) on those HA bars as TradingView
ta.supertrend (ATR = RMA of true range seeded with the first range, bands = HA (h+l)/2 +- 3 ATR that ratchet unless the
previous HA close crossed them; trend turns up when the HA close is above this bar's upper band, down when below the
lower band). BUY = trend turns up, SELL = trend turns down; both fill at the next real open. Indicators run over the bars
this script is given. One position per coin, one fifth of the start per coin, 0.35% per side.
  state_fwd_hast.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_hast_twin.json  control: random entry bars (TWIN_P per free bar), same SELL exit
  python3 fwd_hast.py"""
import random
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: the five majors the other 4h accounts use
N, MULT = 10, 3.0              # my choice: TradingView's Supertrend defaults (the repo gives no numbers)
TWIN_P = 1 / 63                # my choice: the backtest twin's rate (2 x 162 BTC trades / 20,314 4h bars)
# also mine: 4h bars, fills at the next open, long only, size one fifth of the start per coin
LABEL = ("Heikin Ashi + Supertrend 4 ชม. (ipankaj-v/nifty-heikinashi-supertrend) BTC ETH SOL BNB XRP: แท่ง Heikin Ashi "
         "แล้วใช้ Supertrend 10 แท่ง 3 ATR ซื้อเมื่อเทรนด์หันขึ้น ขายเมื่อหันลง (backtest Binance 4 ชม. 2017 ถึง 26 พ.ย. 69 "
         "หลังหัก 0.35%/ข้าง BTC 162 ไม้ +2.23% ต่อไม้ มัธยฐาน -2.33% ชนะ 38% ETH 161 ไม้ +2.60% SOL 107 ไม้ +7.99% "
         "BNB 157 ไม้ +4.66% XRP 141 ไม้ +2.87% ตัวแฝดเข้าสุ่ม +2.0 ถึง +10.0% ใกล้หรือดีกว่า ตั้งแต่ 2025 -0.25 ถึง -2.65% "
         "ต่อไม้ permutation 200 รอบบน 6,000 แท่งล่าสุด กริด 4 แบบ p 0.244/0.303/0.229/0.468/0.264)")
ACCOUNTS = {"state_fwd_hast.json": ("rule", LABEL),
            "state_fwd_hast_twin.json": ("random", "Heikin Ashi + Supertrend 4 ชม. ตัวควบคุม: เข้าแท่งสุ่ม ออกเมื่อเทรนด์หันลงแบบเดียวกัน")}


def ha(b):
    out, po, pc = [], None, None
    for x in b:
        c = (x["o"] + x["h"] + x["l"] + x["c"]) / 4
        o = (x["o"] + x["c"]) / 2 if po is None else (po + pc) / 2
        out.append((o, max(x["h"], o, c), min(x["l"], o, c), c))
        po, pc = o, c
    return out


def signals(b):
    """per bar 'buy', 'sell' or None: Supertrend(N, MULT) on the Heikin Ashi bars"""
    atr = fu = fl = pc = None
    d, out = 0, []
    for i, (o, h, l, c) in enumerate(ha(b)):
        tr = h - l if pc is None else max(h - l, abs(h - pc), abs(l - pc))
        atr = tr if atr is None else atr + (tr - atr) / N
        mid = (h + l) / 2
        up, lo = mid + MULT * atr, mid - MULT * atr
        if fu is None:
            nu, nl = up, lo
        else:
            nu = up if (up < fu or pc > fu) else fu
            nl = lo if (lo > fl or pc < fl) else fl
        sig = None
        if fu is not None and i >= N:
            prev = d
            if d != 1 and c > nu:
                d = 1
            elif d != -1 and c < nl:
                d = -1
            sig = "buy" if d == 1 and prev != 1 else "sell" if d == -1 and prev == 1 else None
        fu, fl, pc = nu, nl, c
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
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "Supertrend บน Heikin Ashi หันลง")
            continue
        ok = sg[i] == "buy" if mode == "rule" else rng.random() < TWIN_P
        if not ok:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "Supertrend บน Heikin Ashi หันขึ้น" if mode == "rule" else "สุ่มแท่ง"
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
            print("fwd_hast fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
