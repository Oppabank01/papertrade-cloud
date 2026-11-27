#!/usr/bin/env python3
"""Forward paper test of a mechanical ICC (Indication, Correction, Continuation), for Elneto264's X post (9 Nov 2026:
"0 of 4 markets passed my fixed-rule ICC test after costs"; the rules sit in an X article we cannot read, so every
number here is my choice). Opened 27 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked
to try weak ideas too. Fake money only.

On closed 4h Binance bars, long only:
  Indication: a close above the highest high of the N bars before; L = that high, SH = highest high since then.
  Correction: within W bars, a low at least PB*ATR14 under SH while no close falls under L - FAIL*ATR14;
              CL = lowest low of the correction.
  Continuation: within W bars of the correction start, a close above SH -> buy at the next open.
Stop CL, target entry + RR*(entry - CL), else sell at the close of the HOLD-th bar. A gap through the stop or target
fills at the open; both touched in one bar = stop. No setup is tracked while a position is open. One position per
coin, one eighth of the start per coin, 0.35% per side.
  state_fwd_icc.json       8 coins
  state_fwd_icc_twin.json  control: random entry bars (TWIN_P per free bar), stop at the lowest low of the last 6 bars,
                           the same target and time exit
  python3 fwd_icc.py"""
import random
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]   # my choice
N = 50                         # my choice: indication lookback (searched 20 and 50, long+short and long only; 50 long best)
W = 12                         # my choice: bars allowed for the correction to start, and then for the continuation
PB = 1.0                       # my choice: the correction must pull back at least 1 ATR14 from the swing high
FAIL = 1.0                     # my choice: a close more than 1 ATR14 under the broken high cancels the setup
RR = 2.0                       # my choice: target 2R
HOLD = 30                      # my choice: time exit at the close of the 30th bar (5 days)
TWIN_P = 1 / 160               # my choice: about as many twin entries as the rule had in the backtest (908 / 8 coins)
TWIN_LB = 6                    # my choice: twin stop = lowest low of the last 6 bars
LABEL = ("ICC 4 ชม. long อย่างเดียว 8 เหรียญ (แทนโพสต์ Elneto264 ที่ไม่เห็นกฎ): ทะลุจุดสูง 50 แท่ง ย่อ 1 ATR ปิดเหนือจุดสูงอีกครั้ง "
         "stop ที่จุดต่ำของการย่อ เป้า 2R ถือไม่เกิน 30 แท่ง (backtest Binance 2017-2026 หลังหัก 0.35%/ข้าง 908 ไม้ +0.85% ต่อไม้ "
         "มัธยฐาน -2.80% ชนะ 41% BTC +0.34% ETH +0.82% SOL +0.27% BNB +0.93% XRP +2.29% DOGE +3.77% ADA -0.13% LINK -0.18% "
         "ตัวแฝดเข้าสุ่มแพ้กฎครบ 8 เหรียญ permutation 200 รอบ p BTC 0.552 ETH 0.070 SOL 0.567 BNB 0.328 XRP 0.010 "
         "DOGE 0.055 ADA 0.433 LINK 0.806 ไม่ผ่านประตู ตั้งแต่ 2025 ติดลบ 6 ใน 8 เหรียญ)")
ACCOUNTS = {"state_fwd_icc.json": ("rule", LABEL),
            "state_fwd_icc_twin.json": ("random", "ICC ตัวควบคุม: เข้าสุ่มแท่ง stop จุดต่ำ 6 แท่ง เป้า 2R ถือไม่เกิน 30 แท่ง แบบเดียวกัน")}


def atr14(b):
    out, a = [None] * len(b), 0.0
    for i in range(1, len(b)):
        tr = max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - b[i - 1]["c"]), abs(b[i]["l"] - b[i - 1]["c"]))
        a = tr if i == 1 else (a * 13 + tr) / 14
        if i >= 14:
            out[i] = a
    return out


def setup_step(su, b, i, a):
    """Advance the ICC setup with closed bar i (a = its ATR14). Returns the stop on a continuation close, else None."""
    x = b[i]
    if su.get("ph") == 1:                                    # waiting for the correction
        su["SH"] = max(su["SH"], x["h"])
        if x["c"] < su["L"] - FAIL * a or (x["t"] - su["t0"]) / H4 > W:
            su.clear()
        elif su["SH"] - x["l"] >= PB * a:
            su.update(ph=2, tc=x["t"], CL=x["l"])
        return None
    if su.get("ph") == 2:                                    # in the correction, waiting for the continuation close
        if x["c"] > su["SH"]:
            stop = su["CL"]
            su.clear()
            return stop
        su["CL"] = min(su["CL"], x["l"])
        if x["c"] < su["L"] - FAIL * a or (x["t"] - su["tc"]) / H4 > W:
            su.clear()
        return None
    if i >= N:
        hi = max(y["h"] for y in b[i - N:i])
        if x["c"] > hi:
            su.update(ph=1, L=hi, SH=x["h"], t0=x["t"])
    return None


def exit_px(p, y):
    s, t = p["stop"], p["tgt"]
    return y["o"] if y["o"] <= s else s if y["l"] <= s else max(t, y["o"]) if y["h"] >= t else None


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px * (1 - COST)
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    su = s.setdefault("su", {}).setdefault(sym, {})
    atr = atr14(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p:
            if x["t"] < p["entry_t"]:
                continue
            px = exit_px(p, x)
            why = "stop" if px is not None and px < p["entry"] else "ถึงเป้า 2R"
            if px is None and (x["t"] - p["entry_t"]) / H4 + 1 >= HOLD:
                px, why = x["c"], f"ครบ {HOLD} แท่ง"
            if px is not None:
                close(s, sym, px, x["t"] + H4, why)
            continue
        if not atr[i]:
            continue
        if mode == "rule":
            stop = setup_step(su, bars, i, atr[i])
        else:
            stop = min(y["l"] for y in bars[max(0, i - TWIN_LB + 1):i + 1]) if rng.random() < TWIN_P else None
        if stop is None:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if e <= stop or s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd * (1 + COST)
        why = "ICC ปิดเหนือจุดสูงหลังย่อ" if mode == "rule" else "สุ่มแท่ง"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, stop=stop, tgt=e + RR * (e - stop),
                             entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_icc fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
