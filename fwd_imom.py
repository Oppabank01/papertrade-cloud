#!/usr/bin/env python3
"""Forward paper test of intraday momentum (Gao, Han, Li & Zhou 2018 for stocks; crypto versions such as Wen et al.
2022: the return of the day so far predicts the last stretch of the day) on BTC, ETH, SOL (opened 25 Nov 2026 by the
scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too). Fake money only.

On 1h Binance bars: the UTC day's return from the 00:00 open to the 22:00 bar's close (23:00 UTC) above +THR -> long
the 23:00 bar, below -THR -> short it; enter at its open, exit at the next bar's open (00:00 UTC). No stop (one hour is
the time stop). One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_imom.json       BTC, ETH, SOL
  state_fwd_imom_twin.json  control: random entry hours (TWIN_P per free hour), random side, same 1h hold
  python3 fwd_imom.py"""
import random
from datetime import datetime, timezone
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
H = 3600 * 1000
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the three coins every scout test uses
THR = 0.02                     # my choice: best of 4 variants tried (0 or 2%, long-only or both sides), see LABEL
TWIN_P = 1 / 48                # my choice: about one random hour every two days, near the rule's ~0.4 trades a day
LABEL = ("โมเมนตัมระหว่างวัน 1 ชม. BTC ETH SOL (Gao et al. 2018, Wen et al. 2022): ผลตอบแทนวัน UTC ตั้งแต่ 00:00 ถึง 23:00 "
         "เกิน +2% long ชั่วโมงสุดท้าย (23:00-24:00 UTC = 06:00-07:00 ไทย) ต่ำกว่า -2% short "
         "(backtest Binance 1 ชม. 2017-2026 หลังหัก 0.35%/ข้าง BTC 1,270 ไม้ -0.62% ETH 1,661 ไม้ -0.61% SOL 1,390 ไม้ -0.63% "
         "ต่อไม้ ก่อนหัก ราว +0.08/+0.10/+0.07% ตัวแฝดชั่วโมงสุ่ม -0.69 ถึง -0.73% permutation ค้น 4 แบบ p 0.005/0.005/0.025 "
         "แพทเทิร์นมีจริงแต่ต้นทุนไปกลับ 0.7% ใหญ่กว่าราว 8 เท่า และอ่อนลงตั้งแต่ปี 2023)")
ACCOUNTS = {"state_fwd_imom.json": ("rule", LABEL),
            "state_fwd_imom_twin.json": ("random", "โมเมนตัมระหว่างวันตัวควบคุม: ชั่วโมงสุ่ม ฝั่งสุ่ม ถือ 1 ชม. แบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def hour(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).hour


def signal(b, i):
    """Side for the bar after b[i] (+1, -1, 0): b[i] must be the closed 22:00 UTC bar and b[i-22] the same day's 00:00."""
    if hour(b[i]["t"]) != 22 or i < 22 or b[i - 22]["t"] != b[i]["t"] - 22 * H:
        return 0
    r = b[i]["c"] / b[i - 22]["o"] - 1
    return 1 if r > THR else -1 if r < -THR else 0


def trades(b, first=1):
    """The backtest: list of (entry_t, entry_px, exit_px, side), oldest first."""
    out = []
    for i in range(first, len(b) - 2):
        d = signal(b, i)
        if d and b[i + 1]["t"] == b[i]["t"] + H and b[i + 2]["t"] == b[i + 1]["t"] + H:
            out.append((b[i + 1]["t"], b[i + 1]["o"], b[i + 2]["o"], d))
    return out


def close(s, sym, px, t, why):
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
        nx = bars[i + 1]
        p = s["pos"].get(sym)
        if p and nx["t"] >= p["exit_t"]:
            close(s, sym, nx["o"], nx["t"], "ครบ 1 ชม.")
        if sym in s["pos"]:
            continue
        if mode == "rule":
            d = signal(bars, i) if nx["t"] == x["t"] + H else 0
        else:
            d = rng.choice((1, -1)) if rng.random() < TWIN_P else 0
        usd = s["start_usd"] / 3
        if not d or (d > 0 and s["cash"] < usd * (1 + COST)):
            continue
        e = nx["o"]
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = ("วันนี้ขึ้นเกิน 2% long ชั่วโมงสุดท้าย" if d > 0 else "วันนี้ลงเกิน 2% short ชั่วโมงสุดท้าย") if mode == "rule" else "สุ่มชั่วโมง สุ่มฝั่ง"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=nx["t"], exit_t=nx["t"] + H, t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_imom fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
