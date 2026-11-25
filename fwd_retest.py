#!/usr/bin/env python3
"""Forward paper test of "breakout then wait for the retest" (X posts on FensoryApp's breakout-retest option, e.g.
x.com/andyweb_3/status/2124820757297439063: "buying the breakout and waiting for the retest are two different trades").
The posts give no numbers, so every number here is my choice. Opened 25 Nov 2026 by the scout; backtest in LABEL,
opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 1d Binance bars: a close above the highest close of the N bars before marks level L. For up to W bars after it,
a bar whose low comes within TOUCH of L and closes above L is the retest -> long at the next open. A close below L*FAIL
first, or no retest in W bars, cancels it. Exit at the next open after a close below the lowest close of the X bars
before, or a close below L*FAIL. One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_retest.json       BTC, ETH, SOL
  state_fwd_retest_twin.json  control: random entry days (TWIN_P per free day), L = that day's close, the same exits
  python3 fwd_retest.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
N = 20                         # my choice: breakout lookback (searched 20 and 55; 20 gives more trades)
W = 10                         # my choice: bars to wait for the retest
X = 10                         # my choice: exit on a close below the lowest close of the X bars before
TOUCH = 0.01                   # my choice: the retest low may stay up to 1% above L
FAIL = 0.97                    # my choice: a close 3% under L means the breakout failed (cancel or exit)
TWIN_P = 1 / 20                # my choice: as the backtest twin
DAY = 86400 * 1000
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
LABEL = ("ทะลุแล้วรอ retest รายวัน BTC ETH SOL: ปิดเหนือราคาปิดสูงสุด 20 วันก่อน ได้ระดับ L รอไม่เกิน 10 วันให้ low ลงมาแตะ "
         "ไม่เกิน L+1% แล้วปิดเหนือ L ซื้อเปิดวันถัดไป ออกเมื่อปิดต่ำกว่าต่ำสุด 10 วันก่อน หรือปิดต่ำกว่า L-3% "
         "(backtest Binance รายวัน 2017-2026 หลังหัก 0.35%/ข้าง ต่อไม้ BTC 59 ไม้ +4.6% ETH 56 +3.0% SOL 32 +22.6% "
         "มัธยฐาน -4.1/-4.5/-4.5% ชนะ 36-41% ซื้อทันทีที่ทะลุ +6.1/+7.5/+20.1% ตัวแฝดวันสุ่ม +1.8/+1.9/+8.6% "
         "permutation ค้น 2 แบบ (20/55 วัน) p 0.095/0.373/0.020 ไม่ผ่าน รอ retest แย่กว่าซื้อทันที)")
ACCOUNTS = {"state_fwd_retest.json": ("rule", LABEL),
            "state_fwd_retest_twin.json": ("random", "ทะลุแล้วรอ retest ตัวควบคุม: เข้าวันสุ่ม L เท่าราคาปิดวันนั้น ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def brk(b, i):
    """L when bar i closes above the highest close of the N bars before, else None."""
    L = max(x["c"] for x in b[i - N:i])
    return L if b[i]["c"] > L else None


def out(b, i, L):
    return b[i]["c"] < min(x["c"] for x in b[i - X:i]) or b[i]["c"] < L * FAIL


def trades(b, first=N):
    """The backtest (scout /tmp/scout_1027/bt.py, N=20): list of (entry_t, entry_px, exit_px), open trades left out."""
    res, pos, pend = [], None, None
    for i in range(max(first, N, X), len(b) - 1):
        x = b[i]
        if pos:
            if x["t"] >= pos[0] and out(b, i, pos[2]):
                res.append((pos[0], pos[1], b[i + 1]["o"]))
                pos = None
        elif pend:
            L, exp_t = pend
            if x["c"] < L * FAIL or x["t"] > exp_t:
                pend = None
            elif x["l"] <= L * (1 + TOUCH) and x["c"] > L:
                pos, pend = (b[i + 1]["t"], b[i + 1]["o"], L), None
        else:
            L = brk(b, i)
            if L:
                pend = (L, x["t"] + W * DAY)
    return res


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px - p["qty"] * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen, pend = s.setdefault("seen", {}), s.setdefault("pend", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < max(N, X):
            continue
        seen[sym] = x["t"]
        nx, p = bars[i + 1], s["pos"].get(sym)
        if p:
            if x["t"] >= p["entry_t"] and out(bars, i, p["L"]):
                close(s, sym, nx["o"], nx["t"], "ปิดต่ำกว่าต่ำสุด 10 วัน หรือต่ำกว่า L-3%")
            continue
        L = None
        if sym in pend:
            pL, exp_t = pend[sym]
            if x["c"] < pL * FAIL or x["t"] > exp_t:
                del pend[sym]
            elif x["l"] <= pL * (1 + TOUCH) and x["c"] > pL:
                L = pL
                del pend[sym]
            if L is None:
                continue
        elif mode == "rule":
            bL = brk(bars, i)
            if bL:
                pend[sym] = [bL, x["t"] + W * DAY]
            continue
        elif rng.random() < TWIN_P:
            L = x["c"]
        if L is None:
            continue
        usd = s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        e = nx["o"]
        s["cash"] -= usd + usd * COST
        why = f"retest ระดับ {L:.6g}" if mode == "rule" else "สุ่มวัน"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, L=L, entry_t=nx["t"], t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_retest fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
