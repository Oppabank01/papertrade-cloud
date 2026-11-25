#!/usr/bin/env python3
"""Forward paper test of "MA Cluster Squeeze" (younghwan91/quantbox docs/STRATEGIES.md, Binance USDT-M 4h), opened 25 Nov
2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 4h bars: SMA 20/50/100/200 all within 3% of each other ((max - min) / min < 3%); close above all four and
8-bar momentum above +1% -> long, close below all four and momentum below -1% -> short. Enter at the next open, hard
stop 2%, target 8%, trailing stop 0.5% from the best price once it has gone 2% our way, out at the close after 192 bars.
Each bar: a gap through the stop fills at the open, then the stop, then the target, then the bar's high (low for a short)
moves the trail for the next bar. One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_macluster.json       BTC, ETH, SOL
  state_fwd_macluster_twin.json  control: random entry times (1 in 50 free bars), random side, same exits
  python3 fwd_macluster.py"""
import random
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                 # per side, as every account here
TWIN_P = 1 / 50               # my choice: about the rule's trade rate on BTC 2017-2026 (303 trades)
SPREAD, MOM_N, MOM = 0.03, 8, 0.01   # from the repo, except MOM_N: the repo gives no momentum window, 8 bars is mine (its D_mom8 uses 8)
SL, ACT, DIST, TP, MAXH = 0.02, 0.02, 0.005, 0.08, 192   # from the repo; MAXH is mine (the repo lists 192 bars for D_mom8 only)
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the three coins every scout test uses (the repo trades 60 perps)
LABEL = ("MA Cluster Squeeze 4 ชม. (quantbox) BTC ETH SOL: SMA 20/50/100/200 ห่างกันไม่เกิน 3% ปิดเหนือทุกเส้นและขึ้น 8 แท่งเกิน 1% "
         "long (short กลับกัน) stop 2% เป้า 8% trail 0.5% เมื่อได้ 2% (backtest Binance 4 ชม. 2017-2026 หลังหัก 0.35%/ข้าง "
         "BTC 303 ไม้ -0.46% ETH 238 ไม้ -0.44% SOL 111 ไม้ -0.20% ต่อไม้ ก่อนหัก +0.24/+0.27/+0.50% ตัวแฝดเข้าสุ่ม "
         "-0.57/-0.74/-0.65% permutation 200 รอบ p 0.085/0.095/0.060 ไม่ผ่าน)")
ACCOUNTS = {"state_fwd_macluster.json": ("rule", LABEL),
            "state_fwd_macluster_twin.json": ("random", "MA Cluster Squeeze ตัวควบคุม: เข้าสุ่มเวลา ฝั่งสุ่ม ออกแบบเดียวกัน")}


def sma(c, n):
    out, s = [None] * len(c), 0.0
    for i, v in enumerate(c):
        s += v
        if i >= n:
            s -= c[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ind(b):   # same as the scout's /tmp/scout_1207/bt.py
    c = [x["c"] for x in b]
    m = [None] * MOM_N + [c[i] / c[i - MOM_N] - 1 for i in range(MOM_N, len(c))]
    return m, [sma(c, n) for n in (20, 50, 100, 200)]


def signal(b, i, m, ss):
    v = [s[i] for s in ss]
    if None in v or m[i] is None or (max(v) - min(v)) / min(v) >= SPREAD:
        return 0
    if b[i]["c"] > max(v) and m[i] > MOM:
        return 1
    if b[i]["c"] < min(v) and m[i] < -MOM:
        return -1
    return 0


def exit_px(p, x):
    """Exit price on bar x or None; moves the trail for the next bar. Same order as the backtest's leg()."""
    o, h, l, d = x["o"], x["h"], x["l"], p["d"]
    p["n"] += 1
    if d > 0:
        if o <= p["stop"]: return o, "stop/trail"
        if l <= p["stop"]: return p["stop"], "stop/trail"
        if h >= p["tgt"]: return max(p["tgt"], o), "ถึงเป้า 8%"
        p["peak"] = max(p["peak"], h)
        if p["peak"] >= p["entry"] * (1 + ACT): p["stop"] = max(p["stop"], p["peak"] * (1 - DIST))
    else:
        if o >= p["stop"]: return o, "stop/trail"
        if h >= p["stop"]: return p["stop"], "stop/trail"
        if l <= p["tgt"]: return min(p["tgt"], o), "ถึงเป้า 8%"
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
    m, ss = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            px, why = exit_px(p, x)
            if px is not None:
                close(s, sym, px, x["t"] + H4, why)
                exited = True
        if sym in s["pos"] or exited:
            continue
        if mode == "rule":
            d = signal(bars, i, m, ss)
        else:
            d = (1 if rng.random() < 0.5 else -1) if ss[3][i] and rng.random() < TWIN_P else 0
        usd = s["start_usd"] / 3
        if not d or (d > 0 and s["cash"] < usd * (1 + COST)):
            continue
        e = bars[i + 1]["o"]
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "SMA 4 เส้นบีบแล้วทะลุ" if mode == "rule" else "สุ่มเวลา ฝั่งสุ่ม"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd, n=0, peak=e,
                             stop=e * (1 - d * SL), tgt=e * (1 + d * TP), entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_macluster fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
