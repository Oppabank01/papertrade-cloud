#!/usr/bin/env python3
"""Forward paper test of "Stochastics 7 x SMA6" (stangler/stochastics7-sma6-strategy-pine, GitHub 16 Nov 2026: a Pine
contrarian strategy for FX 5m; seven stochastics 5/8/13/21/34/55/89 all oversold, then the SMA6 turns up) on BTC, ETH,
SOL, BNB, XRP (opened 27 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak
ideas too). Fake money only.

On closed 1h Binance bars, long only, the repo's defaults: %K = 100 (close - lowest low) / (highest high - lowest low) over
each period, smoothK 1. "All oversold" = all 7 %K <= 20, "all overbought" = all 7 >= 80. Long signal = all oversold within
the last 3 bars and SMA6 above its previous value; short signal = all overbought within 3 bars and SMA6 below; only the
first bar of each signal counts. BUY at the next open on a long signal when flat; SELL at the next open on a short signal
(the repo reverses there, this account only closes). One position per coin, one fifth of the start per coin, 0.35% per side.
  state_fwd_sto7.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_sto7_twin.json  control: random entry bars (TWIN_P per free bar), same SELL exit
  python3 fwd_sto7.py"""
import random
from collections import deque
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: the five majors the other accounts use
PERIODS, OB, OS, NEED, LOOK, SMA_N = (5, 8, 13, 21, 34, 55, 89), 80, 20, 7, 3, 6   # the repo's defaults
TWIN_P = 1 / 300               # my choice: about the backtest's rate (BTC 163 long entries over 1 in 286 free bars, XRP 1 in 381)
# also mine: 1h bars instead of FX 5m, Binance majors instead of FX, fills at the next open, long only (no reverse into short)
LABEL = ("Stochastic 7 เส้น x SMA6 1 ชม. (stangler) BTC ETH SOL BNB XRP: ซื้อเมื่อสโตแคสติก 7 คาบ (5 ถึง 89) ต่ำกว่า 20 "
         "ครบทุกเส้นภายใน 3 แท่งแล้ว SMA6 หันขึ้น ขายเมื่อเกิน 80 ครบทุกเส้นแล้ว SMA6 หันลง (backtest Binance 1 ชม. "
         "2017 ถึง 27 พ.ย. 69 long อย่างเดียวหลังหัก 0.35%/ข้าง BTC 163 ไม้ +1.00% ต่อไม้ มัธยฐาน +1.54% ชนะ 66% ETH 127 ไม้ "
         "+0.52% SOL 115 ไม้ +0.96% BNB 169 ไม้ +1.64% XRP 111 ไม้ -0.44% ตัวแฝดเข้าสุ่มออกแบบเดียวกัน +0.51/-0.31/+1.24/"
         "+0.66/-0.17% ตั้งแต่ 2025 -0.64 ถึง +2.47% รุ่น repo กลับฝั่ง short ด้วยติดลบทุกเหรียญ -0.74 ถึง -3.77% "
         "permutation 200 รอบบน 6,000 แท่งล่าสุด กริด 2 แบบ p 0.597/0.005/0.761/0.005/0.065)")
ACCOUNTS = {"state_fwd_sto7.json": ("rule", LABEL),
            "state_fwd_sto7_twin.json": ("random", "Stochastic 7 เส้น 1 ชม. ตัวควบคุม: เข้าแท่งสุ่ม ออกเมื่อสโตแคสติกเกิน 80 ครบแล้ว SMA6 หันลงแบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def rolling(vals, n, worse):
    out, dq = [None] * len(vals), deque()
    for i, v in enumerate(vals):
        while dq and worse(vals[dq[-1]], v):
            dq.pop()
        dq.append(i)
        if dq[0] <= i - n:
            dq.popleft()
        if i >= n - 1:
            out[i] = vals[dq[0]]
    return out


def signals(b):
    """per bar +1 (long signal), -1 (short signal) or 0; same as the scout's /tmp/scout_0957/sto.py signals()"""
    n = len(b)
    c, h, l = [x["c"] for x in b], [x["h"] for x in b], [x["l"] for x in b]
    ob, os_ = [0] * n, [0] * n
    for p in PERIODS:
        hh, ll = rolling(h, p, lambda a, v: a <= v), rolling(l, p, lambda a, v: a >= v)
        for i in range(n):
            if hh[i] is None or hh[i] == ll[i]:   # ta.stoch is na on a flat range
                continue
            k = 100 * (c[i] - ll[i]) / (hh[i] - ll[i])
            ob[i] += k >= OB
            os_[i] += k <= OS
    sig, lastob, lastos, ls_prev, ss_prev, s, prev = [0] * n, -10**9, -10**9, False, False, 0.0, None
    for i in range(n):
        if ob[i] >= NEED:
            lastob = i
        if os_[i] >= NEED:
            lastos = i
        s += c[i]
        if i >= SMA_N:
            s -= c[i - SMA_N]
        sma = s / SMA_N if i >= SMA_N - 1 else None
        up = dn = False
        if i >= SMA_N:
            up, dn = sma > prev, sma < prev
        prev = sma
        ls, ss = i - lastos <= LOOK and up, i - lastob <= LOOK and dn
        if ls and not ls_prev:
            sig[i] = 1
        elif ss and not ss_prev:
            sig[i] = -1
        ls_prev, ss_prev = ls, ss
    return sig


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
    sg = signals(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p:
            if x["t"] >= p["entry_t"] and sg[i] == -1:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "สโตแคสติก 7 เส้นเกิน 80 แล้ว SMA6 หันลง")
            continue
        ok = sg[i] == 1 if mode == "rule" else rng.random() < TWIN_P
        if not ok:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "สโตแคสติก 7 เส้นต่ำกว่า 20 แล้ว SMA6 หันขึ้น" if mode == "rule" else "สุ่มแท่ง"
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / en, entry=en, last=en, usd=usd, entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=en, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_sto7 fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
