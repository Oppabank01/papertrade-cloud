#!/usr/bin/env python3
"""Forward paper test of an odd idea from an X post (machao_stock, 26 Oct 2026: "buy gold at the round number below"),
opened 23 Nov 2026 by the scout on PAXG (tokenized gold on Binance). The backtest lost and did worse than random entries
(LABEL); opened anyway because the user asked to try weak and odd ideas too. Fake money only.

After each closed daily bar a resting buy limit sits at L = the round STEP level at or below that close. On the next
daily bar, if its low reaches L, the order fills at min(open, L) (an open already below L fills at the open). Out at the
close of the HOLD-th day counting the fill day. No stop. Long only, one position, the whole account, 0.35% per side.
  state_fwd_goldround.json       PAXG
  state_fwd_goldround_twin.json  control: buy at the open of random days (TWIN_P per free day), same hold
  python3 fwd_goldround.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                      # per side, as every account here
SYMS = ["PAXGUSDT"]
DAY = 6 * H4
# grid tried (PAXG daily 2020-08 to 2026-11, whole sample, no split): STEP 50/100 x HOLD 1/3/5 = 6 settings, all lost
STEP = 100                         # chosen by me: the post's levels are $100 apart (4,000 and 3,965 near it)
HOLD = 5                           # chosen by me: least bad of the grid; the post gives no exit
TWIN_P = 1 / 8                     # the rule traded 197 times in ~1,300 free days
LABEL = ("ทองแตะเลขกลม (PAXG รายวัน): ตั้งซื้อที่ระดับ $100 ใต้ราคาปิด ถ้าวันถัดไปลงแตะก็ได้ของ ถือ 5 วัน ไม่มี stop "
         "(backtest 2020-2026 หลังหัก 0.35%/ข้าง 197 ไม้ เฉลี่ย -0.43% มัธยฐาน -0.38% ชนะ 40% แพ้ซื้อวันสุ่ม -0.27% permutation p 0.23 ตก)")
ACCOUNTS = {"state_fwd_goldround.json": ("rule", LABEL),
            "state_fwd_goldround_twin.json": ("random", "ทองแตะเลขกลม ตัวควบคุม: ซื้อเปิดวันสุ่ม ถือ 5 วันแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def level(prev_close, step=STEP):
    return (prev_close // step) * step


def touched(b, i, step=STEP):
    """fill price of the limit order on bar i, or None"""
    if i < 1:
        return None
    L = level(b[i - 1]["c"], step)
    return min(b[i]["o"], L) if b[i]["l"] <= L < b[i - 1]["c"] else None


def trades(b, step=STEP, hold=HOLD, first=1):
    """The backtest (same as the scout's /tmp/scout_0240.py rn_trades): list of dict(t, e, x, hold), oldest first."""
    out, i, n = [], first, len(b)
    while i < n - hold:
        e = touched(b, i, step)
        if e is None:
            i += 1
            continue
        out.append(dict(t=b[i]["t"], e=e, x=b[i + hold - 1]["c"], hold=hold))
        i += hold
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
            close(s, sym, x["c"], x["t"] + DAY, f"ครบ {HOLD} วัน")
            exited = True
        if sym in s["pos"] or exited:
            continue
        if mode == "rule":
            e = touched(bars, i)
            why = f"แตะ ${level(bars[i - 1]['c']):,.0f}" if e is not None else ""
        else:   # the twin decides at the close before and buys this day's open
            e, why = (x["o"], "สุ่มวัน") if rng.random() < TWIN_P else (None, "")
        if e is None:
            continue
        usd = s["cash"] / (1 + COST)   # whole account, as byttrade.open_pos
        if usd <= 0:
            continue
        s["cash"] += -usd - usd * COST
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, until=x["t"] + (HOLD - 1) * DAY,
                             entry_t=x["t"], t=iso(x["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(x["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
        if HOLD == 1:
            close(s, sym, x["c"], x["t"] + DAY, "ครบ 1 วัน")
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_goldround fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
