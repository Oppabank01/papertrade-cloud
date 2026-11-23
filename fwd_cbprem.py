#!/usr/bin/env python3
"""Forward paper test of the Coinbase premium (Coinbase BTC-USD vs Binance BTCUSDT), opened 23 Nov 2026. Fake money only.

Rule on closed 1h bars: premium = Coinbase close / Binance close - 1, z = (premium - mean of the previous 168 hours) / their
stdev. z > 2 -> long BTC at the next Binance 1h open, z < -2 -> short; close at the open 24 hours later; no new entry while
holding. Whole account, 0.1% per side (Binance spot taker; the other accounts mostly use 0.35%).
Backtest 2021-01 to 2026-11 (24 settings tried, random entry hours as baseline): long side 446 trades -0.49%/trade at 0.35%
per side (+0.21% before costs), short side 514 trades -0.53% (+0.17% before costs), both beat random entry hours (p 0.003 to
0.007) but neither pays 0.35% per side; at 0.1% about break-even. Settings chosen by me. Opened because the user wants weak
ideas tried.
  state_fwd_cbprem.json       the rule
  state_fwd_cbprem_twin.json  control: random hours (1 in 60 free hours), random side, same 24 h hold
  python3 fwd_cbprem.py"""
import json, random, time, urllib.request
from datetime import datetime, timezone
import byttrade as B
from byttrade import iso, load, save

COST, LOOK, Z, HOLD_H, TWIN_P = 0.001, 168, 2.0, 24, 1 / 60
H1 = 3600 * 1000
CB = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=3600&start={}&end={}"
ACCOUNTS = {"state_fwd_cbprem.json": ("rule", "Coinbase premium BTC: ราคา Coinbase แพงกว่า Binance ผิดปกติ (z>2 จาก 7 วัน) long 24 ชม. ถูกผิดปกติ short (backtest ชนะสุ่ม p 0.003 แต่ได้ราว 0.2%/ไม้ก่อนค่าธรรมเนียม)"),
            "state_fwd_cbprem_twin.json": ("random", "Coinbase premium ตัวควบคุม: ชั่วโมงสุ่ม ฝั่งสุ่ม ถือ 24 ชม.")}


def fetch_1h():
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=1h")
    try:
        return B.fetch("BTCUSDT")
    finally:
        B.URL = old


def fetch_cb(hours=290):
    end = int(time.time()) // 3600 * 3600
    f = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
    rows = json.loads(urllib.request.urlopen(urllib.request.Request(CB.format(f(end - hours * 3600), f(end)), headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())
    return {r[0] * 1000: r[4] for r in rows}


def zscores(bars, cb):
    """z per bar index (None when the window is incomplete); bars and cb keyed by open time in ms."""
    prem = [cb[x["t"]] / x["c"] - 1 if x["t"] in cb else None for x in bars]
    z = [None] * len(bars)
    for i in range(LOOK, len(bars)):
        w = prem[i - LOOK:i]
        if prem[i] is None or None in w or bars[i]["t"] - bars[i - LOOK]["t"] != LOOK * H1:
            continue
        m = sum(w) / LOOK
        sd = (sum((x - m) ** 2 for x in w) / LOOK) ** 0.5
        z[i] = (prem[i] - m) / sd if sd > 0 else 0.0
    return z


def close(s, px, t, why):
    p = s["pos"].pop("BTCUSDT")
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin="BTC", side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, bars, cb, mode, rng):
    if s.get("seen") is None:
        s["seen"] = [x for x in bars if x["closed"]][-1]["t"]
        return
    z = zscores(bars, cb)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= s["seen"] or i + 1 >= len(bars):
            continue
        s["seen"] = x["t"]
        nxt, p = bars[i + 1], s["pos"].get("BTCUSDT")
        if p and nxt["t"] >= p["exit_t"]:
            close(s, nxt["o"], nxt["t"], "ครบ 24 ชม.")
        if "BTCUSDT" in s["pos"]:
            continue
        if mode == "rule":
            d = 0 if z[i] is None else 1 if z[i] > Z else -1 if z[i] < -Z else 0
        else:
            d = rng.choice((1, -1)) if rng.random() < TWIN_P else 0
        if not d:
            continue
        e, usd = nxt["o"], s["cash"] / (1 + COST)
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = (f"premium z {z[i]:+.1f}" if mode == "rule" else "ชั่วโมงสุ่ม")
        s["pos"]["BTCUSDT"] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd, entry_t=nxt["t"],
                                   exit_t=nxt["t"] + HOLD_H * H1, t=iso(nxt["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nxt["t"]), coin="BTC", side=s["pos"]["BTCUSDT"]["side"], px=e, usd=usd, why=why))
    if "BTCUSDT" in s["pos"]:
        s["pos"]["BTCUSDT"]["last"] = bars[-1]["c"]


def main():
    try:
        bars, cb = fetch_1h(), fetch_cb()
    except Exception as e:
        print("fwd_cbprem fetch failed", type(e).__name__)
        return
    rng = random.Random()
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        step(s, bars, cb, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
