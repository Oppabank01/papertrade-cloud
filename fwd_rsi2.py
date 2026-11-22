#!/usr/bin/env python3
"""Forward paper test of Connors' RSI(2) daily mean reversion on BTC, ETH, SOL (opened 23 Nov 2026 from a batch of simple
bar ideas; backtest in LABEL, opened at any p because the user asked to try everything). Fake money only.

On closed daily Binance bars: close above SMA200 and RSI2 below X -> long at the next open, out at the next open after a
close above SMA5. Mirror: close below SMA200 and RSI2 above 100-X -> short, out after a close below SMA5. Time stop: out at
the next open after the MAXH-th day. No price stop (Connors' rule has none; the time stop caps the hold). One position per
coin, one third of the start per coin, 0.35% per side.
  state_fwd_rsi2.json       BTC, ETH, SOL
  state_fwd_rsi2_twin.json  control: random entry days (TWIN_P) on the SMA200 side, same exits
  python3 fwd_rsi2.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
# grid tried in-sample (bars before 2024, BTC+ETH+SOL pooled): X 5/10/15 x max hold 5/10 days = 6 settings
GRID = [(x, h) for x in (5, 10, 15) for h in (5, 10)]
X, MAXH = 15, 5                    # chosen: best pooled in-sample (pre-2024) mean per trade after costs
TWIN_P = 1 / 13                    # about the rule's signal rate (562 trades in ~7,500 free coin-days)
LABEL = ("RSI2 Connors รายวัน BTC ETH SOL: เหนือ SMA200 และ RSI2 ต่ำกว่า 15 long ใต้ SMA200 และเกิน 85 short ออกเมื่อปิดข้าม SMA5 หรือครบ 5 วัน "
         "(backtest 2017-2026 หลังหัก 562 ไม้ เฉลี่ย -0.61% มัธยฐาน +0.94% ชนะ 59% p 0.60 ตก ปี 2024+ 210 ไม้ -1.02%)")
ACCOUNTS = {"state_fwd_rsi2.json": ("rule", LABEL),
            "state_fwd_rsi2_twin.json": ("random", "RSI2 ตัวควบคุม: เข้าวันสุ่ม ฝั่งตาม SMA200 ออกแบบเดียวกัน")}
DAY = 86400 * 1000


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ind(b):
    c, n = [x["c"] for x in b], len(b)
    s200, s5, rsi, a, z, ag, al = [None] * n, [None] * n, [None] * n, 0.0, 0.0, 0.0, 0.0
    for i in range(n):
        a += c[i]; z += c[i]
        if i >= 200:
            a -= c[i - 200]
        if i >= 5:
            z -= c[i - 5]
        if i >= 199:
            s200[i] = a / 200
        if i >= 4:
            s5[i] = z / 5
        if i:
            d = c[i] - c[i - 1]
            g, l = max(d, 0), max(-d, 0)
            if i <= 2:
                ag += g / 2; al += l / 2
            else:
                ag = (ag + g) / 2; al = (al + l) / 2
            if i >= 2:
                rsi[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return s200, s5, rsi


def signal(x, s200, rsi, lim=X):
    if s200 is None or rsi is None:
        return 0
    if x["c"] > s200 and rsi < lim:
        return 1
    if x["c"] < s200 and rsi > 100 - lim:
        return -1
    return 0


def out_now(x, s5, d, entry_t, maxh=MAXH):
    return (s5 is not None and (x["c"] - s5) * d > 0) or x["t"] >= entry_t + (maxh - 1) * DAY


def trades(b, lim=X, maxh=MAXH, first=200, ind_=None):
    """The backtest: list of dict(t, d, e, x) on closed bars, oldest first. Entries and exits at the next open."""
    s200, s5, rsi = ind_ or ind(b)
    out, i, n = [], first, len(b)
    while i < n - 1:
        d = signal(b[i], s200[i], rsi[i], lim)
        if not d:
            i += 1
            continue
        e, t0, j, px = b[i + 1]["o"], b[i + 1]["t"], i + 1, None
        while j < n - 1:
            if out_now(b[j], s5[j], d, t0, maxh):
                px = b[j + 1]["o"]
                break
            j += 1
        if px is None:
            break
        out.append(dict(t=t0, d=d, e=e, x=px))
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
    s200, s5, rsi = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"] and out_now(x, s5[i], p["d"], p["entry_t"]):
            timed = not (s5[i] is not None and (x["c"] - s5[i]) * p["d"] > 0)
            close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], f"ครบ {MAXH} วัน" if timed else "ปิดข้าม SMA5")
            exited = True
        if sym in s["pos"] or exited:
            continue
        if mode == "rule":
            d = signal(x, s200[i], rsi[i])
        else:
            d = (1 if x["c"] > s200[i] else -1) if s200[i] and rng.random() < TWIN_P else 0
        if not d:
            continue
        e, t0, usd = bars[i + 1]["o"], bars[i + 1]["t"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = f"RSI2 {rsi[i]:.0f} {'เหนือ' if d > 0 else 'ใต้'} SMA200" if mode == "rule" else "สุ่มวัน ฝั่งตาม SMA200"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=t0, t=iso(t0), why=why)
        s["log"].append(dict(kind="buy", t=iso(t0), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_rsi2 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
