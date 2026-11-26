#!/usr/bin/env python3
"""Forward paper test of "Donchian 20 breakout, ATR stop and target" (drakkB/pine-script-22-strategies-btc-benchmark,
script 10-donchian-20-atr-stop-target.pine; on its sealed BTC 1d period 2024-12-17 to 2026-10-16 at 0.1%/side: 13 trades
+33.79% vs holding -23.25%, verdict inconclusive). Opened 26 Nov 2026 by the scout; backtest in LABEL, opened at any p
because the user asked to try weak ideas too. Fake money only.

On closed 1d Binance bars (the script as written): flat and the close above the highest high of the 20 bars before ->
long at the next open; stop = signal close - 2 * ATR14, target = signal close + 3 * ATR14 (Pine's ta.atr, RMA seeded
with the SMA of the first 14 true ranges of the bars fetched), checked on closed daily bars from the entry bar on; a gap
through the stop fills at the open, a gap over the target fills at the open; both touched = stop. The exit bar's own
close may signal a new entry (Pine fills the exit inside that bar). One position per coin, one fifth of the start per
coin, 0.35% per side.
  state_fwd_don20atr.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_don20atr_twin.json  control: random entry days (TWIN_P per flat day), the same ATR stop and target
  python3 fwd_don20atr.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: the repo ran BTC only; the 5 large coins the scout uses
LOOK, AN, SL, TP = 20, 14, 2, 3        # the script's numbers
TWIN_P = 1 / 22                        # my choice: about the rule's entry rate per flat day in the backtest (1/21 to 1/32)
LABEL = ("Donchian 20 รายวัน stop 2 ATR เป้า 3 ATR (drakkB 22 ท่า Pine) BTC ETH SOL BNB XRP: ปิดเหนือจุดสูงสุด 20 วันก่อน ซื้อ "
         "(backtest Binance 1d 2017-2026 หลังหัก 0.35%/ข้าง BTC 106 ไม้ +0.70% ต่อไม้ ETH 105 ไม้ +1.35% SOL 71 ไม้ +5.74% "
         "BNB 104 ไม้ +3.93% XRP 78 ไม้ +1.42% ชนะ 47-57% ตัวแฝดเข้าสุ่ม +1.3/+1.1/+2.4/+1.5/+0.9% "
         "ตั้งแต่ 2025 +2.04/-0.95/-3.58/+1.63/-0.23% ต่อไม้ permutation 200 รอบ p 0.299/0.129/0.005/0.005/0.080 "
         "SOL กับ BNB ผ่าน 0.01 รายเหรียญ แต่ลอง 10 แบบ (2 ท่า x 5 เหรียญ) จึงยังไม่ผ่านเมื่อคิดจำนวนครั้งที่ลอง)")
ACCOUNTS = {"state_fwd_don20atr.json": ("rule", LABEL),
            "state_fwd_don20atr_twin.json": ("random", "Donchian 20 ตัวควบคุม: เข้าวันสุ่ม stop 2 ATR เป้า 3 ATR แบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def pine_atr(b, n=AN):
    """Pine ta.atr (same as the scout's /tmp/scout_pine22.py): RMA of the true range, seeded with the SMA of the first n."""
    tr = [b[0]["h"] - b[0]["l"]] + [max(x["h"] - x["l"], abs(x["h"] - p["c"]), abs(x["l"] - p["c"])) for p, x in zip(b, b[1:])]
    out, a = [None] * len(b), None
    for i in range(len(b)):
        if i == n - 1:
            a = sum(tr[:n]) / n
        elif i >= n:
            a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


def brk(b, i):
    return i >= LOOK and b[i]["c"] > max(x["h"] for x in b[i - LOOK:i])


def hit(x, stop, tgt):
    o = x["o"]
    return o if o <= stop else stop if x["l"] <= stop else max(tgt, o) if x["h"] >= tgt else None


def trades(b):
    """The backtest (same trades as the scout's /tmp/scout_pine22.py don20_trades): (entry_t, entry, exit), oldest first."""
    atr, out, i, n = pine_atr(b), [], LOOK, len(b)
    while i < n - 1:
        if not (brk(b, i) and atr[i]):
            i += 1
            continue
        e, stop, tgt = b[i + 1]["o"], b[i]["c"] - SL * atr[i], b[i]["c"] + TP * atr[i]
        j = i + 1
        while j < n and hit(b[j], stop, tgt) is None:
            j += 1
        if j >= n:
            break
        out.append((b[i + 1]["t"], e, hit(b[j], stop, tgt)))
        i = j
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
    atr = pine_atr(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < LOOK:
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            px = hit(x, p["stop"], p["tgt"])
            if px is not None:
                close(s, sym, px, x["t"] + B.DAY, "stop 2 ATR" if px < p["entry"] else "ถึงเป้า 3 ATR")
        if sym in s["pos"] or not atr[i]:
            continue
        if mode == "rule":
            go, why = brk(bars, i), "ปิดเหนือจุดสูงสุด 20 วัน"
        else:
            go, why = rng.random() < TWIN_P, "สุ่มวัน"
        if not go:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 5
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, stop=x["c"] - SL * atr[i],
                             tgt=x["c"] + TP * atr[i], entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_don20atr fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
