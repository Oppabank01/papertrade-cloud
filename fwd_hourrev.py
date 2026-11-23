#!/usr/bin/env python3
"""Forward paper test of the "Polymarket hourly reversal bot" idea (X, quietoraclex 20 Nov 2026: a bot that bets against
the last hour on the BTC hourly Up/Down markets, no rules posted) in its closest mechanical form, on BTC, ETH, SOL
(opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too).
Fake money only, nothing is sent to Polymarket: the bet is settled on Binance 1h candles, as those markets are.

On each closed 1h Binance candle with |close/open - 1| > THR: bet the next hour goes the other way ("Up" after a red
candle, "Down" after a green one) at an assumed all-in price PX per share; the bet pays 1 per share if the next candle
agrees ("Up" wins on close >= open, as the markets read it), else 0. One bet per coin at a time, STAKE of the start each.
  state_fwd_hourrev.json       BTC, ETH, SOL
  state_fwd_hourrev_twin.json  control: random hours (TWIN_P per free hour), random side, same price and payout
  python3 fwd_hourrev.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # the coins with hourly Up/Down markets; the post used BTC only
PX = 0.52      # my choice: 0.50 at the hour's open + 1c spread + about 1c taker fee and slippage; break-even hit rate 52%
STAKE = 0.02   # my choice: 2% of the start per bet (a lost bet loses all of it, so a third per coin would not survive)
# grid tried in-sample (1h bars before 2024, BTC+ETH+SOL pooled): THR 0 / 0.5% / 1% = 3 settings
GRID = (0.0, 0.005, 0.01)
THR = 0.005    # chosen: best pooled in-sample mean per bet (hit 54.6%, +5.0% per bet; 0% gave +2.6%, 1% gave +4.8%)
TWIN_P = 1 / 3 # my choice: about the rule's bet rate per free hour at THR 0.5% (BTC 1 in 4, SOL 1 in 2)
LABEL = ("กลับทิศรายชั่วโมงแบบ Polymarket BTC ETH SOL (ไอเดียจากโพสต์ quietoraclex): แท่ง 1 ชม. ขยับเกิน 0.5% แทงชั่วโมงถัดไปกลับทิศ "
         "ซื้อที่ 0.52 จ่าย 1 ถ้าถูก (backtest Binance 1 ชม. 2017-2026 จุดคุ้มทุนชนะ 52% BTC 21,283 ไม้ ชนะ 56.0% ETH 29,231 ไม้ 54.9% "
         "SOL 27,423 ไม้ 52.8% ตัวแฝดสุ่ม 49.9-50.1% permutation p 0.005 ทุกเหรียญ แต่ 365 วันล่าสุดชนะแค่ 51.9 ถึง 52.8% "
         "ราคา 0.52 เป็นค่าที่สมมติ ยังไม่ได้เทียบราคาจริงของตลาดรายชั่วโมง)")
ACCOUNTS = {"state_fwd_hourrev.json": ("rule", LABEL),
            "state_fwd_hourrev_twin.json": ("random", "กลับทิศรายชั่วโมง ตัวควบคุม: แทงชั่วโมงสุ่ม ฝั่งสุ่ม ราคา 0.52 จ่าย 1 แบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def side(x, thr=THR):
    m = x["c"] / x["o"] - 1
    return (1 if m < 0 else -1) if abs(m) > thr else 0


def won(d, x):
    return x["c"] >= x["o"] if d > 0 else x["c"] < x["o"]


def trades(b, thr=THR, first=1):
    """The backtest: list of dict(t, d, win), oldest first (one bet per candle, each on the next candle)."""
    out = []
    for i in range(first, len(b) - 1):
        d = side(b[i], thr)
        if d:
            out.append(dict(t=b[i + 1]["t"], d=d, win=won(d, b[i + 1])))
    return out


def settle(s, sym, x):
    p = s["pos"].pop(sym)
    w = won(p["d"], x)
    px = 1.0 if w else 0.0
    s["cash"] += p["qty"] * px
    s["log"].append(dict(kind="sell", t=iso(x["t"]), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"],
                         ret=round(px / PX - 1, 5), pnl=p["usd"] * (px / PX - 1), cost_side=0.0,
                         why=f"ชั่วโมงนั้นปิด {x['c'] / x['o'] - 1:+.2%} {'ถูก' if w else 'ผิด'}ทาง"))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            settle(s, sym, x)
        if sym in s["pos"]:
            continue
        d = side(x) if mode == "rule" else (rng.choice((1, -1)) if rng.random() < TWIN_P else 0)
        if not d:
            continue
        usd = s["start_usd"] * STAKE
        if s["cash"] < usd:
            continue
        s["cash"] -= usd          # the cost is inside PX
        t0 = bars[i + 1]["t"]
        why = (f"แท่งก่อนหน้า {x['c'] / x['o'] - 1:+.2%} แทงกลับทิศ" if mode == "rule" else "สุ่มชั่วโมง สุ่มฝั่ง")
        s["pos"][sym] = dict(side="up" if d > 0 else "down", d=d, qty=usd / PX, entry=PX, last=PX, usd=usd,
                             entry_t=t0, t=iso(t0), why=why)
        s["log"].append(dict(kind="buy", t=iso(t0), coin=sym[:-4], side=s["pos"][sym]["side"], px=PX, usd=usd, why=why))


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_hourrev fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
