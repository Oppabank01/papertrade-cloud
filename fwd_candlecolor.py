#!/usr/bin/env python3
"""Forward paper test of Orsonneri/crypto-trading-bots 01-candle-momentum (GitHub, 21 Nov 2026, a Binance futures
backtester): trade today in the colour of yesterday's UTC day candle, managed on 15m bars, long and short, on BTC, ETH,
SOL. Opened 28 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too.
Fake money only.

The repo's default CONFIG (session_start_hour 0, stop_mode fixed_pct 1%, breakout_threshold 1%, partial_share 0.5):
  yesterday green -> long at today's first 15m open, red -> short, doji -> no trade.
  BREAKOUT when that open is within 1% of yesterday's high (low for a short): target = the nearest earlier day whose
  high is above max(yesterday's high, entry) (low below the min for a short), none if no such day; otherwise BASE:
  target = yesterday's high (low). A target on the wrong side of the entry becomes entry +/- 0.2% (the repo's gap_guard).
  Stop = entry -/+ 1%, triggered only by a 15m CLOSE beyond it. Each 15m bar from the entry: half off at halfway to the
  target on touch (stop moves to the entry), then the full target on touch, then the stop on close, then out at the close
  of the day's last bar. Same order as the repo, which is kind to the trader inside one bar.
The earlier days come from Binance 1d bars (1000 days; the repo walks all of its own history: my choice, the 15m feed
here only holds about 10 days). One position per coin, one third of the start per coin, 0.35% per side instead of the
repo's futures fees, no leverage (the repo runs 20x; my choice: a fixed third, as every scout account).
  state_fwd_candlecolor.json       BTC, ETH, SOL
  state_fwd_candlecolor_twin.json  control: a random side every day, the same targets, stops and exits
  python3 fwd_candlecolor.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # the repo's default is ETH; BTC and SOL added by me
STOP_PCT, NEAR, HALF, GAP = 0.01, 0.01, 0.5, 0.002   # from the repo's CONFIG
M15, DAY = 15 * 60 * 1000, 86400 * 1000
LABEL = ("สีแท่งวันก่อน (Orsonneri/crypto-trading-bots) วันก่อนเขียว long แดง short ที่ open วันใหม่ เวลา UTC เป้าที่ high/low "
         "วันก่อนหรือจุดสูงสุดเก่าถ้าเปิดใกล้ไม่เกิน 1% ขายครึ่งที่ครึ่งทางแล้วเลื่อน stop มาทุน stop 1% ดูราคาปิด 15 นาที "
         "ปิดสิ้นวัน BTC ETH SOL (backtest Binance 15 นาที 2017 ถึง 27 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 3,323 ไม้ -0.70% "
         "ETH 3,322 ไม้ -0.75% SOL 2,273 ไม้ -0.76% ต่อไม้ ก่อนหัก +0.004/-0.046/-0.060% ตัวแฝดสุ่มฝั่ง -0.71/-0.72/-0.80% "
         "permutation 200 รอบบน 30,000 แท่งล่าสุด p 0.065/0.512/0.179 ไม่ผ่าน ต้นทุนกินหมด)")
ACCOUNTS = {"state_fwd_candlecolor.json": ("rule", LABEL),
            "state_fwd_candlecolor_twin.json": ("random", "สีแท่งวันก่อนตัวควบคุม: สุ่มฝั่งทุกวัน เป้า stop และการออกแบบเดียวกัน")}


def fetch_iv(sym, iv):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def plan(days, t, d, e):
    """Levels for a trade opened at t (a UTC day start) at e on side d, from closed day bars (oldest first): (stop, take,
    partial) or None when yesterday's bar is missing."""
    k = next((j for j, x in enumerate(days) if x["t"] == t - DAY), None)
    if k is None:
        return None
    prev = days[k]
    peak = prev["h"] if d > 0 else prev["l"]
    if abs(e - peak) / e <= NEAR:
        th = max(peak, e) if d > 0 else min(peak, e)
        take = next(((x["h"] if d > 0 else x["l"]) for x in reversed(days[:k]) if (d > 0 and x["h"] > th) or (d < 0 and x["l"] < th)), None)
    else:
        take = peak
    if take is not None and (take - e) * d <= 0:
        take = e * (1 + GAP * d)
    return e * (1 - STOP_PCT * d), take, (e + (take - e) * HALF if take is not None else None)


def colour(days, t):
    prev = next((x for x in days if x["t"] == t - DAY), None)
    return 0 if prev is None else (prev["c"] > prev["o"]) - (prev["c"] < prev["o"])


def bar(p, x):
    """One closed 15m bar against position p: (partial fill or None, exit fill or None, why)."""
    d, part = p["d"], None
    if p["part"] is not None and not p["halved"] and ((x["h"] >= p["part"]) if d > 0 else (x["l"] <= p["part"])):
        part, p["halved"], p["stop"] = p["part"], True, p["entry"]
    if p["take"] is not None and ((x["h"] >= p["take"]) if d > 0 else (x["l"] <= p["take"])):
        return part, p["take"], "ถึงเป้า"
    if (x["c"] < p["stop"]) if d > 0 else (x["c"] > p["stop"]):
        return part, x["c"], "stop เท่าทุน" if p["halved"] else "stop 1% ราคาปิด"
    if (x["t"] + M15) % DAY == 0:
        return part, x["c"], "ปิดสิ้นวัน"
    return part, None, None


def sell(s, sym, q, px):
    p = s["pos"][sym]
    s["cash"] += q * px - abs(q) * px * COST
    p["qty"] -= q
    p["legs"].append((abs(q) * p["entry"] / p["usd"], px))
    p["fees"] += abs(q) * px * COST


def step(s, sym, bars, days, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    days = [x for x in days if x["closed"]]
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            part, px, why = bar(p, x)
            if part is not None:
                sell(s, sym, p["qty"] * HALF, part)
                s["log"].append(dict(kind="part", t=iso(x["t"] + M15), coin=sym[:-4], side=p["side"], px=part, why="ขายครึ่งที่ครึ่งทาง"))
            if px is not None:
                sell(s, sym, p["qty"], px)
                s["pos"].pop(sym)
                ret = sum(sh * p["d"] * (v / p["entry"] - 1) for sh, v in p["legs"])
                s["log"].append(dict(kind="sell", t=iso(x["t"] + M15), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"],
                                     ret=round(ret, 5), pnl=p["usd"] * ret - p["usd"] * COST - p["fees"], cost_side=COST,
                                     part_px=part if part is not None else p.get("part_px"), why=why))
            elif part is not None:
                p["part_px"] = part
        nx = bars[i + 1]
        if sym in s["pos"] or nx["t"] % DAY:
            continue
        d = colour(days, nx["t"]) if mode == "rule" else rng.choice((1, -1))
        lv = plan(days, nx["t"], d, nx["o"]) if d else None
        if not lv:
            continue
        e, usd = nx["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = f"วันก่อน{'เขียว' if d > 0 else 'แดง'}" if mode == "rule" else "สุ่มฝั่ง"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=lv[0], take=lv[1], part=lv[2], halved=False, legs=[], fees=0.0,
                             entry_t=nx["t"], t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = (fetch_iv(sym, "15m"), fetch_iv(sym, "1d"))
        except Exception as e:
            print("fwd_candlecolor fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, (bars, days) in cache.items():
            step(s, sym, bars, days, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
