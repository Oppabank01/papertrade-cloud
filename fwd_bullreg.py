#!/usr/bin/env python3
"""Forward paper test of a price-only version of ivanalonso-dev/crypto-bull-regime-system v2 (GitHub 5 Oct 2026: daily
Donchian breakout traded only while its BTC regime detector says "bull - strong", Chandelier 3 x ATR trailing stop) on
BTC, ETH, SOL, BNB, XRP (opened 27 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try
weak ideas too). Fake money only.

On closed 1d Binance bars, long only. BTC regime: raw state "not" when the BTC close is at or below its SMA200, else
"strong" when the 90-day Kaufman efficiency ratio is above 0.14, else "weak"; the state switches only after 5 consecutive
days of a new raw state (the repo uses MVRV above its 200-day mean instead of SMA200; MVRV needs Coin Metrics data).
BUY = flat, state strong and the close above the highest close of the previous 20 days, fill at the next open, stop at
entry - 3 x ATR20. Each closed bar: the stop is a resting order (low at or below it -> fill at min(open, stop)); else the
stop rises to the highest close since entry - 3 x ATR20; SELL at the next open when the close is below the lowest close
of the previous 10 days or the state is "not". One position per coin, one fifth of the start per coin, 0.35% per side.
The regime is computed on the 1000 days byttrade.fetch returns, so its first switch can differ from one seeded years
earlier.
  state_fwd_bullreg.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_bullreg_twin.json  control: random entry on strong-regime days (TWIN_P), same stop and exits
  python3 fwd_bullreg.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: the five majors the other scout accounts use
MA = 200                       # my choice: BTC SMA200 in place of the repo's MVRV > its 200-day mean (no MVRV data here)
ER_N, ER_MIN, CONFIRM = 90, 0.14, 5   # from the repo's detector (ER90 > 0.14, 5 consecutive closes to switch)
BRK, ATR_N, K, XLOW = 20, 20, 3, 10   # from the repo's v2 (20-day close high, 3 x ATR(20), 10-day close low)
TWIN_P = 1 / 23                # my choice: about 1.5 x the backtest rate (25 BTC trades / 868 strong days)
# also mine: ATR is the plain 20-day mean of true range, equal size per coin instead of 0.5% equity risk, fills at the
# next open, five coins instead of the repo's 19
LABEL = ("ระบบขาขึ้น BTC (ivanalonso-dev/crypto-bull-regime-system v2 รุ่นใช้ราคา) BTC ETH SOL BNB XRP: ซื้อเมื่อ BTC "
         "อยู่ในขาขึ้นแรง (เหนือ SMA200 และ ER90 เกิน 0.14 ยืนยัน 5 วัน) และราคาปิดทะลุจุดสูงสุด 20 วัน stop 3 ATR20 "
         "เลื่อนตามจุดสูงสุด ขายเมื่อปิดต่ำกว่าจุดต่ำสุด 10 วันหรือ BTC หลุดขาขึ้น (backtest Binance รายวัน 2017 ถึง "
         "26 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 25 ไม้ +4.64% ต่อไม้ มัธยฐาน -4.48% ETH 26 ไม้ +6.12% SOL 18 ไม้ +29.45% "
         "BNB 24 ไม้ +32.15% มัธยฐาน -1.13% XRP 17 ไม้ +28.98% ตัวแฝดเข้าสุ่มวันขาขึ้นแรง +1.76 ถึง +25.63% แพ้กฎทุกเหรียญ "
         "ตั้งแต่ 2025 2 ถึง 4 ไม้ต่อเหรียญ -1.19 ถึง +13.86% permutation 200 รอบกริด 2 แบบ (3/10, 4/20) "
         "p 0.100/0.020/0.005/0.005/0.005)")
ACCOUNTS = {"state_fwd_bullreg.json": ("rule", LABEL),
            "state_fwd_bullreg_twin.json": ("random", "ระบบขาขึ้น BTC ตัวควบคุม: เข้าวันสุ่มในช่วงขาขึ้นแรง stop และกฎออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def regime(b):
    """per bar 'strong' | 'weak' | 'not' | None, from these bars only"""
    c = [x["c"] for x in b]
    out, state, run, cand = [None] * len(b), None, 0, None
    for i in range(max(MA, ER_N), len(b)):
        sma = sum(c[i - MA + 1:i + 1]) / MA
        vol = sum(abs(c[j] - c[j - 1]) for j in range(i - ER_N + 1, i + 1))
        er = abs(c[i] - c[i - ER_N]) / vol if vol else 0.0
        raw = "not" if c[i] <= sma else ("strong" if er > ER_MIN else "weak")
        if state is None:
            state = raw
        elif raw != state:
            run = run + 1 if raw == cand else 1
            cand = raw
            if run >= CONFIRM:
                state, run, cand = raw, 0, None
        else:
            run, cand = 0, None
        out[i] = state
    return out


def atr(b):
    tr = [None] + [max(x["h"], p["c"]) - min(x["l"], p["c"]) for p, x in zip(b, b[1:])]
    return [None if i < ATR_N else sum(tr[i - ATR_N + 1:i + 1]) / ATR_N for i in range(len(b))]


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, reg_by_t, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    c, a = [x["c"] for x in bars], atr(bars)
    reg = [reg_by_t.get(x["t"]) for x in bars]
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p:
            if x["t"] < p["entry_t"]:
                continue
            if x["l"] <= p["stop"]:
                close(s, sym, min(x["o"], p["stop"]), x["t"], f"หลุด stop {p['stop']:.6g}")
                continue
            p["hc"] = max(p["hc"], c[i])
            p["stop"] = max(p["stop"], p["hc"] - K * a[i])
            if i >= XLOW and c[i] < min(c[i - XLOW:i]):
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "ปิดต่ำกว่าจุดต่ำสุด 10 วัน")
            elif reg[i] not in ("strong", "weak"):
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "BTC หลุดขาขึ้น")
            continue
        if i < BRK + 1 or a[i] is None or reg[i] != "strong":
            continue
        ok = c[i] > max(c[i - BRK:i]) if mode == "rule" else rng.random() < TWIN_P
        if not ok:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "BTC ขาขึ้นแรง ปิดทะลุจุดสูงสุด 20 วัน" if mode == "rule" else "สุ่มวันในขาขึ้นแรง"
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / en, entry=en, last=en, usd=usd, entry_t=et, t=iso(et), why=why,
                             stop=en - K * a[i], hc=0.0)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=en, usd=usd, why=why,
                             stop_set=en - K * a[i]))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_bullreg fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    if "BTCUSDT" not in cache:
        return   # no BTC bars, no regime: no action this round
    btc = cache["BTCUSDT"]
    reg_by_t = {x["t"]: r for x, r in zip(btc, regime(btc)) if x["closed"]}
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, reg_by_t, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
