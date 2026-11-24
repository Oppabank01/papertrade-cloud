#!/usr/bin/env python3
"""Forward paper test of H10-ETH "upward burst in an uptrend" (kalambyryura/ai-trading-arena, strategies/sonnet-h10-eth,
the one recipe of that project that passed its backtest gate), opened 24 Nov 2026 by the scout on 1h bars; backtest
numbers in LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

The recipe runs on 1-minute bars; this is the 1h version. On a closed 1h bar: the close-to-close move of that hour is at
least BURST x rms(close vs open of each of the last RMS_N hours, this one included) and the close is above the mean of
the last SMA_D closed daily closes (UTC days) -> rest a post-only limit buy OFFSET x rms below that close for the next
2 bars. If the first of them opens at or below the limit the order would cross and is dropped (post-only); a fill needs
the low 1 bp through the limit (a touch is not a fill) and fills at the limit, or at the open on the second bar if it
opened below. Stop -5%, target +10%, out at the open of the bar 24 h after the fill bar opened. On the fill bar only the
stop is checked (the target from the next bar, like the recipe); both touched = stop; a gap through the stop fills at
the open. One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_h10.json       ETH, BTC, SOL
  state_fwd_h10_twin.json  control: same limit order and exits at random hours (TWIN_P per free hour), no filter
  python3 fwd_h10.py"""
import math
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
H, DAY = 3600 * 1000, 86400 * 1000
SYMS = ["ETHUSDT", "BTCUSDT", "SOLUSDT"]   # recipe: ETH; BTC and SOL are the coins the card names (my choice to add)
BURST, RMS_N, SMA_D, OFFSET = 3.0, 168, 20, 0.25   # from the recipe
STOP, TGT, HOLD_H, WAIT = 0.05, 0.10, 24, 2        # from the recipe: 500/1000 bps, 24 h, order lives 7200 s = 2 bars
THROUGH = 0.0001                       # recipe: max(1 bp, 2 ticks); 2 ticks dropped (1h bars)
TWIN_P = 1 / 120                       # my choice: about the recipe's order rate (0.2 a day)
LABEL = ("H10 ระเบิดขึ้นในขาขึ้น 1 ชม. ETH BTC SOL (ai-trading-arena ตัวเดียวที่ผ่าน gate ของเขา): แท่ง 1 ชม. ขึ้น 3 เท่าของ rms 168 ชม. "
         "และเหนือ SMA 20 วัน ตั้ง limit ต่ำกว่า 0.25 rms รอ 2 แท่ง stop -5% เป้า +10% ถือไม่เกิน 24 ชม. "
         "(backtest Binance 1 ชม. 2017-2026 หลังหัก 0.35%/ข้าง ETH 285 ไม้ +0.06% ต่อไม้ ก่อนหัก +0.76% มัธยฐาน -0.47% "
         "permutation 200 รอบ p 0.005 แต่ปี 2023-2026 ติดลบทุกปี, BTC 308 ไม้ -0.24% p 0.025, SOL 200 ไม้ -0.12% p 0.065 "
         "ตัวแฝดเวลาสุ่ม ETH -0.63% BTC -0.69% SOL -0.65%)")
ACCOUNTS = {"state_fwd_h10.json": ("rule", LABEL),
            "state_fwd_h10_twin.json": ("random", "H10 ตัวควบคุม: ตั้ง limit แบบเดียวกันที่ชั่วโมงสุ่ม ไม่มีตัวกรอง ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ind(b):
    """rms[i]: root mean square of (close/open - 1) over bars i-RMS_N+1..i; sma[i]: mean of the last SMA_D daily closes
    known at bar i's close (a UTC day closes with its 23:00 bar)."""
    n, rms, sma, sq, days = len(b), [None] * len(b), [None] * len(b), 0.0, []
    for i in range(n):
        sq += (b[i]["c"] / b[i]["o"] - 1) ** 2
        if i >= RMS_N:
            sq -= (b[i - RMS_N]["c"] / b[i - RMS_N]["o"] - 1) ** 2
        if i >= RMS_N - 1:
            rms[i] = math.sqrt(max(sq, 0.0) / RMS_N)
        if (b[i]["t"] + H) % DAY == 0:
            days.append(b[i]["c"])
        if len(days) >= SMA_D:
            sma[i] = sum(days[-SMA_D:]) / SMA_D
    return rms, sma


def signal(b, i, rms, sma):
    if i < 1 or rms[i] is None or sma[i] is None:
        return False
    return b[i]["c"] / b[i - 1]["c"] - 1 >= BURST * rms[i] and b[i]["c"] > sma[i]


def exit_px(p, x):
    """Exit price on bar x for an open long, or None."""
    if x["t"] >= p["exit_t"]:
        return x["o"], f"ครบ {HOLD_H} ชม."
    if x["t"] > p["entry_t"] and x["o"] <= p["stop"]:
        return x["o"], "stop"
    if x["l"] <= p["stop"]:
        return p["stop"], "stop"
    if x["t"] > p["entry_t"] and x["h"] >= p["tgt"]:
        return max(p["tgt"], x["o"]), "ถึงเป้า +10%"
    return None


def fill_px(o, x):
    """Fill price of a pending order o on bar x, 'drop' if it ends, or None to keep waiting."""
    lim, first = o["lim"], x["t"] == o["first_t"]
    if first and x["o"] <= lim:
        return "drop"
    if x["l"] < lim * (1 - THROUGH):
        return lim if first else min(lim, x["o"])
    return "drop" if x["t"] >= o["first_t"] + (WAIT - 1) * H else None


def trades(b, first=1):
    """The backtest: (entry_t, entry_px, exit_t, exit_px) of the rule, oldest first."""
    rms, sma = ind(b)
    out, pos, pend = [], None, None
    for i in range(first, len(b)):
        x, busy = b[i], False
        if pos:
            r = exit_px(pos, x)
            if r:
                out.append((pos["entry_t"], pos["entry"], x["t"], r[0])); pos, busy = None, True
        elif pend:
            f = fill_px(pend, x)
            if f is not None:
                pend, busy = None, f != "drop"
                if f != "drop":
                    pos = dict(entry=f, entry_t=x["t"], exit_t=x["t"] + HOLD_H * H, stop=f * (1 - STOP), tgt=f * (1 + TGT))
                    if x["l"] <= pos["stop"]:
                        out.append((x["t"], f, x["t"], pos["stop"])); pos = None
        if not pos and not pend and not busy and i + 1 < len(b) and rms[i] is not None and signal(b, i, rms, sma):
            pend = dict(lim=x["c"] * (1 - OFFSET * rms[i]), first_t=x["t"] + H)
    return out


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px * (1 - COST)
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen, pend = s.setdefault("seen", {}), s.setdefault("pend", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    rms, sma = ind(bars)
    usd = s["start_usd"] / len(SYMS)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym], busy = x["t"], False
        p = s["pos"].get(sym)
        if p:
            r = exit_px(p, x)
            if r:
                close(s, sym, r[0], x["t"], r[1]); busy = True
        elif sym in pend:
            f = fill_px(pend[sym], x)
            if f is not None:
                o = pend.pop(sym)
                busy = f != "drop"
                if f != "drop" and s["cash"] >= usd * (1 + COST):
                    s["cash"] -= usd * (1 + COST)
                    s["pos"][sym] = dict(side="long", d=1, qty=usd / f, entry=f, last=f, usd=usd, entry_t=x["t"],
                                         exit_t=x["t"] + HOLD_H * H, stop=f * (1 - STOP), tgt=f * (1 + TGT),
                                         t=iso(x["t"]), why=o["why"])
                    s["log"].append(dict(kind="buy", t=iso(x["t"]), coin=sym[:-4], side="long", px=f, usd=usd, why=o["why"]))
                    if x["l"] <= s["pos"][sym]["stop"]:
                        close(s, sym, s["pos"][sym]["stop"], x["t"], "stop")
        if sym in s["pos"] or sym in pend or busy or rms[i] is None:
            continue
        go = signal(bars, i, rms, sma) if mode == "rule" else rng.random() < TWIN_P
        if go:
            why = "แท่ง 1 ชม. ขึ้น %.2f%% เกิน 3 rms เหนือ SMA 20 วัน" % (100 * (x["c"] / bars[i - 1]["c"] - 1)) \
                if mode == "rule" else "สุ่มชั่วโมง"
            pend[sym] = dict(lim=x["c"] * (1 - OFFSET * rms[i]), first_t=x["t"] + H, t=iso(x["t"]), why=why)
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_h10 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
