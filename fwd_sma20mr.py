#!/usr/bin/env python3
"""Forward paper test of the "buy the dip below SMA20" bot (aman25singh/crypto-mean-reversion-backtest, XRP 1h; its own
study says it loses once stops are checked inside the bar), opened 26 Nov 2026 by the scout; backtest in LABEL, opened
at any p because the user asked to try weak ideas too. Fake money only.

On closed 1h bars, long only: flat and the close at least 0.5% below the SMA20 -> buy at the next open. Out at the next
open after a close at least 0.5% above the SMA20 (not on the entry bar), or inside a bar at +5% target or -2.5% stop;
a gap through the stop fills at the open; both touched = stop. One position per coin, one third of the start per
coin, 0.35% per side.
  state_fwd_sma20mr.json       XRP, BTC, ETH
  state_fwd_sma20mr_twin.json  control: random entry times (1 in 30 free bars), same exits
  python3 fwd_sma20mr.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                 # per side, as every account here
H1 = 3600 * 1000
N, BAND, TP, SL = 20, 0.005, 0.05, 0.025   # from the README (SMA-20, buy 0.5% below, sell 0.5% above, 5% target, 2.5% stop)
TWIN_P = 1 / 30               # my choice: about as often as the rule fires
SYMS = ["XRPUSDT", "BTCUSDT", "ETHUSDT"]   # my choice: the README trades XRP only (Coinbase); BTC and ETH added, Binance spot
LABEL = ("ย่อใต้ SMA20 1 ชม. (aman25singh) XRP BTC ETH: ปิดต่ำกว่า SMA20 0.5% ซื้อแท่งถัดไป ขายเมื่อปิดเหนือ SMA20 0.5% "
         "เป้า +5% stop -2.5% (backtest Binance 1 ชม. 2017-2026 หลังหัก 0.35%/ข้าง XRP 4,359 ไม้ -0.80% BTC 3,468 ไม้ -0.72% "
         "ETH 4,570 ไม้ -0.80% ต่อไม้ ก่อนหัก -0.10/-0.02/-0.10% ตัวแฝดเข้าสุ่ม -0.78/-0.69/-0.76% ติดลบทุกปี "
         "permutation 200 รอบ 365 วัน กริด 6 แบบ p 0.91/0.43/0.91 ไม่ผ่าน)")
ACCOUNTS = {"state_fwd_sma20mr.json": ("rule", LABEL),
            "state_fwd_sma20mr_twin.json": ("random", "ย่อใต้ SMA20 ตัวควบคุม: เข้าสุ่มเวลา ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def sma(b):   # same as the scout's /tmp/scout_0216/bt_mr.py sma()
    out, s = [None] * len(b), 0.0
    for i, x in enumerate(b):
        s += x["c"]
        if i >= N:
            s -= b[i - N]["c"]
        if i >= N - 1:
            out[i] = s / N
    return out


def signal(b, i, m):
    return 1 if m[i] is not None and b[i]["c"] <= m[i] * (1 - BAND) else 0


def exit_px(b, j, m, p):
    """price and reason if the position closes during bar j, else (None, None)."""
    x = b[j]
    if x["t"] > p["entry_t"] and m[j - 1] is not None and b[j - 1]["c"] >= m[j - 1] * (1 + BAND):
        return x["o"], "ปิดเหนือ SMA20 0.5%"
    if x["o"] <= p["stop"]: return x["o"], "stop"
    if x["l"] <= p["stop"]: return p["stop"], "stop"
    if x["h"] >= p["tgt"]: return max(p["tgt"], x["o"]), "ถึงเป้า 5%"
    return None, None


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
    m = sma(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < 1:
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            px, why = exit_px(bars, i, m, p)
            if px is not None:
                close(s, sym, px, x["t"] + H1, why)   # the backtest may buy again on the close of the exit bar
        if sym in s["pos"]:
            continue
        d = signal(bars, i, m) if mode == "rule" else (1 if i >= N and rng.random() < TWIN_P else 0)
        usd = s["start_usd"] / 3
        if not d or s["cash"] < usd * (1 + COST):
            continue
        e = bars[i + 1]["o"]
        s["cash"] -= usd + usd * COST
        why = "ปิดต่ำกว่า SMA20 0.5%" if mode == "rule" else "สุ่มเวลา"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, stop=e * (1 - SL), tgt=e * (1 + TP),
                             entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_sma20mr fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
