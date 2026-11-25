#!/usr/bin/env python3
"""Forward paper test of "D_mom8" VR squeeze (younghwan91/quantbox docs/STRATEGIES.md, claimed 2,868 trades WR 62.6% PF 1.97
on 60 perps over 6 years), opened 25 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to
try weak ideas too. Fake money only.

On closed 1h bars: VR = ATR(8) / ATR(56) (Wilder) below 0.5 -> trade the 8-bar momentum side (long if the close is above
the close 8 bars back, short if below). Enter at the next open, hard stop 1%, target 20%, trailing stop 0.5% from the best
price once it has gone 4% our way, out at the close after 192 bars. Each bar: a gap through the stop fills at the open,
then the stop, then the target, then the bar's high (low for a short) moves the trail for the next bar. One position per
coin, one third of the start per coin, 0.35% per side.
  state_fwd_vrsqueeze.json       BTC, ETH, SOL
  state_fwd_vrsqueeze_twin.json  control: random entry times (1 in 200 free bars), random side, same exits
  python3 fwd_vrsqueeze.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch, wilder_atr

COST = 0.0035                 # per side, as every account here
H1 = 3600 * 1000
TWIN_P = 1 / 200              # my choice: more often than the rule (BTC 112 trades in 9 years) so the control fills faster
VR_MAX, MOM_N = 0.5, 8        # from the repo
SL, ACT, DIST, TP, MAXH = 0.01, 0.04, 0.005, 0.20, 192   # from the repo
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the three coins every scout test uses (the repo trades 60 perps);
# also mine: 1h only (the repo runs 15m, 1h and 4h side by side) and no BTC-below-MA50 long gate (G6) and no slot pool
LABEL = ("VR squeeze D_mom8 1 ชม. (quantbox) BTC ETH SOL: ATR8/ATR56 ต่ำกว่า 0.5 เข้าตามทิศ 8 แท่ง stop 1% เป้า 20% "
         "trail 0.5% เมื่อได้ 4% (backtest Binance 1 ชม. 2017-2026 หลังหัก 0.35%/ข้าง BTC 112 ไม้ -0.38% ETH 76 ไม้ -0.52% "
         "SOL 33 ไม้ -0.87% ต่อไม้ ชนะ 15-26% ก่อนหัก +0.32/+0.18/-0.17% ตัวแฝดเข้าสุ่ม -0.67/-0.65/-0.33% "
         "permutation ใช้ไม่ได้เพราะแท่งที่สลับแล้วแทบไม่เกิด squeeze ไม่ผ่าน ห่างจากที่ repo อ้าง win 62.6% มาก)")
ACCOUNTS = {"state_fwd_vrsqueeze.json": ("rule", LABEL),
            "state_fwd_vrsqueeze_twin.json": ("random", "VR squeeze D_mom8 ตัวควบคุม: เข้าสุ่มเวลา ฝั่งสุ่ม ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ind(b):   # same as the scout's /tmp/scout_1207/bt.py
    c = [x["c"] for x in b]
    vr = [a / z if a and z else None for a, z in zip(wilder_atr(b, 8), wilder_atr(b, 56))]
    return vr, [None] * MOM_N + [c[i] / c[i - MOM_N] - 1 for i in range(MOM_N, len(c))]


def signal(i, vr, m):
    if vr[i] is None or m[i] is None or vr[i] >= VR_MAX or m[i] == 0:
        return 0
    return 1 if m[i] > 0 else -1


def exit_px(p, x):
    """Exit price on bar x or None; moves the trail for the next bar. Same order as the backtest's leg()."""
    o, h, l, d = x["o"], x["h"], x["l"], p["d"]
    p["n"] += 1
    if d > 0:
        if o <= p["stop"]: return o, "stop/trail"
        if l <= p["stop"]: return p["stop"], "stop/trail"
        if h >= p["tgt"]: return max(p["tgt"], o), "ถึงเป้า 20%"
        p["peak"] = max(p["peak"], h)
        if p["peak"] >= p["entry"] * (1 + ACT): p["stop"] = max(p["stop"], p["peak"] * (1 - DIST))
    else:
        if o >= p["stop"]: return o, "stop/trail"
        if h >= p["stop"]: return p["stop"], "stop/trail"
        if l <= p["tgt"]: return min(p["tgt"], o), "ถึงเป้า 20%"
        p["peak"] = min(p["peak"], l)
        if p["peak"] <= p["entry"] * (1 - ACT): p["stop"] = min(p["stop"], p["peak"] * (1 + DIST))
    return (x["c"], "ครบ 192 แท่ง") if p["n"] >= MAXH else (None, None)


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
    vr, m = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            px, why = exit_px(p, x)
            if px is not None:
                close(s, sym, px, x["t"] + H1, why)
                exited = True
        if sym in s["pos"] or exited:
            continue
        if mode == "rule":
            d = signal(i, vr, m)
        else:
            d = (1 if rng.random() < 0.5 else -1) if vr[i] and rng.random() < TWIN_P else 0
        usd = s["start_usd"] / 3
        if not d or (d > 0 and s["cash"] < usd * (1 + COST)):
            continue
        e = bars[i + 1]["o"]
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "ATR8/ATR56 ต่ำกว่า 0.5 เข้าตามทิศ 8 แท่ง" if mode == "rule" else "สุ่มเวลา ฝั่งสุ่ม"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd, n=0, peak=e,
                             stop=e * (1 - d * SL), tgt=e * (1 + d * TP), entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_vrsqueeze fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
