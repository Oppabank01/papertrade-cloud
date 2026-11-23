#!/usr/bin/env python3
"""Forward paper test of anna-johney/momentum-mean-reversion-regime-switcher (GitHub, Nov 2026) on BTC, ETH, SOL daily
bars (opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too).
Fake money only.

On closed daily Binance bars: efficiency ratio ER = |close - close N bars ago| / sum of |daily close changes| over those
N bars. ER >= ER_TH -> momentum: long if close > close N bars ago, short if below. ER < ER_TH -> mean reversion: z = (close
- mean of the last N closes) / their population SD; |z| >= Z_TH -> the opposite side of z, else flat. When the wanted side
differs from the held one, close and/or open at the next open (the repo fills at the next close; on Binance's 24/7 daily
bars the next open is that close). No stop, no target. All three numbers are the repo's fixed rules, none chosen by me.
One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_regime.json       BTC, ETH, SOL
  state_fwd_regime_twin.json  control: each day with chance TWIN_P picks a random side (long, short or flat) and holds it
  python3 fwd_regime.py"""
import random
import statistics as st
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the repo takes any one series
N, ER_TH, Z_TH = 20, 0.35, 0.5     # the repo's fixed rules
TWIN_P = 1 / 6                     # my choice: about the rule's rate of side changes per coin-day in the backtest
LABEL = ("regime switcher รายวัน BTC ETH SOL (anna-johney/momentum-mean-reversion-regime-switcher): ER 20 วัน 0.35 ขึ้นไปตามโมเมนตัม "
         "ต่ำกว่านั้นสวน z-score 0.5 long+short (backtest 2017-2026 หลังหัก 0.35%/ข้าง BTC 617 ไม้ -0.16% p 0.080 "
         "ETH 640 ไม้ -0.79% p 0.652 SOL 445 ไม้ -0.27% p 0.259 ก่อนหัก +0.54/-0.09/+0.43% ชนะราว 50% ปี 2024+ -0.08/-0.35/-1.10% "
         "ตัวแฝดสุ่มฝั่ง -0.81 ถึง -0.86% ติดลบหลังหักทุกเหรียญ)")
ACCOUNTS = {"state_fwd_regime.json": ("rule", LABEL),
            "state_fwd_regime_twin.json": ("random", "regime switcher ตัวควบคุม: ทุกวันมีโอกาส 1 ใน 6 สุ่มฝั่งใหม่ (long short หรือว่าง)")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def eff(c):
    path = sum(abs(y - x) for x, y in zip(c, c[1:]))
    return abs(c[-1] - c[0]) / path if path else 0.0


def signal(b, i):
    """Wanted side after the close of bar i: 1, -1 or 0 (None before N bars of history)."""
    if i < N:
        return None
    c = [x["c"] for x in b[i - N:i + 1]]
    if eff(c) >= ER_TH:
        return 1 if c[-1] > c[0] else -1 if c[-1] < c[0] else 0
    w = c[1:]
    sd = st.pstdev(w)
    z = (c[-1] - st.fmean(w)) / sd if sd else 0.0
    return (-1 if z > 0 else 1) if abs(z) >= Z_TH else 0


def trades(b, first=30):
    """The backtest (the scout's /tmp/scout_1115.py calls this): list of dict(t, d, e, x), oldest first."""
    out, p = [], None
    for i in range(first, len(b) - 1):
        want = signal(b, i)
        if want is None or want == (p["d"] if p else 0):
            continue
        if p:
            out.append(dict(p, x=b[i + 1]["o"]))
            p = None
        if want:
            p = dict(t=b[i + 1]["t"], d=want, e=b[i + 1]["o"])
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
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        cur = p["d"] if p else 0
        if mode == "rule":
            want = signal(bars, i)
        else:
            want = rng.choice((1, -1, 0)) if rng.random() < TWIN_P else cur
        if want is None or want == cur:
            continue
        e, t = bars[i + 1]["o"], bars[i + 1]["t"]
        er = eff([y["c"] for y in bars[i - N:i + 1]]) if i >= N else 0.0
        why = "สุ่มฝั่งใหม่" if mode != "rule" else f"ER {er:.2f} " + ("ตามโมเมนตัม" if er >= ER_TH else "สวน z-score")
        if p:
            close(s, sym, e, t, why)
        if not want:
            continue
        usd = s["start_usd"] / 3
        if want > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if want > 0 else usd) - usd * COST
        s["pos"][sym] = dict(side="long" if want > 0 else "short", d=want, qty=want * usd / e, entry=e, last=e, usd=usd,
                             entry_t=t, t=iso(t), why=why)
        s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_regime fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
