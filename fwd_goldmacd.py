#!/usr/bin/env python3
"""Forward paper test of the closest mechanical form of DaviddDotTech's gold bot (X, 24 Nov 2026: "backtested +1,669%
on 456 trades", elsewhere "loses 69% of its trades, 3.8x R/R"; no rules posted, the build runs through tradingkit.com,
and his silver bot was "a 2 hour strategy using the MACD"), on gold as PAXG (opened 24 Nov 2026 by the scout; backtest
in LABEL, opened at any p because the user asked to try weak ideas too). Fake money only.

On closed 2h PAXGUSDT bars: MACD(12, 26, 9) line crosses above its signal line -> long at the next open; crosses
below -> short. Stop 2 ATR14 (Wilder), target 7.6 ATR (3.8R as in his post), from the signal bar's ATR, checked on bar
high/low from the entry bar on (gap through -> open, both touched -> stop); else out at the close of the 120th bar.
One position, the whole account, 0.35% per side.
  state_fwd_goldmacd.json       PAXG
  state_fwd_goldmacd_twin.json  control: random entry bars (TWIN_P per free bar), random side, same exits
  python3 fwd_goldmacd.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
H2 = 2 * 3600 * 1000
SYMS = ["PAXGUSDT"]            # my choice: the only gold pair on Binance
SL, TP, HOLD = 2.0, 7.6, 120   # my choices: 2 ATR stop, 3.8R target from his post, 10 days cap
WARM = 201                     # same start bar as the backtest loop
TWIN_P = 1 / 25                # my choice: about the rule's signal rate (MACD crosses about 1 in 13 bars, many while holding)
LABEL = ("ทอง MACD 2 ชม. (แทนบอททองของ DaviddDotTech ที่ไม่บอกกฎ) PAXG: MACD 12/26/9 ตัดขึ้นเส้นสัญญาณ long ตัดลง short "
         "stop 2 ATR เป้า 7.6 ATR (3.8R ตามโพสต์) ถือไม่เกิน 120 แท่ง (เลขออกผมเลือกเอง) "
         "(backtest Binance 2 ชม. 2020-2026 หลังหัก 0.35%/ข้าง 503 ไม้ -0.68% ต่อไม้ ก่อนหัก +0.02% ชนะ 23% "
         "เข้าสุ่ม -0.63% permutation 200 รอบ p 0.149 ติดลบทุกปี)")
ACCOUNTS = {"state_fwd_goldmacd.json": ("rule", LABEL),
            "state_fwd_goldmacd_twin.json": ("random", "ทอง MACD ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งสุ่ม stop 2 ATR เป้า 7.6 ATR ถือไม่เกิน 120 แท่งแบบเดียวกัน")}


def fetch_iv(sym, iv="2h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ema(c, n):
    out, e, k = [None] * len(c), None, 2 / (n + 1)
    for i, v in enumerate(c):
        e = v if e is None else e + k * (v - e)
        out[i] = e
    return out


def watr(b, n=14):   # ATR part of the scout's /tmp/scout_0505/bt.py wilder()
    atr, tr_s = [None] * len(b), 0.0
    for i in range(1, len(b)):
        h, l, pc = b[i]["h"], b[i]["l"], b[i - 1]["c"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        if i <= n:
            tr_s += tr
            if i < n:
                continue
        else:
            tr_s = tr_s - tr_s / n + tr
        atr[i] = tr_s / n
    return atr


def ind(b):   # same as bt.py sig_macd
    c = [x["c"] for x in b]
    e12, e26 = ema(c, 12), ema(c, 26)
    m = [a - z for a, z in zip(e12, e26)]
    s = ema(m, 9)
    sig = [0] * len(b)
    for i in range(35, len(b)):   # 35: my warm-up (26 + 9)
        if m[i] > s[i] and m[i - 1] <= s[i - 1]:
            sig[i] = 1
        elif m[i] < s[i] and m[i - 1] >= s[i - 1]:
            sig[i] = -1
    return sig, watr(b)


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
    sig, atr = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            o, h, l, d = x["o"], x["h"], x["l"], p["d"]
            hit = (o if o <= p["stop"] else p["stop"] if l <= p["stop"] else max(p["tgt"], o) if h >= p["tgt"] else None) if d > 0 else \
                  (o if o >= p["stop"] else p["stop"] if h >= p["stop"] else min(p["tgt"], o) if l <= p["tgt"] else None)
            p["held"] = p.get("held", 0) + 1      # closed bars from the entry bar on, counted like the backtest
            if hit is not None:
                close(s, sym, hit, x["t"] + H2, "stop" if (hit - p["entry"]) * d < 0 else "ถึงเป้า 7.6 ATR")
                exited = True
            elif p["held"] >= HOLD:
                close(s, sym, x["c"], x["t"] + H2, "ถือครบ 120 แท่ง")
                exited = True
        if sym in s["pos"] or exited or not atr[i] or i < WARM:
            continue
        if mode == "rule":
            d = sig[i]
        else:
            d = rng.choice((1, -1)) if rng.random() < TWIN_P else 0
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["cash"] / (1 + COST)   # whole account, as byttrade.open_pos (one coin only)
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "MACD ตัดเส้นสัญญาณ" if mode == "rule" else "สุ่มแท่ง ฝั่งสุ่ม"
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=e - d * SL * atr[i], tgt=e + d * TP * atr[i], entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "2h")
        except Exception as e:
            print("fwd_goldmacd fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
