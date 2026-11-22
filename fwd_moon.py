#!/usr/bin/env python3
"""ODD IDEA, on purpose: forward paper test of a moon-phase rule on daily BTC, ETH, SOL bars (opened 23 Nov 2026 from a
batch of simple bar ideas; there is no reason this should work, backtest in LABEL). Fake money only.

Moon phase from the mean synodic month (29.530588853 days) counted from the new moon of 2000-01-06 18:14 UTC (accurate to
about half a day, good enough for daily bars). Waxing = new moon to full moon. At each daily open the wanted side is DIR
while waxing and -DIR while waning (MODE "long": the short half stays flat). When the wanted side changes, the old
position closes and the new one opens at that open. No stop; the phase change is the exit. One position per coin, one
third of the start per coin, 0.35% per side.
  state_fwd_moon.json       BTC, ETH, SOL
  state_fwd_moon_twin.json  control: random entry days (1 in 15), long (random side if MODE "ls"), out at the open 15 days later
  python3 fwd_moon.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
DAY = 86400 * 1000
REF, SYN = 947182440000, 29.530588853 * DAY     # new moon 2000-01-06 18:14 UTC, mean synodic month
# grid tried in-sample (bars before 2024, BTC+ETH+SOL pooled): DIR long/short while waxing x MODE long+short/long only = 4
GRID = [(d, m) for d in (1, -1) for m in ("ls", "long")]
DIR, MODE = -1, "long"             # chosen: best pooled in-sample (pre-2024) mean per trade after costs = long while waning only
TWIN_P, TWIN_HOLD = 1 / 15, 15     # about half a synodic month, like the rule's hold
LABEL = ("ไอเดียแปลก ข้างขึ้นข้างแรม BTC ETH SOL: ถือ long เฉพาะข้างแรม (วันเพ็ญถึงเดือนดับ) ข้างขึ้นไม่ถือ "
         "(backtest 2017-2026 หลังหัก 308 ไม้ เฉลี่ย +3.07% มัธยฐาน -0.72% p 0.06 ปี 2024+ 105 ไม้ -1.20% ตก)")
ACCOUNTS = {"state_fwd_moon.json": ("rule", LABEL),
            "state_fwd_moon_twin.json": ("random", "ข้างขึ้นข้างแรม ตัวควบคุม: long วันสุ่ม ถือ 15 วัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def waxing(t):
    return ((t - REF) / SYN) % 1 < 0.5


def want(t, d=DIR, mode=MODE):
    w = d if waxing(t) else -d
    return w if mode == "ls" or w > 0 else 0


def trades(b, d=DIR, mode=MODE, first=1):
    """The backtest: list of dict(t, d, e, x) on closed bars, oldest first; decisions at closed bar i, fills at b[i+1] open."""
    out, cur = [], None
    for i in range(first, len(b) - 1):
        w, nx = want(b[i + 1]["t"], d, mode), b[i + 1]
        if cur and cur["d"] != w:
            out.append(dict(cur, x=nx["o"]))
            cur = None
        if not cur and w:
            cur = dict(t=nx["t"], d=w, e=nx["o"])
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
        nx, p = bars[i + 1], s["pos"].get(sym)
        if mode == "rule":
            w = want(nx["t"])
            if p and p["d"] != w:
                close(s, sym, nx["o"], nx["t"], "ข้างแรม" if waxing(nx["t"]) is False else "ข้างขึ้น")
            if sym in s["pos"] or not w:
                continue
            why = f"{'ข้างขึ้น' if waxing(nx['t']) else 'ข้างแรม'} ฝั่ง {'long' if w > 0 else 'short'}"
        else:
            if p and nx["t"] >= p["entry_t"] + TWIN_HOLD * DAY:
                close(s, sym, nx["o"], nx["t"], f"ครบ {TWIN_HOLD} วัน")
                continue
            if p or rng.random() >= TWIN_P:
                continue
            w, why = (rng.choice((1, -1)) if MODE == "ls" else 1), "สุ่มวัน"
        e, usd = nx["o"], s["start_usd"] / 3
        if w > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if w > 0 else usd) - usd * COST
        s["pos"][sym] = dict(side="long" if w > 0 else "short", d=w, qty=w * usd / e, entry=e, last=e, usd=usd,
                             entry_t=nx["t"], t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_moon fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
