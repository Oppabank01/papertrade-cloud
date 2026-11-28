#!/usr/bin/env python3
"""Forward paper test of QuantifiedStrategies' "9 EMA Trading Strategy" (X, 22 and 24 Nov 2026; the post links an article
and gives no crypto rule) in its closest mechanical form on BTC and ETH. Opened 29 Nov 2026 by the scout; backtest in
LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

On closed daily Binance bars (UTC), per coin: close above EMA9 -> long at the next open; out at the next open after the
first close at or below EMA9. One position per coin, half the start per coin, 0.35% per side.
  state_fwd_ema9.json       BTC ETH
  state_fwd_ema9_twin.json  control: random entries (1 in 4 free days), same exit
  python3 fwd_ema9.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT"]          # my choice: the two biggest coins, both backtested
N = 9                                  # from the post (9-period EMA)
TWIN_P = 1 / 4                         # my choice: the rule is long about half the days, the twin leaves at once when the rule is off
# also mine: daily bars, long only, signal on the close and fill at the next open, EMA seeded with the first close
LABEL = ("EMA9 รายวัน (QuantifiedStrategies) BTC ETH: ปิดเหนือ EMA9 ซื้อตอนเปิดวันถัดไป ปิดต่ำกว่าออกวันถัดไป ไม้ละครึ่งทุน "
         "(backtest Binance รายวัน ส.ค. 60 ถึง 28 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 313 ไม้ +0.99% ต่อไม้ มัธยฐาน -1.96% ชนะ 27% "
         "ตัดไม้ดีสุด 1% เหลือ +0.04% ทบต้น +233% แพ้ถือเฉยๆ +1,306% ETH 332 ไม้ +0.62% ทบต้น +3% "
         "2 ปีล่าสุด BTC -0.89% ETH -1.02% ต่อไม้ permutation 200 รอบก่อนหัก BTC p 0.030 ETH p 0.109)")
ACCOUNTS = {"state_fwd_ema9.json": ("rule", LABEL),
            "state_fwd_ema9_twin.json": ("random", "EMA9 รายวัน ตัวควบคุม: เข้าสุ่ม 1 ใน 4 วัน ออกเมื่อปิดต่ำกว่า EMA9 แบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ema(c, n=N):
    a, out = 2 / (n + 1), [c[0]]
    for x in c[1:]:
        out.append(out[-1] + a * (x - out[-1]))
    return out


def trades(b):
    """The backtest (same trades as the scout's /tmp/scout_0220/bt.py ema9_trades): list of (entry t, entry, exit t, exit)."""
    c = [x["c"] for x in b]
    E, pos, out = ema(c), None, []
    for i in range(N, len(b) - 1):
        if pos is not None:
            if c[i] <= E[i]:
                out.append((pos[1], pos[0], b[i + 1]["t"], b[i + 1]["o"]))
                pos = None
            continue
        if c[i] > E[i]:
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
    E = ema(c)
    for i in shut:
        if b[i]["t"] <= seen[sym] or i + 1 >= len(b) or i < N:
            continue
        seen[sym] = b[i]["t"]
        p = s["pos"].get(sym)
        if p:
            if b[i]["t"] >= p["entry_t"] and c[i] <= E[i]:
                close(s, sym, b[i + 1]["o"], b[i + 1]["t"], f"ปิด {c[i]:.2f} ต่ำกว่า EMA9 {E[i]:.2f}")
            continue
        if not (c[i] > E[i] if mode == "rule" else rng.random() < TWIN_P):
            continue
        e, t = b[i + 1]["o"], b[i + 1]["t"]
        usd = min(s["start_usd"] / len(SYMS), s["cash"] / (1 + COST))   # my choice: take what cash is left after losses
        if usd < 0.01:
            continue
        s["cash"] -= usd + usd * COST
        why = f"ปิด {c[i]:.2f} เหนือ EMA9 {E[i]:.2f}" if mode == "rule" else "สุ่มเวลา"
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
            print("fwd_ema9 fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        for sym, b in bars.items():
            step(s, sym, b, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
