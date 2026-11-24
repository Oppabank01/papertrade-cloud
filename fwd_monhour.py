#!/usr/bin/env python3
"""Forward paper test of the Monday hour windows in Aalipour, Mehdian & Rezvanian (2026, Finance Research Letters 110634,
"Are day-of-the-week effects in cryptocurrencies real? Intraday evidence"; through a secondary write-up: the BTC Monday
effect sits around 06:00 and 18:00 UTC) on BTC, ETH (opened 24 Nov 2026 by the scout; backtest in LABEL, opened at any
p because the user asked to try weak ideas too). Fake money only.

On 1h Binance bars: when the next bar is a Monday bar opening at one of START_HS UTC, buy at its open; sell at the open
of the bar HOLD hours later. Long only, one position per coin, one half of the start per coin, 0.35% per side. No stop
(the hour is the time stop).
  state_fwd_monhour.json       BTC, ETH
  state_fwd_monhour_twin.json  control: random entry hours (TWIN_P per free hour), same 1h hold
  python3 fwd_monhour.py"""
import random
from datetime import datetime, timezone
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
H = 3600 * 1000
SYMS = ["BTCUSDT", "ETHUSDT"]  # the write-up names BTC and ETH windows; only the BTC hours are used, for both
WEEKDAY, START_HS, HOLD = 0, (6, 18), 1   # Monday, 06:00 and 18:00 UTC; the 1h hold is my reading of "around"
TWIN_P = 1 / 84                # my choice: two random hours a week on average, like the rule
LABEL = ("ชั่วโมงวันจันทร์ 06:00 และ 18:00 UTC (13:00 และ 01:00 คืนวันอังคาร เวลาไทย) BTC ETH ตาม Aalipour et al. 2026 "
         "ซื้อเปิดแท่งถือ 1 ชม. (backtest Binance 1 ชม. 2017-2026 ก่อนหัก BTC +0.029% ETH -0.001% ต่อไม้ ชั่วโมงสุ่ม +0.038/+0.053% "
         "หลังหัก 0.35%/ข้าง BTC 967 ไม้ -0.67% ETH 967 ไม้ -0.70% permutation 200 รอบ p 0.209/0.602 ปี 2024+ ก่อนหักติดลบทั้งคู่ "
         "ไม่ต่างจากชั่วโมงสุ่ม คาดว่าแพ้ต้นทุนราว 0.7% ต่อไม้)")
ACCOUNTS = {"state_fwd_monhour.json": ("rule", LABEL),
            "state_fwd_monhour_twin.json": ("random", "ชั่วโมงวันจันทร์ตัวควบคุม: เข้าชั่วโมงสุ่ม ถือ 1 ชม. แบบเดียวกัน")}


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


def is_start(t):
    d = datetime.fromtimestamp(t / 1000, timezone.utc)
    return d.weekday() == WEEKDAY and d.hour in START_HS


def trades(b, first=1):
    """The backtest: list of (entry_t, entry_px, exit_t, exit_px), oldest first."""
    out, i = [], first
    while i < len(b) - 1:
        if not is_start(b[i + 1]["t"]):
            i += 1
            continue
        e_t, e, j = b[i + 1]["t"], b[i + 1]["o"], i + 1
        while j < len(b) - 1 and b[j + 1]["t"] < e_t + HOLD * H:
            j += 1
        if j >= len(b) - 1:
            break
        out.append((e_t, e, b[j + 1]["t"], b[j + 1]["o"]))
        i = j
    return out


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px * (1 - COST)
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


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
            close(s, sym, nx["o"], nx["t"], f"ครบ {HOLD} ชม.")
        if sym in s["pos"]:
            continue
        go = is_start(nx["t"]) if mode == "rule" else rng.random() < TWIN_P
        usd = s["start_usd"] / len(SYMS)
        if not go or s["cash"] < usd * (1 + COST):
            continue
        e = nx["o"]
        s["cash"] -= usd * (1 + COST)
        why = "เปิดแท่งวันจันทร์ %02d:00 UTC" % hour(nx["t"]) if mode == "rule" else "สุ่มชั่วโมง"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=nx["t"],
                             exit_t=nx["t"] + HOLD * H, t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_monhour fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
