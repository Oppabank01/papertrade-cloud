#!/usr/bin/env python3
"""Forward paper test of the pre-holiday drift for Bitcoin (Quantpedia, Cyril Dujava, 8 Sep 2025: buy the day before a
US holiday, hold through it, sell at the close of the day after; tested there on BTC futures / BITO 2018 to Jun 2025)
on BTC and ETH (opened 26 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak
ideas too). Fake money only.

On closed daily Binance bars (UTC), per coin: the bar of day D-1 closes and day D is a US federal holiday -> long at the
next open (= the D-1 close); out at the open two bars later (= the close of D+1). One position per coin, half the start
per coin, 0.35% per side.
  state_fwd_preholiday.json       BTC ETH
  state_fwd_preholiday_twin.json  control: random entry days (TWIN_P per free day), same two-day hold
  python3 fwd_preholiday.py"""
import datetime as dt
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
DAY = 86400 * 1000
SYMS = ["BTCUSDT", "ETHUSDT"]          # my choice: the paper's Bitcoin plus ETH
TWIN_P = 1 / 33                        # my choice: about the rule's rate (10 or 11 holidays a year)
# also mine: the holiday list is the 10 US federal holidays on their calendar date (not the observed weekday) plus
# Juneteenth from 2021, in place of the paper's "consensus U.S. calendar as per Time and Date"; no N-day-high filter
# (the paper's best variant; with N 5 BTC gave only 21 trades in 9 years); days are UTC
LABEL = ("ซื้อก่อนวันหยุดสหรัฐ (Quantpedia pre-holiday drift) BTC ETH รายวัน: ซื้อตอนปิดวันก่อนวันหยุดราชการสหรัฐ "
         "ขายตอนปิดวันหลังวันหยุด ไม้ละครึ่งทุน (backtest Binance รายวัน 2018 ถึง 24 พ.ย. 69 หลังหัก 0.35%/ข้าง "
         "BTC 93 ไม้ -0.42% ต่อไม้ มัธยฐาน -0.48% ชนะ 40% ก่อนหัก +0.28% ETH 93 ไม้ -0.65% ก่อนหัก +0.05% "
         "ถือ 2 วันทุกวัน -0.50/-0.47% ตั้งแต่ 2025 BTC 20 ไม้ -1.02% permutation 200 รอบ กริด 4 แบบ "
         "(ไม่กรอง หรือปิดสูงสุด 5/10/20 วัน) BTC p 0.433 ETH p 0.791)")
ACCOUNTS = {"state_fwd_preholiday.json": ("rule", LABEL),
            "state_fwd_preholiday_twin.json": ("random", "ซื้อก่อนวันหยุดสหรัฐ ตัวควบคุม: เข้าวันสุ่ม 1 ใน 33 วัน ถือ 2 วันแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def nth_wd(y, m, wd, n):
    """The n-th weekday wd (0 = Monday) of month m; n = -1 is the last one."""
    if n > 0:
        d = dt.date(y, m, 1)
        return d + dt.timedelta((wd - d.weekday()) % 7 + 7 * (n - 1))
    d = dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(1)
    return d - dt.timedelta((d.weekday() - wd) % 7)


def holidays(y):
    h = {dt.date(y, 1, 1), nth_wd(y, 1, 0, 3), nth_wd(y, 2, 0, 3), nth_wd(y, 5, 0, -1), dt.date(y, 7, 4),
         nth_wd(y, 9, 0, 1), nth_wd(y, 10, 0, 2), dt.date(y, 11, 11), nth_wd(y, 11, 3, 4), dt.date(y, 12, 25)}
    if y >= 2021:
        h.add(dt.date(y, 6, 19))
    return h


def day(t):
    return dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date()


def pre_holiday(t):
    d = day(t) + dt.timedelta(1)
    return d in holidays(d.year)


def trades(b):
    """The backtest (same trades as the scout's /tmp/scout_1902/bt.py trades(b, 0)): list of (entry t, entry, exit)."""
    out, i = [], 0
    while i + 3 < len(b):
        if pre_holiday(b[i]["t"]):
            out.append((b[i + 1]["t"], b[i + 1]["o"], b[i + 3]["o"]))
            i += 3
            continue
        i += 1
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, b, mode, rng):
    """b: daily bars of one coin, the last day may still be forming. Walks every closed day after s['seen'][sym]."""
    shut = [i for i in range(len(b)) if b[i]["closed"]]
    seen = s["seen"] if isinstance(s.get("seen"), dict) else {}
    s["seen"] = seen
    if sym not in seen:
        seen[sym] = b[shut[-1]]["t"]
        return
    for i in shut:
        if b[i]["t"] <= seen[sym] or i + 1 >= len(b):
            continue
        seen[sym] = b[i]["t"]
        p = s["pos"].get(sym)
        if p:
            if b[i]["t"] >= p["entry_t"] + DAY:          # the holiday bar and the day after have closed
                close(s, sym, b[i + 1]["o"], b[i + 1]["t"], "ครบวันหลังวันหยุด" if mode == "rule" else "ครบ 2 วัน")
            continue
        if not (pre_holiday(b[i]["t"]) if mode == "rule" else rng.random() < TWIN_P):
            continue
        e, t = b[i + 1]["o"], b[i + 1]["t"]
        usd = min(s["start_usd"] / len(SYMS), s["cash"] / (1 + COST))   # my choice: take what cash is left after losses
        if usd < 0.01:
            continue
        s["cash"] -= usd + usd * COST
        why = f"พรุ่งนี้วันหยุดสหรัฐ {day(t).isoformat()}" if mode == "rule" else "สุ่มวัน"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=t, t=iso(t), why=why)
        s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = b[-1]["c"]


def main():
    rng = random.Random()
    bars = {}
    for sym in SYMS:
        try:
            bars[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_preholiday fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        for sym, b in bars.items():
            step(s, sym, b, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
