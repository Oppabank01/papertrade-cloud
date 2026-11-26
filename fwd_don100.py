#!/usr/bin/env python3
"""Forward paper test of nguyenphong198e/donchian-miniapp (GitHub, Nov 2026, the "MEKVRO" Donchian H4 bot's paper engine),
opened 26 Nov 2026 by the scout; backtest in LABEL. Fake money only.

On closed 4h bars: the first bar whose close is above the highest high of the 100 bars before it (a flip; no new entry
while that coin is held) -> long at the next open. Stop 6 ATR14 (Wilder) below the entry, then the highest high since
entry minus 6 ATR14, only moving up; a low at or under the stop sells at the stop (at the open on a gap); 180 bars
(30 days) after the signal bar it sells at that bar's close. One position per coin, one eighth of the start per coin,
0.35% per side.
  state_fwd_don100.json       BTC ETH SOL BNB ZEC AVAX XRP NEAR (the repo's coin list)
  state_fwd_don100_twin.json  control: random entry bars (TWIN_P per free bar), same exits
  python3 fwd_don100.py"""
import random
from collections import deque
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                     # per side, as every account here (the repo pays 0.07% + funding on futures)
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ZECUSDT", "AVAXUSDT", "XRPUSDT", "NEARUSDT"]
LOOK, K, MAXB = 100, 6.0, 180     # the repo's LOOKBACK 100, TRAIL_ATR 6, MAX_BARS 180
# my choices: spot long only with no leverage; one eighth of the start per coin in place of the repo's 2% risk sizing;
# no volume filter (the repo added VOL_MULT 1.5 on 25 Nov, byttrade.fetch has no volume; backtest with it was about
# the same); entry at the next open instead of the breakout close; TWIN_P gives the twin about 10x the rule's entries
TWIN_P = 1 / 55
LABEL = ("Donchian 4 ชม. (nguyenphong198e/donchian-miniapp) 8 เหรียญ: ปิดเหนือจุดสูงสุด 100 แท่งก่อนหน้าครั้งแรก ซื้อ "
         "stop 6 ATR แล้ว trail 6 ATR ใต้จุดสูงสุด ถือไม่เกิน 30 วัน "
         "(backtest Binance 4h 2017-2026 หลังหัก 0.35%/ข้าง 553 ไม้ +6.72% ต่อไม้ มัธยฐาน -2.59% ชนะ 41% ตัวแฝดเข้าสุ่ม +2.49% "
         "ตั้งแต่ 2025 BTC 18 ไม้ -0.74% ETH -0.11% SOL -1.07% ZEC +17.7% permutation 200 รอบ 6000 แท่งล่าสุด กริด 9 แบบ "
         "BTC p 0.687 ETH p 0.119 SOL p 0.363 ไม่ผ่าน)")
ACCOUNTS = {"state_fwd_don100.json": ("rule", LABEL),
            "state_fwd_don100_twin.json": ("random", "Donchian 4 ชม. ตัวควบคุม: เข้าแท่งสุ่ม ทางออก trail 6 ATR แบบเดียวกัน")}


def ind(b):
    """Per bar: Wilder ATR14 (None until defined) and flip (close above the highest high of the LOOK bars before,
    previous bar not above its own ceiling)."""
    n = len(b)
    atr, flip, a, prev, dq = [None] * n, [False] * n, 0.0, False, deque()
    for i in range(n):
        if i >= 1:
            tr = max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - b[i - 1]["c"]), abs(b[i]["l"] - b[i - 1]["c"]))
            a = tr if i == 1 else (a * 13 + tr) / 14
            if i >= 14:
                atr[i] = a
        if i >= LOOK:
            above = b[i]["c"] > b[dq[0]]["h"]
            flip[i] = above and not prev
            prev = above
        while dq and b[dq[-1]]["h"] <= b[i]["h"]:
            dq.pop()
        dq.append(i)
        while dq[0] <= i - LOOK:
            dq.popleft()
    return atr, flip


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px - p["qty"] * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    atr, flip = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            if x["l"] <= p["stop"]:
                close(s, sym, min(p["stop"], x["o"]), x["t"] + H4, "stop" if p["stop"] <= p["sl0"] else "trail 6 ATR")
                exited = True
            else:
                p["ext"] = max(p["ext"], x["h"])
                if atr[i]:
                    p["stop"] = max(p["stop"], p["ext"] - K * atr[i])
                if (x["t"] - p["sig_t"]) // H4 >= MAXB:
                    close(s, sym, x["c"], x["t"] + H4, "ครบ 30 วัน")
                    exited = True
        if sym in s["pos"] or exited or not atr[i]:
            continue
        go = flip[i] if mode == "rule" else i >= LOOK and rng.random() < TWIN_P
        if not go:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS) / (1 + COST)   # so all eight fit with the fee
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "ปิดทะลุจุดสูงสุด 100 แท่ง" if mode == "rule" else "สุ่มเวลา"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, sl0=e - K * atr[i], stop=e - K * atr[i],
                             ext=e, sig_t=x["t"], entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_don100 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
