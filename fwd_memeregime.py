#!/usr/bin/env python3
"""Forward paper test of the closest mechanical version of 6vintik9's post (X, 19 Nov 2026: a Grok trading bot left
overnight "monitoring 24 meme coins, scanning market conditions every 15 minutes and switching between" modes; the rest of
the post is not readable and gives no rules), opened 24 Nov 2026 by the scout. The switch is the regime switcher already
running on daily BTC ETH SOL bars (fwd_regime.py, anna-johney/momentum-mean-reversion-regime-switcher) moved to 15m bars
of Binance meme coins. Backtest in LABEL; opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 15m Binance bars: efficiency ratio ER = |close - close N bars ago| / sum of |close changes| over those N bars.
ER >= ER_TH -> momentum: long if close > close N bars ago, short if below. ER < ER_TH -> mean reversion: z = (close -
mean of the last N closes) / their population SD; |z| >= Z_TH -> the opposite side of z, else flat. When the wanted side
differs from the held one, close and/or open at the next open. No stop, no target.
One position per coin, one quarter of the start per coin, 0.35% per side.
  state_fwd_memeregime.json       DOGE, PEPE, WIF, BONK
  state_fwd_memeregime_twin.json  control: each bar with chance TWIN_P picks a random side (long, short or flat)
  python3 fwd_memeregime.py"""
import random
import statistics as st
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                                        # per side, as every account here
SYMS = ["DOGEUSDT", "PEPEUSDT", "WIFUSDT", "BONKUSDT"]   # my choice: the four biggest meme coins on Binance spot (post: 24 coins)
IV = "15m"                                           # the post's "every 15 minutes"
N, ER_TH, Z_TH = 20, 0.35, 0.5                       # the repo's fixed rules, as fwd_regime.py
TWIN_P = 0.4                                         # my choice: gives about the rule's trade count (DOGE 7,177 trades in 35,039 bars)
LABEL = ("regime switcher เหรียญมีม 15 นาที DOGE PEPE WIF BONK (ใกล้โพสต์บอท Grok ของ 6vintik9 ที่สลับโหมดทุก 15 นาที): "
         "ER 20 แท่ง 0.35 ขึ้นไปตามโมเมนตัม ต่ำกว่านั้นสวน z-score 0.5 long+short (backtest Binance 15 นาที 365 วันถึง 24 พ.ย. 69 "
         "หลังหัก 0.35%/ข้าง DOGE 7,177 ไม้ -0.69% PEPE 7,496 ไม้ -0.66% WIF 7,340 ไม้ -0.67% BONK 7,298 ไม้ -0.69% ต่อไม้ "
         "ก่อนหัก +0.01 ถึง +0.04% ชนะ 6-14% permutation 200 รอบ p 0.085/0.010/0.035/0.149 สัญญาณมีจริงเล็กน้อยแต่ต้นทุนกินหมด)")
ACCOUNTS = {"state_fwd_memeregime.json": ("rule", LABEL),
            "state_fwd_memeregime_twin.json": ("random", "regime switcher เหรียญมีม 15 นาที ตัวควบคุม: ทุกแท่งมีโอกาสสุ่มฝั่งใหม่ (long short หรือว่าง)")}


def fetch_iv(sym, iv=IV):
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


def trades(b, first=N):
    """The backtest: list of dict(t, d, e, x), oldest first."""
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
        usd = s["start_usd"] / 4
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
            cache[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_memeregime fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
