#!/usr/bin/env python3
"""Forward paper test: buy BTC / ETH after an options fear spike (Deribit DVOL), opened 23 Nov 2026. Fake money only.

Rule on closed daily bars: DVOL (Deribit public volatility index, daily close) above its mean of the previous 30 days plus
1.5 standard deviations -> buy at the next daily open, sell at the open 10 days later; no new entry while holding.
Coin's own DVOL (BTC, ETH). Half the start per coin, 0.35% per side. Settings chosen by me (look 30, z 1.5, hold 10) from a
36-setting grid per coin.
Backtest 2021-03 to 2026-11 after costs: BTC 51 trades +1.43%/trade (random entry days p 0.002), ETH 61 +1.58% p 0.004.
By year it is a bet on direction: better than random days in 2021, 2023, 2024, worse in 2022, 2025, 2026 (BTC 2025 -2.3%
vs random -0.7%). Opened anyway because the user wants weak ideas tried.
  state_fwd_dvol.json       the rule
  state_fwd_dvol_twin.json  control: random days (1 in 25 free days), same 10-day hold
  python3 fwd_dvol.py"""
import json, random, time, urllib.request
import byttrade as B
from byttrade import iso, load, save

COST, LOOK, Z, HOLD, TWIN_P = 0.0035, 30, 1.5, 10, 1 / 25
DAY = 86400 * 1000
SYMS = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}
DVOL = "https://www.deribit.com/api/v2/public/get_volatility_index_data?currency={}&start_timestamp={}&end_timestamp={}&resolution=1D"
ACCOUNTS = {"state_fwd_dvol.json": ("rule", "ซื้อหลังดัชนีความกลัวออปชันพุ่ง (Deribit DVOL เกินค่าเฉลี่ย 30 วัน + 1.5 SD) BTC ETH ถือ 10 วัน (backtest +1.4%/ไม้ p 0.002 แต่ปี 2025-26 แพ้สุ่ม)"),
            "state_fwd_dvol_twin.json": ("random", "DVOL ตัวควบคุม: ซื้อวันสุ่ม ถือ 10 วันเหมือนกัน")}


def fetch_daily(sym):
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=1d")
    try:
        return B.fetch(sym)
    finally:
        B.URL = old


def fetch_dvol(cur, days=120):
    now = int(time.time() * 1000)
    r = json.loads(urllib.request.urlopen(urllib.request.Request(DVOL.format(cur, now - days * DAY, now), headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())
    return {d[0] // DAY: d[4] for d in r["result"]["data"] if d[0] + DAY <= now}   # closed days only


def spike(dv, day):
    prev = [dv.get(day - k) for k in range(1, LOOK + 1)]
    if day not in dv or None in prev:
        return False
    m = sum(prev) / LOOK
    sd = (sum((x - m) ** 2 for x in prev) / LOOK) ** 0.5
    return dv[day] > m + Z * sd


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px * (1 - COST)
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, dv, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        nxt, p = bars[i + 1], s["pos"].get(sym)
        if p and nxt["t"] >= p["exit_t"]:
            close(s, sym, nxt["o"], nxt["t"], "ครบ 10 วัน")
        if sym in s["pos"]:
            continue
        go = spike(dv, x["t"] // DAY) if mode == "rule" else rng.random() < TWIN_P
        usd = s["start_usd"] / 2
        if not go or s["cash"] < usd * (1 + COST):
            continue
        e = nxt["o"]
        s["cash"] -= usd * (1 + COST)
        why = "DVOL พุ่งเกิน 1.5 SD" if mode == "rule" else "วันสุ่ม"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=nxt["t"], exit_t=nxt["t"] + HOLD * DAY,
                             t=iso(nxt["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nxt["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, data = random.Random(), {}
    for sym, cur in SYMS.items():
        try:
            data[sym] = (fetch_daily(sym), fetch_dvol(cur))
        except Exception as e:
            print("fwd_dvol fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, (bars, dv) in data.items():
            step(s, sym, bars, dv, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
