#!/usr/bin/env python3
"""Forward paper test of the "RSI mean reversion" rule in Do0vm/crypto-backtest-lab (GitHub, Nov 2026) on BTC, ETH, SOL
daily bars (opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas
too). Fake money only.

On closed daily Binance bars, long only: RSI14 (Wilder) below ENTRY -> buy at the next open; out at the next open after a
close with RSI14 above EXIT. No stop and no time stop (the repo has neither). The repo picked ENTRY/EXIT per coin
(BTC 20/65, ETH 25/70, SOL 30/60); here one setting for all three, chosen in-sample (below).
One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_rsi14.json       BTC, ETH, SOL
  state_fwd_rsi14_twin.json  control: random entry days (TWIN_P per free day), same RSI exit
  python3 fwd_rsi14.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
N = 14                             # the repo's RSI period
# grid tried in-sample (bars before 2024, BTC+ETH+SOL pooled): ENTRY 20/25/30 x EXIT 60/65/70 = 9 settings (the repo's grid
# was entry 20-35 x exit 50-70, 20 combos, per coin)
GRID = [(a, z) for a in (20, 25, 30) for z in (60, 65, 70)]
# chosen: best pooled in-sample mean per trade after costs among settings with 20+ in-sample trades. The overall best
# (20/70, +22.3% per trade) had only 8 in-sample trades and 12 in nine years, too rare to forward test; the 20-trade floor
# is my choice, added after seeing the grid.
ENTRY, EXIT = 25, 65
TWIN_P = 1 / 25                    # my choice: about the rule's entry rate per free coin-day
LABEL = ("RSI14 รายวัน BTC ETH SOL (Do0vm/crypto-backtest-lab): RSI14 ต่ำกว่า 25 ซื้อ ออกเมื่อ RSI14 เกิน 65 long อย่างเดียว ไม่มี stop "
         "(backtest 2017-2026 หลังหัก 0.35%/ข้าง 31 ไม้ เฉลี่ย +12.0% มัธยฐาน +11.4% ชนะ 81% BTC 13 ไม้ +8.6% ETH 11 ไม้ +17.2% "
         "SOL 7 ไม้ +10.3% ตัวแฝดซื้อวันสุ่ม +0.3 ถึง +3.1% permutation p 0.55/0.32/0.75 ไม้น้อย แพ้ถือเฉยๆ)")
ACCOUNTS = {"state_fwd_rsi14.json": ("rule", LABEL),
            "state_fwd_rsi14_twin.json": ("random", "RSI14 ตัวควบคุม: ซื้อวันสุ่ม ออกเมื่อ RSI14 เกิน 65 แบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def rsi(b, n=N):
    c, out, ag, al = [x["c"] for x in b], [None] * len(b), 0.0, 0.0
    for i in range(1, len(c)):
        g, l = max(c[i] - c[i - 1], 0), max(c[i - 1] - c[i], 0)
        if i <= n:
            ag += g / n; al += l / n
        else:
            ag = (ag * (n - 1) + g) / n; al = (al * (n - 1) + l) / n
        if i >= n:
            out[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def trades(b, entry=ENTRY, exit_=EXIT, first=30, r=None):
    """The backtest (the scout's /tmp/scout_0613.py calls this): list of dict(t, d, e, x), oldest first."""
    r, out, p = r or rsi(b), [], None
    for i in range(first, len(b) - 1):
        if r[i] is None:
            continue
        if p:
            if r[i] > exit_:
                out.append(dict(t=p[0], d=1, e=p[1], x=b[i + 1]["o"]))
                p = None
            continue
        if r[i] < entry:
            p = (b[i + 1]["t"], b[i + 1]["o"])
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
    r = rsi(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        if r[i] is None:
            continue
        if sym in s["pos"]:
            if r[i] > EXIT:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], f"RSI14 {r[i]:.0f} เกิน {EXIT}")
            continue
        go = r[i] < ENTRY if mode == "rule" else rng.random() < TWIN_P
        if not go:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += -usd - usd * COST
        why = f"RSI14 {r[i]:.0f} ต่ำกว่า {ENTRY}" if mode == "rule" else "สุ่มวัน"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd,
                             entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_rsi14 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
