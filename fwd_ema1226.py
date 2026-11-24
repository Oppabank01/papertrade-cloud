#!/usr/bin/env python3
"""Forward paper test of the "ema_crossover" winner of maymay5692's dev.to post "I backtested 49 crypto trading
strategies" (Binance daily BTC/USDT 2023 to Feb 2026, fast 12 / slow 26, 34 trades, Sharpe 1.30; the post gives no
other rule). Opened 24 Nov 2026 by the scout; backtest in LABEL. Fake money only.

On closed 1d Binance bars: EMA12 of closes above EMA26 -> long at the next open; EMA12 at or below EMA26 -> out at the
next open. Long only, no stop, no target (the post's plain-language rule). One position per coin, one third of the
start per coin, 0.35% per side.
  state_fwd_ema1226.json       BTC, ETH, SOL
  state_fwd_ema1226_twin.json  control: random entry days (TWIN_P per flat day), out after HOLD days
  python3 fwd_ema1226.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the post's main table is BTC, it also ran ETH and SOL
FAST, SLOW = 12, 26                    # the post's numbers
TWIN_P = 1 / 34                        # my choice: about the rule's entry rate per flat day in the backtest (BTC 1/33, ETH 1/35, SOL 1/38)
HOLD = 35                              # my choice: the rule's mean hold in days in the backtest (34 to 35)
LABEL = ("EMA 12/26 รายวัน (maymay5692 backtest 49 ท่า dev.to) BTC ETH SOL: EMA12 เหนือ EMA26 ถือ long ตัดลงออก "
         "(backtest Binance 1d 2017-2026 หลังหัก 0.35%/ข้าง BTC 50 ไม้ +16.3% ETH 48 ไม้ +13.3% SOL 32 ไม้ +52.9% ต่อไม้ "
         "มัธยฐาน -4 ถึง -7% ชนะ 34-40% ทบรวม BTC x40 ETH x29 SOL x95 เทียบถือเฉยๆ x14/x6/x25 "
         "แต่ 3 ปีล่าสุด x1.70/x1.65/x1.09 เทียบ x1.64/x0.84/x1.25 permutation 200 รอบ (เลือกดีสุดจาก EMA กับ PSAR) "
         "p 0.015/0.050/0.005 edge ของการตามเทรนด์ที่รู้กันอยู่แล้ว ไม่ผ่าน 0.01 ทุกเหรียญ)")
ACCOUNTS = {"state_fwd_ema1226.json": ("rule", LABEL),
            "state_fwd_ema1226_twin.json": ("random", "EMA 12/26 รายวัน ตัวควบคุม: เข้าวันสุ่ม ถือครบ 35 วันแล้วออก")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ema(c, n):
    a, out, e = 2 / (n + 1), [], c[0]
    for x in c:
        e = a * x + (1 - a) * e
        out.append(e)
    return out


def above(b):
    """Per bar: EMA12 > EMA26 on closes (False for the first SLOW bars)."""
    c = [x["c"] for x in b]
    f, s = ema(c, FAST), ema(c, SLOW)
    return [i >= SLOW and f[i] > s[i] for i in range(len(c))]


def trades(b):
    """The backtest (same as the scout's /tmp/scout_0834/bt.py pos_trades(ema_pos)): (entry_t, entry, exit), oldest first."""
    up, out, ent = above(b), [], None
    for i in range(len(b) - 1):
        if up[i] and ent is None:
            ent = (b[i + 1]["t"], b[i + 1]["o"])
        elif not up[i] and ent is not None:
            out.append((ent[0], ent[1], b[i + 1]["o"]))
            ent = None
    return out


def close(s, sym, px, t, why):   # as pullback.close
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
    up = above(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < SLOW:
            continue
        seen[sym] = x["t"]
        if sym in s["pos"]:
            p = s["pos"][sym]
            p["held"] = p.get("held", 0) + 1      # closed bars since the entry bar
            if mode == "rule" and not up[i]:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "EMA12 ตัดลงใต้ EMA26")
            elif mode != "rule" and p["held"] >= HOLD:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "ถือครบ 35 วัน")
            continue
        if mode == "rule":
            go, why = up[i], "EMA12 เหนือ EMA26"
        else:
            go, why = rng.random() < TWIN_P, "สุ่มวัน"
        if not go:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_ema1226 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
