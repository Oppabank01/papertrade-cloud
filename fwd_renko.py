#!/usr/bin/env python3
"""Forward paper test of percentage Renko bricks from santhoshmurali/tradingview "PValue-True Percentage Renko" (GitHub,
Nov 2026; the repo draws the bricks only and gives no orders) turned into a stop-and-reverse rule on BTC, ETH, SOL daily
bars (opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too).
Fake money only.

Bricks follow the repo's spec: compounding grid (up = price x (1 + P), down = price / (1 + P)), High/Low basis, only on
closed bars, continue before testing a reversal, R-brick reversal (2 = the repo's default). The grid is anchored at the
open of the first bar the account sees, so it differs from the backtest's anchor in 2017.
Trade: when the brick direction changes on a closed bar (first brick included) -> at the next open go long (up) or short
(down), closing any opposite position. Always in the market after the first brick.
One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_renko.json       BTC, ETH, SOL
  state_fwd_renko_twin.json  control: flips to a random side at random days (TWIN_P per day), always in after the first
  python3 fwd_renko.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
# grid tried in-sample (daily bars before 2024, BTC+ETH+SOL pooled): P 5/10/15% x R 1/2 = 6 settings (P 10% and R 2 are
# the repo's defaults; 5% and 15% and R 1 are mine). In-sample pooled after costs: 5%/1 -0.55%,
# 5%/2 -0.10%, 10%/1 +0.11%, 10%/2 +3.07%, 15%/1 +2.24%, 15%/2 +16.08% per trade
GRID = [(p, r) for p in (0.05, 0.10, 0.15) for r in (1, 2)]
P, R = 0.15, 2                     # chosen in-sample: best pooled mean per trade after costs (+16.1%, 160 trades); it sits
                                   # on the edge of the grid, so a wider brick might look better still (not tried)
TWIN_P = 1 / 45                    # my choice: about the rule's flip rate per coin-day in the backtest (BTC 1/85, SOL 1/28)
LABEL = ("Renko เปอร์เซ็นต์ BTC ETH SOL รายวัน (santhoshmurali/tradingview): อิฐ 15% กลับทิศ 2 อิฐ อิฐเปลี่ยนเป็นขึ้น long "
         "เปลี่ยนเป็นลง short ถืออยู่ตลอด (backtest 2017-2026 หลังหัก 0.35%/ข้าง BTC 40 ไม้ +15.1% p 0.124 ETH 75 ไม้ +5.9% "
         "p 0.199 SOL 83 ไม้ +15.9% p 0.005 มัธยฐานติดลบทุกเหรียญ ปี 2024+ BTC -14.4% ETH -5.1% SOL -1.3% ต่อไม้ "
         "ตัวแฝดกลับฝั่งสุ่ม -11.9/-8.2/+0.1% แพ้ถือเฉยๆ ทุกเหรียญ)")
ACCOUNTS = {"state_fwd_renko.json": ("rule", LABEL),
            "state_fwd_renko_twin.json": ("random", "Renko ตัวควบคุม: กลับฝั่งสุ่มในวันสุ่ม ถืออยู่ตลอดแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def brick(st, x, p=P, r=R):
    """Advance Renko state st = [ref, bo, bc, dir] by one closed bar x; returns the new direction if it changed, else 0."""
    f = 1 + p
    ref, bo, bc, d = st
    d0 = d
    if d == 0:
        if x["h"] >= ref * f:
            bo, bc, d = ref, ref * f, 1
        elif x["l"] <= ref / f:
            bo, bc, d = ref, ref / f, -1
        else:
            return 0
    if d == 1:
        while x["h"] >= bc * f:
            bo, bc = bc, bc * f
        trig = bo if r == 1 else bo / f
        if x["l"] <= trig:
            (bo, bc), d = ((bc, bo) if r == 1 else (bo, bo / f)), -1
            while x["l"] <= bc / f:
                bo, bc = bc, bc / f
    elif d == -1:
        while x["l"] <= bc / f:
            bo, bc = bc, bc / f
        trig = bo if r == 1 else bo * f
        if x["h"] >= trig:
            (bo, bc), d = ((bc, bo) if r == 1 else (bo, bo * f)), 1
            while x["h"] >= bc * f:
                bo, bc = bc, bc * f
    st[:] = [ref, bo, bc, d]
    return d if d != d0 else 0


def trades(b, p=P, r=R, first=1):
    """The backtest (the scout's /tmp/scout_0938.py calls this): list of dict(t, d, e, x), oldest first. The grid is
    anchored at b[first]['o'], bricks start on b[first + 1]; the last open position is left out."""
    st, out, cur = [b[first]["o"], None, None, 0], [], None
    for i in range(first + 1, len(b) - 1):
        d = brick(st, b[i], p, r)
        if d:
            e = b[i + 1]["o"]
            if cur:
                out.append(dict(t=cur[0], d=cur[1], e=cur[2], x=e))
            cur = (b[i + 1]["t"], d, e)
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen, rk = s.setdefault("seen", {}), s.setdefault("rk", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        if sym not in rk:
            rk[sym] = [x["o"], None, None, 0]      # anchor the grid on the first new bar, no brick on it
            continue
        d = brick(rk[sym], x)
        if mode == "random":
            d = rng.choice((1, -1)) if rng.random() < TWIN_P else 0
        if not d:
            continue
        e, t = bars[i + 1]["o"], bars[i + 1]["t"]
        p = s["pos"].get(sym)
        if p:
            if p["d"] == d:
                continue
            close(s, sym, e, t, "อิฐกลับทิศ" if mode == "rule" else "สุ่มกลับฝั่ง")
        usd = s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = (f"อิฐ {P:.0%} เปลี่ยนเป็น{'ขึ้น' if d > 0 else 'ลง'}" if mode == "rule" else "สุ่มวัน สุ่มฝั่ง")
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=t, t=iso(t), why=why)
        s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_renko fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
