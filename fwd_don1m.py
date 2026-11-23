#!/usr/bin/env python3
"""Forward paper test of Rizrekt/aiprove-eth-pnl-fixed (GitHub, Nov 2026, an AIProve bounty entry): slow Donchian
breakout on 1m bars, 240-bar entry channel and 120-bar exit channel on closes, symmetric long/short. Opened 24 Nov 2026 by
the scout; the backtest (LABEL) is flat before costs and loses after them, opened anyway because the user asked to try weak
ideas too. Fake money only.

On closed 1m Binance bars (the repo's strategy.py): close above the highest close of the 240 bars before -> long; below the
lowest -> short (a held position flips); otherwise a long exits when the close is below the lowest close of the 120 bars
before, a short when above the highest. Fills at the next open (the repo's backtest.py). No stop, no target, all numbers
the repo's own. One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_don1m.json       BTC, ETH, SOL
  state_fwd_don1m_twin.json  control: random entry minutes (TWIN_P per flat bar), random side, the same 120-bar exit
  python3 fwd_don1m.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the repo trades only ETH; BTC and SOL as every scout account
EN, EX = 240, 120                      # the repo's entry and exit channels (1m bars)
TWIN_P = 1 / 250                       # my choice: about the rule's entry rate per bar in the backtest (500 in 129,600 ETH bars, flat part of the time)
LABEL = ("Donchian 1 นาที (Rizrekt/aiprove-eth-pnl-fixed) BTC ETH SOL: ปิดเหนือราคาปิดสูงสุด 240 แท่งก่อน long ต่ำกว่าต่ำสุด short "
         "ออกเมื่อปิดสวนกรอบ 120 แท่ง (backtest Binance 1 นาที 90 วันถึง 24 พ.ย. 69 หลังหัก 0.35%/ข้าง "
         "ETH 500 ไม้ -0.69% BTC 509 ไม้ -0.72% SOL 494 ไม้ -0.73% ต่อไม้ ก่อนหัก +0.01/-0.02/-0.03% ชนะ 10-17% "
         "permutation 200 รอบ p 0.368/0.701/0.766 ตัวแฝดเข้าสุ่ม -0.72/-0.73/-0.75% ไม่ต่างจากสุ่ม ช่วงนั้นถือเฉยๆ -22 ถึง -30%)")
ACCOUNTS = {"state_fwd_don1m.json": ("rule", LABEL),
            "state_fwd_don1m_twin.json": ("random", "Donchian 1 นาที ตัวควบคุม: เข้านาทีสุ่ม ฝั่งสุ่ม ออกเมื่อปิดสวนกรอบ 120 แท่งแบบเดียวกัน")}


def fetch_iv(sym, iv="1m"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def want(b, i, cur):
    """Side after the close of bar i given the held side cur (None before EN bars of history)."""
    if i < EN:
        return None
    c, w = b[i]["c"], [x["c"] for x in b[i - EN:i]]
    if c > max(w):
        return 1
    if c < min(w):
        return -1
    return exit_side(b, i, cur)


def exit_side(b, i, cur):
    w = [x["c"] for x in b[i - EX:i]]
    if cur > 0 and b[i]["c"] < min(w):
        return 0
    if cur < 0 and b[i]["c"] > max(w):
        return 0
    return cur


def trades(b):
    """The backtest (same as the scout's /tmp/scout_0314/don.py run()): list of (d, entry, exit), oldest first."""
    out, pos, ent = [], 0, None
    for i in range(EN, len(b) - 1):
        w = want(b, i, pos)
        if w != pos:
            px = b[i + 1]["o"]
            if pos:
                out.append((pos, ent, px))
            pos, ent = w, (px if w else None)
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
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < EN:
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        cur = p["d"] if p else 0
        if mode == "rule":
            w = want(bars, i, cur)
        elif cur:
            w = exit_side(bars, i, cur)
        else:
            w = rng.choice((1, -1)) if rng.random() < TWIN_P else 0
        if w == cur:
            continue
        e, t = bars[i + 1]["o"], bars[i + 1]["t"]
        if mode != "rule":
            why = "สุ่มเวลา ฝั่งสุ่ม" if w else "ปิดสวนกรอบ 120 แท่ง"
        else:
            why = "ทะลุกรอบ 240 แท่ง" if w else "ปิดสวนกรอบ 120 แท่ง"
        if p:
            close(s, sym, e, t, why)
        if not w:
            continue
        usd = s["start_usd"] / 3
        if w > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if w > 0 else usd) - usd * COST
        s["pos"][sym] = dict(side="long" if w > 0 else "short", d=w, qty=w * usd / e, entry=e, last=e, usd=usd,
                             entry_t=t, t=iso(t), why=why)
        s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_don1m fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
