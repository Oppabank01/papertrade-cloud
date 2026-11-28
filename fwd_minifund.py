#!/usr/bin/env python3
"""Forward paper test of the trend signal of Red-Eye-Research/Mini-Fund-Engine (GitHub, 24 Nov 2026: multi-horizon
time-series momentum with EWMA volatility targeting on BTC ETH SOL PAXG LINK). Backtested by the scout in the 23:06 run
(rule rewritten from src/strategy.py, repo code not run). Opened at any p because the user asked to try weak ideas too.
Fake money only.

Signal at each closed daily Binance bar t (from the repo): mean over lb in 14/30/90 days of
tanh(return over lb / (EWMA daily vol x sqrt(lb))), EWMA of squared daily returns with span 20, floored at 10% a year.
The repo holds a continuous weight (signal / vol); an account here holds one fixed-size position per coin, so the side is
long when signal > TH, short when signal < -TH, flat in between, changed at the next open. One position per coin, one
fifth of the start per coin, no stop (the signal is the exit), 0.35% per side.
  state_fwd_minifund.json       BTC, ETH, SOL, LINK, PAXG
  state_fwd_minifund_twin.json  control: random entry days (TWIN_P per flat coin-day), random side, out TWIN_HOLD days later
  python3 fwd_minifund.py"""
import math
import random
import byttrade as B
from byttrade import iso, load, save

COST, DAY = 0.0035, 86400 * 1000
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "PAXGUSDT"]   # the repo's universe
LBS, SPAN, FLOOR = (14, 30, 90), 20, 0.10       # from the repo's config.py
TH = 0.25                                       # my choice, the middle of the 0 / 0.25 / 0.5 grid backtested
WARM = 200                                      # my choice: first 200 bars only settle the EWMA vol
TWIN_P, TWIN_HOLD = 1 / 10, 10                  # my choice: about the rule's mean hold (backtest: 9.9 days)
LABEL = ("TSMOM หลายช่วง Mini-Fund-Engine รายวัน: ค่าเฉลี่ย tanh(ผลตอบแทน 14/30/90 วัน หารความผันผวน EWMA) เกิน 0.25 long "
         "ต่ำกว่า -0.25 short ระหว่างนั้นถือเงินสด BTC ETH SOL LINK PAXG "
         "(backtest Binance รายวันถึง 27 พ.ย. 69 หลังหัก 0.35%/ข้าง 941 ไม้ +1.52% ต่อไม้ มัธยฐาน -1.72% ตัดไม้ดีสุด 1% -0.18% "
         "ชนะ 25% ปี 2024-2026 ราว 0% permutation 200 รอบกริดก่อนหัก BTC p 0.030 ETH 0.015 SOL 0.020 LINK 0.080 PAXG 0.149)")
ACCOUNTS = {"state_fwd_minifund.json": ("rule", LABEL),
            "state_fwd_minifund_twin.json": ("random", "TSMOM Mini-Fund ตัวควบคุม: เข้าวันสุ่ม ฝั่งสุ่ม ถือ 10 วัน")}


def fetch_daily(sym):   # as fwd_tripleema.fetch_daily
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=1d")
    try:
        return B.fetch(sym)
    finally:
        B.URL = old


def signal(c):
    a = 2 / (SPAN + 1)
    var, vol = FLOOR ** 2 / 365, [FLOOR]
    for i in range(1, len(c)):
        r = c[i] / c[i - 1] - 1
        var = (1 - a) * var + a * r * r
        vol.append(max(FLOOR, math.sqrt(max(var, 1e-12) * 365)))
    sig = [0.0] * len(c)
    for t in range(max(LBS), len(c)):
        dv = vol[t] / math.sqrt(365)
        sig[t] = sum(math.tanh((c[t] / c[t - lb] - 1) / max(dv * math.sqrt(lb), 1e-6)) for lb in LBS) / len(LBS)
    return sig


def want(sig, i):
    return 1 if sig[i] > TH else -1 if sig[i] < -TH else 0


def trades(b, first=WARM):
    """The backtest (same rule as the scout's /tmp/scout_2306/bt.py discrete_trades(th=0.25, ls=True)): dict(t, d, e, x)."""
    sig = signal([x["c"] for x in b])
    out, p = [], None
    for i in range(max(first, WARM), len(b) - 1):
        w, cur = want(sig, i), p["d"] if p else 0
        if w == cur:
            continue
        e = b[i + 1]["o"]
        if p:
            out.append(dict(t=p["t"], d=p["d"], e=p["e"], x=e))
            p = None
        if w:
            p = dict(t=b[i + 1]["t"], d=w, e=e)
    return out


def close(s, sym, px, t, why):   # as fwd_tripleema.close
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
    sig = signal([x["c"] for x in bars])
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < WARM:
            continue
        seen[sym] = x["t"]
        p, nb = s["pos"].get(sym), bars[i + 1]
        cur = p["d"] if p else 0
        if mode == "rule":
            nd = want(sig, i)
            why_out = "สัญญาณเปลี่ยนฝั่ง" if nd else "สัญญาณกลับเข้าช่วงกลาง"
        elif p:
            nd = cur if nb["t"] - p["entry_t"] < TWIN_HOLD * DAY else 0
            why_out = f"ครบ {TWIN_HOLD} วัน"
        else:
            nd = rng.choice((1, -1)) if rng.random() < TWIN_P else 0
        if nd == cur:
            continue
        if p:
            close(s, sym, nb["o"], nb["t"], why_out)
        if not nd:
            continue
        e, usd = nb["o"], s["start_usd"] / len(SYMS)
        if nd > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if nd > 0 else usd) - usd * COST
        why = f"สัญญาณ TSMOM {sig[i]:+.2f}" if mode == "rule" else "สุ่มวัน สุ่มฝั่ง"
        s["pos"][sym] = dict(side="long" if nd > 0 else "short", d=nd, qty=nd * usd / e, entry=e, last=e, usd=usd,
                             entry_t=nb["t"], t=iso(nb["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nb["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_daily(sym)
        except Exception as e:
            print("fwd_minifund fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
