#!/usr/bin/env python3
"""Forward paper test of llatoski/LatinTradingNetwork-public rule TF-1 (GitHub, public copy 20 Nov 2026: hold BTC and ETH
in proportion to how many of three horizons, 30, 91 and 365 days, show the price rising faster than cash). Opened
26 Nov 2026 by the scout as a binary version; backtest in LABEL, opened at any p because the user asked to try weak ideas
too. Fake money only.

On closed daily Binance bars (UTC), per coin: count the horizons h in (30, 91, 365) with the close above the close h days
before; count >= K -> long at the next open; out at the next open on the first close where the count is under K. One
position per coin, half the start per coin, 0.35% per side.
  state_fwd_tf1.json       BTC ETH (the repo's coins, against USDT here in place of BRL)
  state_fwd_tf1_twin.json  control: random entries (1 in 10 free days), same exits
  python3 fwd_tf1.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT"]          # the repo trades BTC/BRL and ETH/BRL
HS = (30, 91, 365)                     # the repo's three horizons in days
K = 2                                  # my choice: 2 of 3 (the repo scales size by count/3 and by 10%/yr vol target)
TWIN_P = 1 / 10                        # my choice: about twice the rule's entry rate; the twin leaves when the rule is off
# also mine: cash rate 0 (USDT earns nothing here, the repo compares with the CDI), all-or-nothing size in place of the
# volatility target and the 20%/25% caps, signals on closes, fills at the next open
LABEL = ("TF-1 ตามเทรนด์ 3 ช่วง (llatoski/LatinTradingNetwork) BTC ETH รายวัน: ราคาปิดสูงกว่า 30/91/365 วันก่อนอย่างน้อย 2 ใน 3 ช่วง "
         "ซื้อตอนเปิดวันถัดไป ออกเมื่อเหลือไม่ถึง 2 ไม้ละครึ่งทุน (backtest Binance รายวัน 2018 ถึง 25 พ.ย. 69 หลังหัก 0.35%/ข้าง "
         "BTC 71 ไม้ +9.06% ต่อไม้ มัธยฐาน -1.71% ชนะ 28% ETH 65 ไม้ +14.31% มัธยฐาน -1.98% ตัวแฝดเข้าสุ่ม +3.76/+4.44% "
         "ตั้งแต่ 2025 BTC 9 ไม้ +2.30% ETH 12 ไม้ +3.67% permutation 200 รอบ กริด 3 แบบ (1/2/3 ใน 3) BTC p 0.050 ETH p 0.060 "
         "ไม่ผ่านเกณฑ์ 0.01)")
ACCOUNTS = {"state_fwd_tf1.json": ("rule", LABEL),
            "state_fwd_tf1_twin.json": ("random", "TF-1 ตามเทรนด์ 3 ช่วง ตัวควบคุม: เข้าสุ่ม 1 ใน 10 วัน ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def score(c, i):
    """None until 365 days exist, else how many horizons show a higher close."""
    if i < max(HS):
        return None
    return sum(c[i] > c[i - h] for h in HS)


def trades(b):
    """The backtest (same trades as the scout's /tmp/scout_0909/bt.py trades(b, tf1_score(b), 2)): list of
    (entry t, entry, exit t, exit) on closed daily bars."""
    c = [x["c"] for x in b]
    pos, out = None, []
    for i in range(len(b) - 1):
        g = score(c, i)
        if g is None:
            continue
        if pos is not None:
            if g < K:
                out.append((pos[1], pos[0], b[i + 1]["t"], b[i + 1]["o"]))
                pos = None
            continue
        if g >= K:
            pos = (b[i + 1]["o"], b[i + 1]["t"])
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, b, mode, rng):
    """b: daily bars of one coin, the last day may still be forming. Walks every closed day after s['seen'][sym]."""
    shut = [i for i in range(len(b)) if b[i]["closed"]]
    seen = s["seen"] if isinstance(s.get("seen"), dict) else {}
    s["seen"] = seen
    if sym not in seen:
        seen[sym] = b[shut[-1]]["t"]
        return
    c = [x["c"] for x in b]
    for i in shut:
        if b[i]["t"] <= seen[sym] or i + 1 >= len(b):
            continue
        seen[sym] = b[i]["t"]
        g = score(c, i)
        if g is None:
            continue
        p = s["pos"].get(sym)
        if p:
            if b[i]["t"] >= p["entry_t"] and g < K:
                close(s, sym, b[i + 1]["o"], b[i + 1]["t"], f"เทรนด์เหลือ {g} ใน 3 ช่วง")
            continue
        if not (g >= K if mode == "rule" else rng.random() < TWIN_P):
            continue
        e, t = b[i + 1]["o"], b[i + 1]["t"]
        usd = min(s["start_usd"] / len(SYMS), s["cash"] / (1 + COST))   # my choice: take what cash is left after losses
        if usd < 0.01:
            continue
        s["cash"] -= usd + usd * COST
        why = f"ขึ้น {g} ใน 3 ช่วง (30/91/365 วัน)" if mode == "rule" else "สุ่มเวลา"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=t, t=iso(t), why=why)
        s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = b[-1]["c"]


def main():
    rng = random.Random()
    bars = {}
    for sym in SYMS:
        try:
            bars[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_tf1 fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        for sym, b in bars.items():
            step(s, sym, b, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
