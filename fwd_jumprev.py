#!/usr/bin/env python3
"""Forward paper test of the "basic mean-reverting strategy" in De Nicola, "On the Intraday Behavior of Bitcoin",
Ledger 6 (2021) 58-80, section 4.3 and Table 5, on BTC, ETH, SOL 4h bars (opened 23 Nov 2026 by the scout; backtest in
LABEL, opened at any p because the user asked to try weak ideas too). Fake money only.

On closed 4h Binance bars: if the bar's return is at least K standard deviations below zero -> long; at least K above
-> short. Enter at the next open, out one bar later at the following open (the paper holds one period, close to close).
The paper took the SD of the whole 2015-2018 sample (look-ahead); here it is the SD of the last SD_N 4h returns.
One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_jumprev.json       BTC, ETH, SOL
  state_fwd_jumprev_twin.json  control: random entry bars (TWIN_P per free bar), random side, same one-bar hold
  python3 fwd_jumprev.py"""
import random
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # the paper used BTC only; ETH and SOL added by me
K = 2.0                            # the paper's 2 sigma column (4h: +0.32% per trade before fees, 2015-2018 Bitstamp)
SD_N = 180                         # my choice: 30 days of 4h returns, so the SD uses only the past
TWIN_P = 1 / 17                    # my choice: the rule fired 3,172 times in ~54,000 coin-bars in the backtest
LABEL = ("ดีดกลับหลังแท่งกระโดด 4 ชม. BTC ETH SOL (De Nicola 2021): แท่งลงเกิน 2 SD ซื้อ ขึ้นเกิน 2 SD short ถือ 1 แท่ง "
         "(backtest 2017-2026 หลังหัก 0.35%/ข้าง BTC 1,165 ไม้ -0.75% p 0.900 ETH 1,201 ไม้ -0.74% p 0.811 "
         "SOL 806 ไม้ -0.54% p 0.025 ก่อนหักแค่ -0.05 ถึง +0.16% ต้นทุนกินหมด ตัวแฝดสุ่ม -0.66 ถึง -0.71%)")
ACCOUNTS = {"state_fwd_jumprev.json": ("rule", LABEL),
            "state_fwd_jumprev_twin.json": ("random", "ดีดกลับหลังแท่งกระโดด ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งสุ่ม ถือ 1 แท่งแบบเดียวกัน")}


def sig(b):
    """+1 / -1 / 0 per bar: the bar's return against K x SD of the last SD_N returns (that return included)."""
    r = [0.0] + [b[i]["c"] / b[i - 1]["c"] - 1 for i in range(1, len(b))]
    out = [0] * len(b)
    for i in range(SD_N, len(b)):
        w = r[i - SD_N + 1:i + 1]
        m = sum(w) / SD_N
        sd = (sum((v - m) ** 2 for v in w) / SD_N) ** 0.5
        out[i] = 1 if r[i] <= -K * sd else -1 if r[i] >= K * sd else 0
    return out


def trades(b, first=SD_N):
    """The backtest (the scout's /tmp/scout_0427.py calls this): list of dict(t, d, e, x), oldest first."""
    s, out = sig(b), []
    for i in range(first, len(b) - 2):
        if s[i]:
            out.append(dict(t=b[i + 1]["t"], d=s[i], e=b[i + 1]["o"], x=b[i + 2]["o"]))
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
    sg = sig(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "ถือครบ 1 แท่ง")
        if i < SD_N:
            continue
        d = sg[i] if mode == "rule" else (rng.choice((1, -1)) if rng.random() < TWIN_P else 0)
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = f"แท่ง {x['c'] / bars[i - 1]['c'] - 1:+.2%} เกิน {K:g} SD" if mode == "rule" else "สุ่มแท่ง สุ่มฝั่ง"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_jumprev fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
