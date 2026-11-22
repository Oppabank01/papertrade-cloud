#!/usr/bin/env python3
"""Forward paper test of the "Bollinger breakout" row of thecomicopera/trading-backtest-lab on BTC, ETH, SOL (opened
23 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too). Fake money only.

On closed 4h Binance bars: close above the upper Bollinger band (SMA20 + 2 population SD, the repo's defaults) -> long at
the next open; out at the next open after a close below the middle band (SMA20). No stop and no time limit (the repo's
rule has none). Long only, as in the repo. One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_bbbreak.json       BTC, ETH, SOL
  state_fwd_bbbreak_twin.json  control: random entry bars (TWIN_P per free bar), same exit
  python3 fwd_bbbreak.py"""
import random
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
N, K = 20, 2.0                     # the repo's defaults, not tuned (one setting tried)
TWIN_P = 1 / 40                    # the rule traded 979 times in ~37,000 free coin-bars, so the twin trades about as often
LABEL = ("Bollinger breakout 4 ชม. BTC ETH SOL: ปิดเหนือกรอบบน (SMA20 + 2 SD) ซื้อเปิดแท่งถัดไป ขายเมื่อปิดใต้เส้นกลาง long อย่างเดียว "
         "(backtest 2017-2026 หลังหัก 0.35%/ข้าง 979 ไม้ เฉลี่ย +0.44% มัธยฐาน -1.94% ชนะ 34% permutation p BTC 0.010 ETH 0.080 SOL 0.284 "
         "ปี 2024+ ติดลบทั้งสามเหรียญ -0.33 ถึง -0.71% ต่อไม้)")
ACCOUNTS = {"state_fwd_bbbreak.json": ("rule", LABEL),
            "state_fwd_bbbreak_twin.json": ("random", "Bollinger breakout ตัวควบคุม: ซื้อแท่งสุ่ม ขายเมื่อปิดใต้เส้นกลางแบบเดียวกัน")}


def bands(b, n=N, k=K):
    c = [x["c"] for x in b]
    up, mid = [None] * len(b), [None] * len(b)
    for i in range(n - 1, len(b)):
        w = c[i - n + 1:i + 1]
        m = sum(w) / n
        sd = (sum((v - m) ** 2 for v in w) / n) ** 0.5
        up[i], mid[i] = m + k * sd, m
    return up, mid


def trades(b, first=N):
    """The backtest (same as the scout's /tmp/scout_0240.py bb_trades): list of dict(t, e, x, hold), oldest first."""
    up, mid = bands(b)
    out, i, n = [], first, len(b)
    while i < n - 1:
        if up[i] is None or b[i]["c"] <= up[i]:
            i += 1
            continue
        e, j = b[i + 1]["o"], i + 1
        while j < n - 1 and b[j]["c"] >= mid[j]:
            j += 1
        if j >= n - 1:
            break
        out.append(dict(t=b[i + 1]["t"], e=e, x=b[j + 1]["o"], hold=j - i))
        i = j + 1
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
    up, mid = bands(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"] and mid[i] is not None and x["c"] < mid[i]:
            close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "ปิดใต้เส้นกลาง SMA20")
            exited = True
        if sym in s["pos"] or exited or up[i] is None:
            continue
        if not (x["c"] > up[i] if mode == "rule" else rng.random() < TWIN_P):
            continue
        e, t0, usd = bars[i + 1]["o"], bars[i + 1]["t"], s["start_usd"] / 3
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += -usd - usd * COST
        why = f"ปิดเหนือกรอบบน {x['c'] / up[i] - 1:+.2%}" if mode == "rule" else "สุ่มแท่ง"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=t0, t=iso(t0), why=why)
        s["log"].append(dict(kind="buy", t=iso(t0), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_bbbreak fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
