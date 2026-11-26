#!/usr/bin/env python3
"""Forward paper test of the Donchian ensemble of Zarattini, Pagani and Barbon, "Catching Crypto Trends" (SFI Research
Paper 25-80, 2025: several Donchian channel trend models with different lookbacks combined into one signal, Sharpe above
1.5 net on a rotation of the top 20 coins). Only the abstract could be read, so this is the scout's closest mechanical
version, opened 26 Nov 2026; backtest in LABEL, opened at any p because the user asked to try weak ideas too. Fake money.

On closed daily Binance bars (UTC), per coin: for each lookback n in LBS a model goes in on a close at the n-day closing
high and goes out on a close under its trailing stop (the midpoint of the n-day high and low, set at entry and only moved
up). The share of models in >= THR -> long at the next open; out at the next open on the first close under THR. One
position per coin, one fifth of the start per coin, 0.35% per side. The models start fresh on each 1000-bar fetch, so the
score of a day uses the bars of that fetch up to that day (the backtest in LABEL used full history; same trades on every
coin but BNB, 57 against 58).
  state_fwd_dens.json       BTC ETH SOL BNB XRP
  state_fwd_dens_twin.json  control: random entries (1 in 10 free days), same exits
  python3 fwd_dens.py"""
import random
from collections import deque
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                                   # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: five large coins for the paper's top 20
LBS = (5, 10, 20, 30, 60, 90, 150, 250, 360)    # my choice of lookbacks in days (the abstract gives none)
THR = 0.5                                       # my choice: half the models in (tested 1/3, 1/2, 2/3)
TWIN_P = 1 / 10                                 # my choice: a few times the rule's entry rate; the twin leaves when the rule is off
# also mine: entry on a close at the n-day closing high, the Donchian midpoint as the trailing stop, all-or-nothing size
# in place of the paper's volatility sizing, no rotation, signals on closes, fills at the next open
LABEL = ("Donchian ensemble 9 ช่วง (Zarattini, Pagani, Barbon 2025 แบบที่ใกล้สุด) 5 เหรียญรายวัน: โมเดลละช่วง 5 ถึง 360 วัน "
         "เข้าเมื่อปิดสูงสุดของช่วง ออกเมื่อปิดใต้จุดกึ่งกลางช่องที่เลื่อนขึ้นอย่างเดียว ซื้อเมื่อโมเดลเข้าครึ่งหนึ่งขึ้นไป "
         "ไม้ละ 1 ใน 5 (backtest Binance รายวัน 2018 ถึง 25 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 66 ไม้ +8.14% ต่อไม้ มัธยฐาน -1.84% "
         "ETH 67 ไม้ +5.16% SOL 35 ไม้ +17.45% BNB 70 ไม้ +16.04% XRP 42 ไม้ +7.38% ตัวแฝดเข้าสุ่ม +1.54/+0.84/+2.28/+4.20/+0.11% "
         "ตั้งแต่ 2025 BTC -0.51% ETH -0.18% SOL -1.37% BNB +1.53% XRP -4.26% ต่อไม้ permutation 200 รอบ กริด 3 แบบ "
         "BTC p 0.065 ETH p 0.060 ไม่ผ่านเกณฑ์ 0.01)")
ACCOUNTS = {"state_fwd_dens.json": ("rule", LABEL),
            "state_fwd_dens_twin.json": ("random", "Donchian ensemble ตัวควบคุม: เข้าสุ่ม 1 ใน 10 วัน ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def roll(vals, n, big):
    """Rolling max (big) or min of the n values ending at each index; None before that."""
    out, dq = [None] * len(vals), deque()
    for i, v in enumerate(vals):
        while dq and (vals[dq[-1]] <= v if big else vals[dq[-1]] >= v):
            dq.pop()
        dq.append(i)
        while dq[0] <= i - n:
            dq.popleft()
        if i >= n - 1:
            out[i] = vals[dq[0]]
    return out


def scores(b):
    """Per bar: share of the LBS models that are in (None until the longest lookback exists)."""
    c, h, l = [x["c"] for x in b], [x["h"] for x in b], [x["l"] for x in b]
    tot = [0] * len(b)
    for n in LBS:
        cm, hh, ll = roll(c, n, True), roll(h, n, True), roll(l, n, False)
        inn, stop = False, None
        for i in range(len(b)):
            if cm[i] is None:
                continue
            mid = (hh[i] + ll[i]) / 2
            if inn:
                stop = max(stop, mid)
                if c[i] < stop:
                    inn = False
            elif c[i] >= cm[i]:
                inn, stop = True, mid
            tot[i] += inn
    return [None if i < max(LBS) else tot[i] / len(LBS) for i in range(len(b))]


def trades(b, sc):
    """The backtest (same trades as the scout's /tmp/scout_0909/bt.py trades(b, sc, 0.5)): list of
    (entry t, entry, exit t, exit) on closed daily bars, for a given per-bar score list."""
    pos, out = None, []
    for i in range(len(b) - 1):
        if sc[i] is None:
            continue
        if pos is not None:
            if sc[i] < THR:
                out.append((pos[1], pos[0], b[i + 1]["t"], b[i + 1]["o"]))
                pos = None
            continue
        if sc[i] >= THR:
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
    sc = scores(b)
    for i in shut:
        if b[i]["t"] <= seen[sym] or i + 1 >= len(b):
            continue
        seen[sym] = b[i]["t"]
        g = sc[i]
        if g is None:
            continue
        p = s["pos"].get(sym)
        if p:
            if b[i]["t"] >= p["entry_t"] and g < THR:
                close(s, sym, b[i + 1]["o"], b[i + 1]["t"], f"โมเดลเข้าเหลือ {round(g * len(LBS))} ใน {len(LBS)}")
            continue
        if not (g >= THR if mode == "rule" else rng.random() < TWIN_P):
            continue
        e, t = b[i + 1]["o"], b[i + 1]["t"]
        usd = min(s["start_usd"] / len(SYMS), s["cash"] / (1 + COST))   # my choice: take what cash is left after losses
        if usd < 0.01:
            continue
        s["cash"] -= usd + usd * COST
        why = f"โมเดลเข้า {round(g * len(LBS))} ใน {len(LBS)}" if mode == "rule" else "สุ่มเวลา"
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
            print("fwd_dens fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        for sym, b in bars.items():
            step(s, sym, b, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
