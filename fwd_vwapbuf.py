#!/usr/bin/env python3
"""Forward paper test of the intraday "VWAP trend with a volatility buffer" (dantecoderr/vwap-nq on GitHub, Nov 2026,
built on Zarattini & Aziz 2023, SSRN 4631351: on NQ futures +$334k a contract 2019-2024 and +$23k in held-out 2025
after costs) on BTC, ETH, SOL (opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked
to try weak ideas too). Fake money only.

Session = the UTC day. byttrade.fetch gives no volume, so the reference line is the session TWAP of (h+l+c)/3 (the
backtest shows TWAP and VWAP give nearly the same trades and results on these coins). On closed 15m Binance bars from
the one closing 00:30 UTC: close above ref x (1 + buf) -> long at the next open, below ref x (1 - buf) -> short (or flip),
else hold. Flat at the open of the next day's first bar. buf = K x stdev of the previous 14 daily close-to-close returns.
No stop (the repo found stops did not help). One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_vwapbuf.json       BTC, ETH, SOL
  state_fwd_vwapbuf_twin.json  control: random entry bars (TWIN_P per free bar), random side, same flat-at-day-end
  python3 fwd_vwapbuf.py"""
import random
import statistics as st
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice; the repo trades NQ only
M15, DAY = 15 * 60 * 1000, 86400 * 1000
K, NDAYS = 0.15, 14            # from the repo; no search here
FIRST = M15                    # my choice: start one bar after the open (the repo waits 30 min on 5m bars)
TWIN_P = 1 / 30                # my choice: about one random trade a day per coin, held to the day end (rule: ~2.6 a day)
LABEL = ("VWAP trend มีบัฟเฟอร์ 15 นาที BTC ETH SOL (dantecoderr/vwap-nq, Zarattini 2023) ใช้ TWAP แทน VWAP เพราะไม่มีวอลุ่ม: "
         "ปิดเหนือเส้นเฉลี่ยของวัน + 0.15 เท่าของ std รายวัน 14 วัน long ต่ำกว่า short ปิดทุกสิ้นวัน UTC "
         "(backtest Binance 15 นาที 2017-2026 แบบ TWAP หลังหัก 0.35%/ข้าง BTC 8,583 ไม้ -0.65% ETH 8,436 ไม้ -0.56% "
         "SOL 6,496 ไม้ -0.64% ต่อไม้ ก่อนหัก +0.05/+0.14/+0.06% ติดลบทุกปี แบบ VWAP ใกล้กัน permutation 3 ปีล่าสุด "
         "กริด 4 แบบ 200 รอบ p 0.184/0.005/0.234 ราวสองไม้ครึ่งต่อวันต้นทุนจึงกินหมด)")
ACCOUNTS = {"state_fwd_vwapbuf.json": ("rule", LABEL),
            "state_fwd_vwapbuf_twin.json": ("random", "VWAP บัฟเฟอร์ ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งสุ่ม ปิดสิ้นวันแบบเดียวกัน")}


def fetch_iv(sym, iv):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def buffers(daily):
    """day start (ms) -> K x stdev of the NDAYS daily returns that closed before that day."""
    c = [(x["t"], x["c"]) for x in daily if x["closed"]]
    out = {}
    for i in range(NDAYS, len(c)):
        rs = [c[j][1] / c[j - 1][1] - 1 for j in range(i - NDAYS + 1, i + 1)]
        out[c[i][0] + DAY] = K * st.pstdev(rs)
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, daily, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    buf, ref, cur, sp, n = buffers(daily), [], None, 0.0, 0
    for x in bars:                                   # session TWAP up to and including each bar
        d = x["t"] // DAY
        if d != cur:
            cur, sp, n = d, 0.0, 0
        sp += (x["h"] + x["l"] + x["c"]) / 3
        n += 1
        ref.append(sp / n)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        nx, day0 = bars[i + 1], x["t"] // DAY * DAY
        if nx["t"] // DAY * DAY != day0:
            if sym in s["pos"]:
                close(s, sym, nx["o"], nx["t"], "จบวัน UTC")
            continue
        b = buf.get(day0)
        if b is None or x["t"] - day0 < FIRST:
            continue
        p = s["pos"].get(sym)
        if mode == "rule":
            d = 1 if x["c"] > ref[i] * (1 + b) else -1 if x["c"] < ref[i] * (1 - b) else 0
            why = "ปิดเหนือเส้นเฉลี่ยของวันเกินบัฟเฟอร์" if d > 0 else "ปิดใต้เส้นเฉลี่ยของวันเกินบัฟเฟอร์"
        else:
            d = rng.choice((1, -1)) if not p and rng.random() < TWIN_P else 0
            why = "สุ่มแท่ง สุ่มฝั่ง"
        if not d or (p and p["d"] == d):
            continue
        if p:
            close(s, sym, nx["o"], nx["t"], "กลับฝั่ง")
        e, usd = nx["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=nx["t"], t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = (fetch_iv(sym, "15m"), fetch_iv(sym, "1d"))
        except Exception as e:
            print("fwd_vwapbuf fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, (bars, daily) in cache.items():
            step(s, sym, bars, daily, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
