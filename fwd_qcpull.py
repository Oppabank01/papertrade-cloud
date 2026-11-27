#!/usr/bin/env python3
"""Forward paper test of "custom:trend_pullback" of codewithmernpy/quant-critic (GitHub, 25 Nov 2026, a backtest-audit
tool whose README ranks this example spec first of 9 on BTC, ETH, SOL 4h 2021-01 to 2025-10: locked-test Sharpe +0.25,
random-entry p 0.005, break-even 26.9 bps per side, verdict NEEDS WORK). Opened 27 Nov 2026 by the scout; backtest in
LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 4h Binance bars (user_strategies/examples/trend_pullback.json):
  close above EMA200 and RSI14 crossing above 40 (previous bar at or below) -> long at the next open;
  mirrored (mirror_long_for_short): close below EMA200 and RSI14 crossing below 60 -> short at the next open.
  Stop = entry -/+ 2 x ATR14 of the signal bar, target = 2.5 R (entry +/- 5 ATR), out at the close of the 36th bar
  from the entry bar on. Each closed bar from the entry bar on: the stop first (a gap through it fills at the open,
  except on the entry bar), then the target (a gap over it fills at the open, except on the entry bar), then the time
  stop; both touched in one bar = stop (the repo's worst-case tie-break).
My choices: RSI and ATR are Wilder (the repo's builder does not say which), the short mirror of 40 is 60, EMA200 seeded
with the first close of the bars fetched (1000 4h bars make the seed small). One position per coin, one third of the
start per coin, 0.35% per side (the repo charges 7 bps), no leverage, no funding.
  state_fwd_qcpull.json       BTC, ETH, SOL
  state_fwd_qcpull_twin.json  control: random entry bars (TWIN_P per flat bar), random side, the same stop, target, time stop
  python3 fwd_qcpull.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch, wilder_atr

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # the three coins of the repo's README table
TREND, RSI_N, LO, HI = 200, 14, 40.0, 60.0   # EMA200, RSI14 crossing 40 from the spec; 60 is my mirror for shorts
ATR_N, STOP_ATR, TP_R, MAX_BARS = 14, 2.0, 2.5, 36   # from the spec's exit block
TWIN_P = 1 / 60                        # my choice: gives about as many trades as the rule in the backtest
LABEL = ("trend pullback ของ quant-critic 4 ชม.: ปิดเหนือ EMA200 และ RSI14 ตัดขึ้น 40 (short กลับด้าน ตัดลง 60) stop 2 ATR "
         "เป้า 2.5R ถือไม่เกิน 36 แท่ง BTC ETH SOL (backtest Binance 4 ชม. 2017 ถึง 27 พ.ย. 69 หลังหัก 0.35%/ข้าง "
         "BTC 269 ไม้ -0.30% ETH 271 ไม้ +0.07% SOL 186 ไม้ -0.15% ต่อไม้ มัธยฐาน -2.5/-3.0/-4.3% ชนะ 38-41% "
         "ปี 2025+ -0.40/+0.42/+0.32% ตัวแฝดเข้าสุ่มออกแบบเดียวกัน -0.55/-0.59/-0.79% "
         "permutation 200 รอบบน 6,000 แท่งล่าสุด p 0.199/0.015/0.388)")
ACCOUNTS = {"state_fwd_qcpull.json": ("rule", LABEL),
            "state_fwd_qcpull_twin.json": ("random", "trend pullback ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งสุ่ม stop 2 ATR เป้า 2.5R ถือไม่เกิน 36 แท่งแบบเดียวกัน")}


def ema(c, n):
    k, out = 2 / (n + 1), [c[0]]
    for x in c[1:]:
        out.append(out[-1] + k * (x - out[-1]))
    return out


def wilder_rsi(c, n):
    out = [None] * len(c)
    if len(c) <= n:
        return out
    d = [b - a for a, b in zip(c, c[1:])]
    g = sum(max(x, 0) for x in d[:n]) / n
    l = sum(max(-x, 0) for x in d[:n]) / n
    for i in range(n, len(c)):
        if i > n:
            g = (g * (n - 1) + max(d[i - 1], 0)) / n
            l = (l * (n - 1) + max(-d[i - 1], 0)) / n
        out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out


def lines(b):
    c = [x["c"] for x in b]
    return ema(c, TREND), wilder_rsi(c, RSI_N), wilder_atr(b, ATR_N)


def signal(b, i, tr, r):
    if r[i - 1] is None:
        return 0
    if b[i]["c"] > tr[i] and r[i - 1] <= LO < r[i]:
        return 1
    if b[i]["c"] < tr[i] and r[i - 1] >= HI > r[i]:
        return -1
    return 0


def exit_px(p, x):
    """One closed bar against position p (dict with d, stop, tp, entry_t): (fill price, why) or None."""
    first, d = x["t"] == p["entry_t"], p["d"]
    if (d > 0 and x["l"] <= p["stop"]) or (d < 0 and x["h"] >= p["stop"]):
        return (p["stop"] if first else (min if d > 0 else max)(x["o"], p["stop"])), "stop"
    if (d > 0 and x["h"] >= p["tp"]) or (d < 0 and x["l"] <= p["tp"]):
        return (p["tp"] if first else (max if d > 0 else min)(x["o"], p["tp"])), "tp"
    if (x["t"] - p["entry_t"]) // B.H4 + 1 >= MAX_BARS:
        return x["c"], "time"
    return None


def trades(b, first=TREND + 1, rng=None):
    """The backtest (the scout's /tmp/scout_2320/bt.py calls this): list of dict(t, d, e, x, why), oldest first.
    rng given: the twin's entries (random bar and side) with the same exits."""
    tr, r, atr = lines(b)
    out, p = [], None
    for i in range(first, len(b) - 1):
        if p and b[i]["t"] >= p["entry_t"]:
            hit = exit_px(p, b[i])
            if hit:
                out.append(dict(t=p["entry_t"], d=p["d"], e=p["e"], x=hit[0], why=hit[1]))
                p = None
        if p or atr[i] is None:
            continue
        d = signal(b, i, tr, r) if rng is None else (rng.choice((1, -1)) if rng.random() < TWIN_P else 0)
        if d:
            e = b[i + 1]["o"]
            p = dict(entry_t=b[i + 1]["t"], d=d, e=e, stop=e - d * STOP_ATR * atr[i],
                     tp=e + d * TP_R * STOP_ATR * atr[i])
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


WHY = {"stop": f"หลุด stop {STOP_ATR:g} ATR", "tp": f"ถึงเป้า {TP_R:g}R", "time": f"ครบ {MAX_BARS} แท่ง"}


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    tr, r, atr = lines(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < 1:
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            hit = exit_px(p, x)
            if hit:
                close(s, sym, hit[0], x["t"] + B.H4, WHY[hit[1]])
        if sym in s["pos"] or atr[i] is None:
            continue
        d = signal(bars, i, tr, r) if mode == "rule" else (rng.choice((1, -1)) if rng.random() < TWIN_P else 0)
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = ((f"ปิดเหนือ EMA200 RSI14 ตัดขึ้น {LO:g}" if d > 0 else f"ปิดใต้ EMA200 RSI14 ตัดลง {HI:g}") if mode == "rule"
               else "สุ่มแท่ง สุ่มฝั่ง")
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=e - d * STOP_ATR * atr[i], tp=e + d * TP_R * STOP_ATR * atr[i],
                             entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e,
                             usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_qcpull fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
