#!/usr/bin/env python3
"""Forward paper test of a mechanical RSI divergence rule, the closest version of zhshy/divergence-trade-signals
(MACD/RSI divergence + Fibonacci signal engine), opened 24 Nov 2026 after the scout's backtest (Binance 4h, last 12,000
bars, 0.35%/side, 200 permutations): BTC 118 trades +0.01%/trade p 0.020, ETH 121 -0.28% p 0.139, SOL 116 +0.14%
p 0.104, BNB 96 -0.55% p 0.338, XRP 86 +0.43% p 0.035; 2025-2026 negative on most coins. Not a pass, opened because
the user asked to try weak ideas too. Fake money only.

On closed 4h bars: a swing low is a bar whose low is below the 3 bars on each side (confirmed 3 bars later, as in the
repo). Long when the newly confirmed swing low is lower than the previous swing low 5 to 40 bars before it, RSI14 at
the new low is higher, and RSI14 at the previous low was <= 35. Short is the mirror on swing highs (RSI >= 65). Enter at
the next open, stop at the new swing low/high, target 2R, checked on closed 4h bars; a gap through the stop fills at
the open; both touched = stop. One position per coin, a fifth of the start per coin, 0.35% per side.
  state_fwd_rsidiv.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_rsidiv_twin.json  control: random entry times (1 in 100 free bars), random side, stop 3.1%, target 2R
  python3 fwd_rsidiv.py"""
import random
from byttrade import iso, load, save, fetch, H4

COST = 0.0035
PR, GAP_MIN, GAP_MAX, OS, OB, RR = 3, 5, 40, 35, 65, 2.0   # pivot 3 from the repo; gaps, RSI levels and 2R chosen by me
TWIN_P, TWIN_STOP = 1 / 100, 0.031    # the rule's signal rate (1 in 97 bars) and median stop distance in the backtest
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
ACCOUNTS = {"state_fwd_rsidiv.json": ("rule", "RSI divergence 4 ชม. BTC ETH SOL BNB XRP long+short: จุดต่ำใหม่ต่ำกว่าแต่ RSI สูงกว่า (RSI จุดแรก 35 ลงมา) stop ที่จุดต่ำ เป้า 2R backtest -0.05% ต่อไม้ เฉลี่ย 5 เหรียญ p 0.02 ถึง 0.34"),
            "state_fwd_rsidiv_twin.json": ("random", "RSI divergence ตัวควบคุม: เข้าสุ่มเวลา ฝั่งสุ่ม stop 3.1% เป้า 2R")}


def rsi14(b):   # same as the scout's /tmp/scout_1715/bt.py ind()
    n, c = len(b), [x["c"] for x in b]
    out, ag, al = [None] * n, None, None
    for i in range(1, n):
        g, l = max(c[i] - c[i - 1], 0), max(c[i - 1] - c[i], 0)
        ag = g if ag is None else (ag * 13 + g) / 14
        al = l if al is None else (al * 13 + l) / 14
        if i >= 14:
            out[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def signals(b):
    """sig[i] = +1/-1 when a divergence is confirmed at the close of bar i and the next open is still on the right side
    of the new pivot; piv[i] = the stop level (the new pivot)."""
    n, rsi = len(b), rsi14(b)
    sig, piv, lows, highs = [0] * n, [None] * n, [], []
    for i in range(2 * PR, n - 1):
        e = b[i + 1]["o"]
        k = i - PR
        if rsi[k] is None:
            continue
        win = b[k - PR:k] + b[k + 1:k + PR + 1]
        if b[k]["l"] < min(x["l"] for x in win):
            for k1 in reversed(lows):
                if k - k1 > GAP_MAX:
                    break
                if k - k1 >= GAP_MIN:
                    if b[k]["l"] < b[k1]["l"] and rsi[k] > rsi[k1] and rsi[k1] <= OS and e > b[k]["l"]:
                        sig[i], piv[i] = 1, b[k]["l"]
                    break
            lows.append(k)
        if b[k]["h"] > max(x["h"] for x in win):
            for k1 in reversed(highs):
                if k - k1 > GAP_MAX:
                    break
                if k - k1 >= GAP_MIN:
                    if b[k]["h"] > b[k1]["h"] and rsi[k] < rsi[k1] and rsi[k1] >= OB and e < b[k]["h"] and not sig[i]:
                        sig[i], piv[i] = -1, b[k]["h"]
                    break
            highs.append(k)
    return sig, piv


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
    sig, piv = signals(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            o, h, l, d = x["o"], x["h"], x["l"], p["d"]
            hit = (o if o <= p["stop"] else p["stop"] if l <= p["stop"] else max(p["tgt"], o) if h >= p["tgt"] else None) if d > 0 else \
                  (o if o >= p["stop"] else p["stop"] if h >= p["stop"] else min(p["tgt"], o) if l <= p["tgt"] else None)
            if hit is not None:
                close(s, sym, hit, x["t"] + H4, "stop" if (hit - p["entry"]) * d < 0 else "ถึงเป้า 2R")
                exited = True
        if sym in s["pos"] or exited:
            continue
        e = bars[i + 1]["o"]
        if mode == "rule":
            d, sd = sig[i], (e - piv[i]) * sig[i] if sig[i] else 0
        else:
            d = rng.choice((1, -1)) if rng.random() < TWIN_P else 0
            sd = TWIN_STOP * e
        if not d:
            continue
        usd = s["start_usd"] / 5
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "RSI divergence" if mode == "rule" else "สุ่มเวลา ฝั่งสุ่ม"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=e - d * sd, tgt=e + d * RR * sd, entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_rsidiv fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
