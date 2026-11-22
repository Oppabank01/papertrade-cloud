#!/usr/bin/env python3
"""Forward paper test of Larry Williams' volatility breakout on daily BTC, ETH, SOL bars (opened 23 Nov 2026 from a batch
of simple bar ideas; backtest in LABEL, opened at any p because the user asked to try everything). Fake money only.

Each day: range = yesterday's high - low. Buy stop at today's open + K x range, sell stop at open - K x range (with
FILT=1 only the side of yesterday's close vs SMA50). Filled at the level, closed at the next daily open. If both levels
were touched the same day the order is unknown, so the worse of the two trades is booked. Run after the day closes (the
fill is simulated from the closed bar, like a resting stop order). One trade per coin per day, one third of the start
per coin, 0.35% per side.
  state_fwd_volbreak.json       BTC, ETH, SOL
  state_fwd_volbreak_twin.json  control: random days (TWIN_P), random side, in at the open, out at the next open
  python3 fwd_volbreak.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
# grid tried in-sample (bars before 2024, BTC+ETH+SOL pooled): K 0.3/0.5/0.7/0.9 x SMA50 filter off/on = 8 settings
GRID = [(k, f) for k in (0.3, 0.5, 0.7, 0.9) for f in (0, 1)]
K, FILT = 0.9, 1                   # chosen: best pooled in-sample (pre-2024) mean per trade after costs
TWIN_P = 1 / 5                     # about the rule's trade rate (1,929 trades in ~9,000 coin-days)
LABEL = ("ทะลุกรอบผันผวน Larry Williams รายวัน BTC ETH SOL: ซื้อที่ราคาเปิด + 0.9 เท่ากรอบเมื่อวาน ขายที่เปิด - 0.9 เท่า เฉพาะฝั่งตาม SMA50 ออกเปิดวันถัดไป "
         "(backtest 2017-2026 หลังหัก 1,929 ไม้ เฉลี่ย -0.30% มัธยฐาน -0.61% p 0.005 แต่ยังขาดทุนหลังหัก ตก ปี 2024+ 690 ไม้ -0.55%)")
ACCOUNTS = {"state_fwd_volbreak.json": ("rule", LABEL),
            "state_fwd_volbreak_twin.json": ("random", "ทะลุกรอบผันผวน ตัวควบคุม: วันสุ่ม ทิศสุ่ม เข้าตอนเปิด ออกเปิดวันถัดไป")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def sma50(b):
    out, a = [None] * len(b), 0.0
    for i, x in enumerate(b):
        a += x["c"]
        if i >= 50:
            a -= b[i - 50]["c"]
        if i >= 49:
            out[i] = a / 50
    return out


def net(d, e, x):
    return d * (x / e - 1) - COST * (1 + x / e)


def trade_at(b, i, sma, k=K, filt=FILT):
    """(d, entry) for bar i, exit at b[i+1]['o'], or None."""
    if i < 1 or i + 1 >= len(b):
        return None
    y, x, r = b[i - 1], b[i], b[i - 1]["h"] - b[i - 1]["l"]
    if r <= 0:
        return None
    if filt and sma[i - 1] is None:
        return None
    up, dn, ex = x["o"] + k * r, x["o"] - k * r, b[i + 1]["o"]
    go = [(d, e) for d, e, ok, touched in ((1, up, not filt or y["c"] > sma[i - 1], x["h"] >= up),
                                           (-1, dn, not filt or y["c"] < sma[i - 1], x["l"] <= dn)) if ok and touched]
    return min(go, key=lambda g: net(g[0], g[1], ex)) if go else None


def trades(b, k=K, filt=FILT, first=1, sma=None):
    """The backtest: list of dict(t, d, e, x) on closed bars, oldest first."""
    sma, out = sma or sma50(b), []
    for i in range(first, len(b) - 1):
        g = trade_at(b, i, sma, k, filt)
        if g:
            out.append(dict(t=b[i]["t"], d=g[0], e=g[1], x=b[i + 1]["o"]))
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
    sma = sma50(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        if mode == "rule":
            g = trade_at(bars, i, sma)
        else:
            g = (rng.choice((1, -1)), x["o"]) if rng.random() < TWIN_P else None
        if not g:
            continue
        (d, e), usd = g, s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = f"ทะลุ {'บน' if d > 0 else 'ล่าง'} {K} x กรอบเมื่อวาน" if mode == "rule" else "สุ่มวัน สุ่มทิศ"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=x["t"], t=iso(x["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(x["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
        close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "เปิดวันถัดไป")


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_volbreak fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
