#!/usr/bin/env python3
"""Forward paper test of fransratlabala/ZLEMA-Trend-Martingale-Levels-H4-Crypto-Backtest- (GitHub, Nov 2026): dual-ZLEMA
trend flips on 4h bars with a capped Martingale re-entry ladder, per-coin settings from the repo's notebook (CONFIG).
Opened 25 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too.
Fake money only.

On closed 4h Binance bars: trend = sign(ZLEMA fast - ZLEMA slow) (ZLEMA = EMA of 2*close - close[lag], lag (n-1)//2,
seeded at its first value, as the repo). A bar where the trend flips -> enter that way at the next open, level 1. Stop
SL x ATR14 (EMA of true range, as the repo) from the entry, target RR x that risk, checked bar by bar from the entry
bar; a gap through the stop fills at the open, the target fills at the target (as the repo), both touched = stop. A
stop below the coin's max level -> level + 1 and re-enter the same way at the next open after the first later bar
whose trend still points that way (no fresh signals until then); a target, or a stop at the max level, resets to
level 0. Bars with trend 0 are skipped entirely (as the repo). Size = BASE x level (the repo's WEIGHT_BY_LEVEL).
One position per coin, 0.35% per side.
  state_fwd_zlemamart.json       10 coins of the repo
  state_fwd_zlemamart_twin.json  control: random entry bars (TWIN_P per free bar), random side, same exits and ladder
  python3 fwd_zlemamart.py"""
import random
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                          # per side, as every account here
ATR_N = 14                             # the repo's ATR_PERIOD
# symbol: (fast, slow, sl_atr, rr, max_levels), the repo's CONFIG (its own per-coin picks, in-sample to Nov 2026)
CONFIG = {"LTCUSDT": (15, 60, 1.75, 2.5, 3), "XRPUSDT": (15, 100, 1.75, 2.0, 2), "ADAUSDT": (25, 70, 1.75, 2.0, 3),
          "ETHUSDT": (25, 60, 2.00, 2.0, 2), "LINKUSDT": (20, 70, 2.50, 1.5, 5), "BTCUSDT": (15, 80, 1.75, 2.5, 3),
          "DOGEUSDT": (35, 80, 1.75, 2.0, 3), "TRXUSDT": (35, 60, 1.50, 3.0, 1), "SOLUSDT": (25, 60, 1.75, 2.5, 1),
          "BNBUSDT": (50, 80, 2.00, 1.5, 1)}
BASE = 1 / 30                          # my choice: level-1 size as a share of the start; all 10 coins at their max level = 24/30
TWIN_P = 1 / 60                        # my choice: about the rule's flip rate per bar in the backtest (1 flip in 43 to 109 bars by coin)
LABEL = ("ZLEMA + Martingale 4 ชม. (fransratlabala) 10 เหรียญ เลขต่อเหรียญของ repo: ZLEMA เร็ว/ช้ากลับทิศ เข้าแท่งถัดไป stop เป็น ATR "
         "เป้าเป็น R โดน stop เติมไม้ระดับถัดไปขนาดเท่าระดับ (backtest Binance 4 ชม. 2017-2026 หลังหัก 0.35%/ข้าง ขนาดเท่ากันทุกไม้ "
         "LTC +0.94% ADA +0.95% DOGE +1.10% SOL +1.04% LINK +0.65% XRP +0.28% BNB +0.01% ETH -0.14% BTC -0.21% TRX -0.55% ต่อไม้ "
         "มัธยฐาน -2.3 ถึง -4.6% p 0.005 ถึง 0.02 ยกเว้น TRX 0.30 ตัวแฝดเข้าสุ่ม -0.84 ถึง +0.01% "
         "แต่เลขของแต่ละเหรียญคือเลขดีสุดของเหรียญนั้น ใช้เลขชุดเดียว 25/70 ทุกเหรียญติดลบ 8 ใน 10 ค่ามัธยฐานของ 10 ชุดติดลบ 9 ใน 10 "
         "permutation แบบเลือกดีสุดจาก 10 ชุด SOL p 0.020 BTC p 0.119 จึงน่าจะ overfit)")
ACCOUNTS = {"state_fwd_zlemamart.json": ("rule", LABEL),
            "state_fwd_zlemamart_twin.json": ("random", "ZLEMA + Martingale ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งสุ่ม stop เป้า และบันไดเติมไม้แบบเดียวกัน")}


def ema(x, n):
    out, a, v = [None] * len(x), 2 / (n + 1), None
    for i, y in enumerate(x):
        if y is not None:
            v = y if v is None else a * y + (1 - a) * v
        out[i] = v
    return out


def ind(b, fast, slow):
    c = [x["c"] for x in b]

    def zlema(n):
        lag = (n - 1) // 2
        return ema([2 * c[i] - c[i - lag] if i >= lag else None for i in range(len(c))], n)
    f, s = zlema(fast), zlema(slow)
    trend = [0 if a is None or z is None else (a > z) - (a < z) for a, z in zip(f, s)]
    tr = [b[0]["h"] - b[0]["l"]] + [max(x["h"] - x["l"], abs(x["h"] - p["c"]), abs(x["l"] - p["c"])) for p, x in zip(b, b[1:])]
    return trend, ema(tr, ATR_N)


def exit_px(p, x):
    o, h, l, d = x["o"], x["h"], x["l"], p["d"]
    if d > 0:
        return (min(o, p["stop"]), "stop") if l <= p["stop"] else (p["tgt"], "ถึงเป้า") if h >= p["tgt"] else (None, "")
    return (max(o, p["stop"]), "stop") if h >= p["stop"] else (p["tgt"], "ถึงเป้า") if l <= p["tgt"] else (None, "")


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    fast, slow, sl, rr, top = CONFIG[sym]
    seen, m = s.setdefault("seen", {}), s.setdefault("mart", {}).setdefault(sym, dict(level=0, want=0))
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    trend, atr = ind(bars, fast, slow)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i == 0:
            continue
        seen[sym] = x["t"]
        if trend[i] == 0:
            continue
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            px, why = exit_px(p, x)
            if px is not None:
                d = p["d"]
                close(s, sym, px, x["t"] + H4, f"{why} ไม้ระดับ {p['level']}")
                if why == "stop" and m["level"] < top:
                    m["level"], m["want"] = m["level"] + 1, d
                else:
                    m["level"], m["want"] = 0, 0
                continue
        if sym in s["pos"]:
            continue
        if m["want"]:
            if trend[i] != m["want"]:
                continue
            d, m["want"], why = m["want"], 0, f"เติมไม้ระดับ {m['level']} หลังโดน stop"
        elif mode == "rule":
            if not trend[i - 1] or trend[i] == trend[i - 1]:
                continue
            d, m["level"], why = trend[i], 1, f"ZLEMA {fast}/{slow} กลับทิศ{'ขึ้น' if trend[i] > 0 else 'ลง'}"
        else:
            if rng.random() >= TWIN_P:
                continue
            d, m["level"], why = rng.choice((1, -1)), 1, "สุ่มแท่ง ฝั่งสุ่ม"
        e, usd = bars[i + 1]["o"], s["start_usd"] * BASE * m["level"]
        if d > 0 and s["cash"] < usd * (1 + COST):
            m["level"], m["want"] = 0, 0
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd, level=m["level"],
                             stop=e - d * sl * atr[i], tgt=e + d * sl * rr * atr[i], entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in CONFIG:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("zlemamart fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
