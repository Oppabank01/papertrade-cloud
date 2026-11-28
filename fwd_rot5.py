#!/usr/bin/env python3
"""Forward paper test of the coin rotation in walidplayx-debug/crypto-bot (GitHub, 25 Nov 2026; settings frozen by the
author from 240 tried on data to 2024-07-01, their hidden test since then +136% vs buy-and-hold of the five -29%). Opened
28 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

Every 3rd day at the 00:00 UTC daily open (days where (t // DAY) % 3 == 0, my choice of anchor): rank BTC ETH SOL BNB DOGE
by open / open 30 days earlier - 1; long the top 2 if that is > 0, short the weakest if it is < 0; hold to the next review.
Each new position is a third of equity at that open; a coin that keeps its side is not traded (no cost). No stop, no
leverage. 0.35% per side (the author used 0.05% fee + 0.03% slippage + funding on perps).
  state_fwd_rot5.json        the rule
  state_fwd_rot5_twin.json   control: the same number of longs and shorts at each review, coins picked at random
  python3 fwd_rot5.py"""
import random, time
import byttrade as B
from byttrade import iso, load, save

COST, DAY = 0.0035, 86400 * 1000
COINS = "BTC ETH SOL BNB DOGE".split()           # from the repo
LOOK, HOLD, TOP = 30, 3, 2                       # from the repo's RESULTS.md (30 days, every 3 days, top 2 long, weakest short)
ANCHOR = 0                                       # my choice: review days have (t // DAY) % 3 == 0 (anchors 1 and 2 tested: +0.50/+0.48%)
LABEL = ("หมุน 5 เหรียญ (walidplayx-debug/crypto-bot): ทุก 3 วันจัดอันดับ BTC ETH SOL BNB DOGE ตามผลตอบแทน 30 วัน "
         "long 2 อันดับแรกถ้าบวก short อันดับท้ายถ้าลบ ช่องละ 1 ใน 3 "
         "(backtest Binance รายวัน ก.ย. 2017 ถึง 27 พ.ย. 69 หลังหัก 0.35%/ข้าง 1,119 รอบ +0.55% ต่อรอบ มัธยฐาน +0.11% "
         "ชนะ 52% ถือเท่ากันทั้ง 5 เหรียญ +0.78% ตัวแฝดเลือกสุ่มจำนวนเท่ากัน +0.23% ปี 2024 +0.05% 2025 +0.12% 2026 0.00% "
         "ตั้งแต่ 1 ก.ค. 2024 +37% เทียบถือทั้ง 5 -28% permutation 200 รอบกริด 6 แบบก่อนหัก p 0.005)")
ACCOUNTS = {"state_fwd_rot5.json": ("rule", LABEL),
            "state_fwd_rot5_twin.json": ("random", "หมุน 5 เหรียญ ตัวควบคุม: ทุก 3 วัน long/short จำนวนเท่ากฎ แต่สุ่มเหรียญ")}


def fetch_daily(sym):   # as fwd_xsmom.fetch_daily
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=1d")
    try:
        return B.fetch(sym)
    finally:
        B.URL = old


def reviews_after(t0, px):
    return sorted(d for d in px["BTC"] if d > t0 and (d // DAY) % HOLD == ANCHOR)


def eligible(px, d):
    return [c for c in COINS if c in px and d in px[c] and d - LOOK * DAY in px[c]]


def pick(px, d, mode="rule", rng=None):
    """{coin: +1 long / -1 short} wanted from the open of day d."""
    el = eligible(px, d)
    m = {c: px[c][d] / px[c][d - LOOK * DAY] - 1 for c in el}
    r = sorted(el, key=lambda c: -m[c])
    out = {c: 1 for c in r[:TOP] if m[c] > 0}
    if len(r) > TOP and m[r[-1]] < 0:
        out[r[-1]] = -1
    if mode == "random":
        nl = sum(v > 0 for v in out.values())
        ch = rng.sample(el, min(len(el), len(out)))
        out = {c: 1 for c in ch[:nl]} | {c: -1 for c in ch[nl:]}
    return out


def segments(px, first):
    """The backtest (the scout's /tmp/scout_1931/bt_rot.py has the same rule): holding segments (coin, d, t_in, t_out)
    for reviews after `first`, oldest first by exit; segments still open at the end are left out."""
    held, since, out = {}, {}, []
    for a in reviews_after(first, px):
        new = pick(px, a)
        for c, d in held.items():
            if new.get(c) != d:
                out.append((c, d, since.pop(c), a))
        for c in new:
            if held.get(c) != new[c]:
                since[c] = a
        held = new
    return out


def review(s, px, d, mode, rng):
    new = pick(px, d, mode, rng)
    for c, p in list(s["pos"].items()):
        if new.get(c) == p["d"]:
            continue                                  # same side: keep holding, no cost
        s["pos"].pop(c)
        price = px[c][d]
        ret = (price / p["entry"] - 1) * p["d"]
        s["cash"] += p["qty"] * price - abs(p["qty"]) * price * COST
        s["log"].append(dict(kind="sell", t=iso(d), coin=c, side=p["side"], px=price, usd=p["usd"], ret=round(ret, 6),
                             pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * price * COST, cost_side=COST,
                             why="หลุดอันดับหรือกลับข้าง"))
    eq = s["cash"] + sum(p["qty"] * px[c][d] for c, p in s["pos"].items())
    for c, sd in new.items():
        if c in s["pos"]:
            continue
        price, usd = px[c][d], max(eq, 0) / 3
        if usd <= 0:
            continue
        s["cash"] += (-usd if sd > 0 else usd) - usd * COST
        why = (f"อันดับ {'ต้นๆ' if sd > 0 else 'ท้าย'} ผลตอบแทน {LOOK} วัน" if mode == "rule" else "สุ่มเหรียญ จำนวนเท่ากฎ")
        s["pos"][c] = dict(side="long" if sd > 0 else "short", d=sd, qty=sd * usd / price, entry=price, last=price, usd=usd,
                           t=iso(d), why=why)
        s["log"].append(dict(kind="buy", t=iso(d), coin=c, side=s["pos"][c]["side"], px=price, usd=usd, why=why))


def step(s, px, mode, rng, closes=None):
    if s.get("seen") is None:
        s["seen"] = max(px["BTC"])
        return
    for d in reviews_after(s["seen"], px):
        review(s, px, d, mode, rng)
        s["seen"] = d
    for c, p in s["pos"].items():
        if c in (closes or {}):
            p["last"] = closes[c]


def main():
    states = {f: load(f, label) for f, (mode, label) in ACCOUNTS.items()}
    now = time.time() * 1000
    last_rev = (now // DAY - (now // DAY - ANCHOR) % HOLD) * DAY
    if all(s.get("seen") is not None and s["seen"] >= last_rev for s in states.values()) and int(now / 1000) % 21600 > 1800:
        return                                         # nothing new: skip the downloads (marks still refresh about every 6 h)
    px, closes = {}, {}
    for c in COINS:
        try:
            b = fetch_daily(c + "USDT")
            px[c], closes[c] = {x["t"]: x["o"] for x in b}, b[-1]["c"]
        except Exception as e:
            print("fwd_rot5 fetch failed", c, type(e).__name__)
    if len(px) < len(COINS):
        return                                         # a missing coin would change the ranking: skip this run
    due = {d for s in states.values() if s.get("seen") is not None for d in reviews_after(s["seen"], px)}
    if any(d not in px[c] or d - LOOK * DAY not in px[c] for d in due for c in COINS):
        return                                         # a review day missing from one coin's bars: skip, never guess
    rng = random.Random()
    for f, (mode, label) in ACCOUNTS.items():
        step(states[f], px, mode, rng, closes)
        save(f, states[f])


if __name__ == "__main__":
    main()
