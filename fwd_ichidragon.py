#!/usr/bin/env python3
"""Forward paper test of the Darsiv Ichimoku Dragon (github.com/Darsiv/Darsiv-Ichimoku-Dragon, an Ichimoku re-tuned to
6-11-17-22-44 with a +-22 shift) on BTC, ETH, SOL daily bars (opened 25 Nov 2026 by the scout; backtest in LABEL).
Fake money only. The repo gives only the indicator, so the trade rule is the textbook Ichimoku long, my choice:

On 1d Binance bars: long when the close is above both cloud lines (Master Senkou A = mean of the 6/11 and 17/22 Donchian
midpoints, Senkou B = 44-bar midpoint, both taken 22 bars back), Tenkan (6) is above Kijun (22) and the close is above the
close 22 bars back (Chikou); enter at the next bar's open. Exit at the next open after a close below Kijun (22). No stop
(the Kijun exit is the stop). One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_ichidragon.json       BTC, ETH, SOL
  state_fwd_ichidragon_twin.json  control: random entry days (TWIN_P per flat day), the same Kijun exit
  python3 fwd_ichidragon.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
DAY = 86400 * 1000
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the three coins every scout test uses
TEN, KIJ, WINGS, SB, SHIFT = 6, 22, (6, 11, 17, 22), 44, 22   # from the repo's Pine script
WARM = SB - 1 + SHIFT          # first bar index with a full 44-bar Senkou B 22 bars back
TWIN_P = 1 / 20                # my choice: about two times the rule's entry rate in the backtest, as in the backtest twin
LABEL = ("Ichimoku Dragon รายวัน BTC ETH SOL (Darsiv 6-11-17-22-44 เลื่อน 22): ปิดเหนือเมฆ Tenkan 6 เหนือ Kijun 22 "
         "และปิดเหนือราคา 22 วันก่อน ซื้อเปิดวันถัดไป ออกเมื่อปิดใต้ Kijun 22 "
         "(backtest Binance รายวัน 2017-2026 หลังหัก 0.35%/ข้าง BTC 83 ไม้ +4.95% ETH 89 ไม้ +4.64% SOL 54 ไม้ +23.5% ต่อไม้ "
         "มัธยฐาน -1.4 ถึง -2.0% ชนะ 36-43% ตัวแฝดวันสุ่ม +0.8/+1.4/+11.3% permutation ค้น 2 แบบ (Dragon กับ 9-26-52) "
         "p 0.010/0.025/0.005 แต่ 9-26-52 ดีกว่าเล็กน้อย ปี 2025-2026 ราว 0% แท่ง 4 ชม. ไม่ผ่าน)")
ACCOUNTS = {"state_fwd_ichidragon.json": ("rule", LABEL),
            "state_fwd_ichidragon_twin.json": ("random", "Ichimoku Dragon ตัวควบคุม: เข้าวันสุ่ม ออกเมื่อปิดใต้ Kijun 22 แบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def mid(b, i, n):
    w = b[i - n + 1:i + 1]
    return (max(x["h"] for x in w) + min(x["l"] for x in w)) / 2


def kijun(b, i):
    return mid(b, i, KIJ)


def signal(b, i):
    """True when the closed bar b[i] gives a long entry for the next open."""
    if i < WARM:
        return False
    j = i - SHIFT
    w = [mid(b, j, n) for n in WINGS]
    sa = ((w[0] + w[1]) / 2 + (w[2] + w[3]) / 2) / 2
    c = b[i]["c"]
    return c > max(sa, mid(b, j, SB)) and mid(b, i, TEN) > kijun(b, i) and c > b[j]["c"]


def trades(b, first=WARM):
    """The backtest: list of (entry_t, entry_px, exit_px) from flat at bar `first`, oldest first; open trades left out."""
    out, pos = [], None
    for i in range(max(first, WARM), len(b) - 1):
        if pos:
            if b[i]["c"] < kijun(b, i):
                out.append((pos[0], pos[1], b[i + 1]["o"]))
                pos = None
        elif signal(b, i):
            pos = (b[i + 1]["t"], b[i + 1]["o"])
    return out


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
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < WARM:
            continue
        seen[sym] = x["t"]
        nx = bars[i + 1]
        if sym in s["pos"]:
            if x["c"] < kijun(bars, i):
                close(s, sym, nx["o"], nx["t"], "ปิดใต้ Kijun 22")
            continue
        go = signal(bars, i) if mode == "rule" else rng.random() < TWIN_P
        usd = s["start_usd"] / 3
        if not go or s["cash"] < usd * (1 + COST):
            continue
        e = nx["o"]
        s["cash"] -= usd + usd * COST
        why = "ปิดเหนือเมฆ Dragon Tenkan เหนือ Kijun ปิดเหนือ 22 วันก่อน" if mode == "rule" else "สุ่มวัน"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=nx["t"], t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_ichidragon fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
