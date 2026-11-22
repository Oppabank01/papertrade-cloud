#!/usr/bin/env python3
"""Forward paper test of an hour-of-week seasonality window on BTC, ETH, SOL (opened 23 Nov 2026 from a batch of simple
bar ideas; the window was picked in-sample on bars before 2024 and judged on 2024+, numbers in LABEL). Fake money only.

On 4h Binance bars: slot = 4h bar of the week counted from Monday 00:00 UTC (0..41). When the next bar is slot START,
enter DIR at its open and close at the close of the LEN-th bar. One position per coin, one third of the start per coin,
0.35% per side. No stop (the window length is the time stop).
  state_fwd_weekend.json       BTC, ETH, SOL
  state_fwd_weekend_twin.json  control: random entry bars (1 in 42), same direction and length
  python3 fwd_weekend.py"""
import random
from byttrade import iso, load, save, fetch, H4, DAY

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
# searched in-sample (bars before 2024, BTC+ETH+SOL pooled): start slot 0..41 x length 1/2/3/6/12/18 bars x long/short
# = 504 windows; the named hypothesis "long Friday close (Sat 00:00 UTC, slot 30) to Monday close (18 bars)" is one of them
LENS = (1, 2, 3, 6, 12, 18)
START, LEN, DIR = 26, 18, 1        # chosen: best pooled in-sample (pre-2024) mean per trade after costs = long Fri 08:00 UTC to Mon 08:00 UTC
TWIN_P = 1 / 42                    # one random entry a week on average, like the rule
LABEL = ("ช่วงเวลาในสัปดาห์ BTC ETH SOL: long ศุกร์ 08:00 UTC (15:00 ไทย) ถึงจันทร์ 08:00 UTC ถือ 72 ชม. เลือกจาก 504 ช่วงก่อนปี 2024 "
         "(backtest 2017-2026 หลังหัก 1,293 ไม้ เฉลี่ย +0.24% มัธยฐาน -0.18% p 0.26 ตก ปี 2024+ 450 ไม้ -0.43%)")
ACCOUNTS = {"state_fwd_weekend.json": ("rule", LABEL),
            "state_fwd_weekend_twin.json": ("random", "ช่วงเวลาในสัปดาห์ ตัวควบคุม: เข้าแท่งสุ่ม ทิศและความยาวเดียวกัน")}


def slot(t):
    return ((t // DAY + 3) % 7) * 6 + (t % DAY) // H4      # 1970-01-01 was a Thursday; Monday 00:00 UTC = 0


def trades(b, start=START, ln=LEN, d=DIR, first=1):
    """The backtest: list of dict(t, d, e, x) on closed bars, oldest first."""
    out, i, n = [], first, len(b)
    while i < n - 1:
        if slot(b[i + 1]["t"]) != start:
            i += 1
            continue
        e, t0, j = b[i + 1]["o"], b[i + 1]["t"], i + 1
        while j < n and b[j]["t"] < t0 + (ln - 1) * H4:
            j += 1
        if j >= n:
            break
        out.append(dict(t=t0, d=d, e=e, x=b[j]["c"]))
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
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["until"]:
            close(s, sym, x["c"], x["t"] + H4, f"ครบ {LEN} แท่ง")
            exited = True
        if sym in s["pos"] or exited:
            continue
        if not (slot(bars[i + 1]["t"]) == START if mode == "rule" else rng.random() < TWIN_P):
            continue
        d, e, t0, usd = DIR, bars[i + 1]["o"], bars[i + 1]["t"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = f"ช่วงเวลา slot {START} ยาว {LEN} แท่ง" if mode == "rule" else "สุ่มแท่ง"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             until=t0 + (LEN - 1) * H4, entry_t=t0, t=iso(t0), why=why)
        s["log"].append(dict(kind="buy", t=iso(t0), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_weekend fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
