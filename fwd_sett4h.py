#!/usr/bin/env python3
"""Forward paper test of a mechanical version of 0xSett's GetAgent playbook (X, 31 Aug 2026: "every 4 hours, it checks
BTC, Gold and SPY and looks for a clear trend using the 20 EMA, 50 EMA and 10-candle return"; the rest of the post is
cut off, so every rule below past those three inputs is my choice). Opened 28 Nov 2026 by the scout; backtest in LABEL,
opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 4h Binance bars: up = EMA20 above EMA50 and the close above the close 10 bars back; down = the mirror.
  Flat and up -> long at the next open; flat and down -> short at the next open (my choice: both sides).
  In a position, the bar no longer up (long) or down (short) -> out at the next open, and a new entry on the same bar
  if the other side holds. No stop, no target (my choice: the post names none).
Coins BTC, ETH, SOL and PAXG for gold (SPY has no Binance bars). EMAs seeded with the first close of the bars fetched
(my choice; 1000 4h bars make the seed irrelevant for EMA50). One position per coin, a quarter of the start per coin,
0.35% per side, no leverage.
  state_fwd_sett4h.json       BTC, ETH, SOL, PAXG
  state_fwd_sett4h_twin.json  control: random entry bars (TWIN_P per flat bar), random side, the same exit rule
  python3 fwd_sett4h.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]   # the post's BTC and gold, plus ETH and SOL (my choice)
FAST, SLOW, LOOK = 20, 50, 10          # from the post
TWIN_P = 1 / 10                        # my choice: gives about as many trades as the rule in the backtest
LABEL = ("EMA20/50 + ผลตอบแทน 10 แท่ง 4 ชม. (0xSett playbook) BTC ETH SOL PAXG long+short ออกเมื่อเงื่อนไขหาย "
         "(backtest Binance 4 ชม. 2017 ถึง 28 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 1,711 ไม้ -0.48% ETH 1,743 ไม้ -0.42% "
         "SOL 1,080 ไม้ -0.03% PAXG 1,235 ไม้ -0.65% ต่อไม้ ก่อนหัก +0.23/+0.28/+0.67/+0.05% มัธยฐาน -0.8 ถึง -1.4% "
         "ชนะ 12-30% ปี 2025+ -0.56/-0.63/-0.48/-0.55% ตัวแฝดเข้าสุ่มออกแบบเดียวกัน -0.66/-0.68/-0.38/-0.67% "
         "permutation 200 รอบบน 6,000 แท่งล่าสุด ก่อนหัก p 0.224/0.358/0.134/0.075)")
ACCOUNTS = {"state_fwd_sett4h.json": ("rule", LABEL),
            "state_fwd_sett4h_twin.json": ("random", "sett4h ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งสุ่ม ออกเมื่อเงื่อนไขเทรนด์ไม่ตรงฝั่งแบบเดียวกัน")}


def ema(c, n):
    k, out = 2 / (n + 1), [c[0]]
    for x in c[1:]:
        out.append(out[-1] + k * (x - out[-1]))
    return out


def lines(b):
    c = [x["c"] for x in b]
    return ema(c, FAST), ema(c, SLOW)


def trend(b, i, f, s):
    """+1 = up on bar i, -1 = down, 0 = neither."""
    r = b[i]["c"] / b[i - LOOK]["c"] - 1
    if f[i] > s[i] and r > 0:
        return 1
    if f[i] < s[i] and r < 0:
        return -1
    return 0


def trades(b, first=60):
    """The backtest (the scout's /tmp/scout_0619/bt.py): list of dict(t, d, e, x, why), oldest first."""
    f, s = lines(b)
    out, p = [], None
    for i in range(first, len(b) - 1):
        z = trend(b, i, f, s)
        if p and z != p["d"]:
            out.append(dict(t=p["entry_t"], d=p["d"], e=p["e"], x=b[i + 1]["o"], why="trend"))
            p = None
        if not p and z:
            p = dict(entry_t=b[i + 1]["t"], d=z, e=b[i + 1]["o"])
    return out


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
    f, sl = lines(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < LOOK:
            continue
        seen[sym] = x["t"]
        z = trend(bars, i, f, sl)
        p = s["pos"].get(sym)
        if p and z != p["d"]:
            close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "เงื่อนไขเทรนด์หาย")
        if sym in s["pos"]:
            continue
        d = z if mode == "rule" else (rng.choice((1, -1)) if rng.random() < TWIN_P else 0)
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 4
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = (f"EMA20 {'เหนือ' if d > 0 else 'ใต้'} EMA50 และ 10 แท่ง{'บวก' if d > 0 else 'ลบ'}" if mode == "rule"
               else "สุ่มแท่ง สุ่มฝั่ง")
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e,
                             usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_sett4h fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
