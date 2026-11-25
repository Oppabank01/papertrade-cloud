#!/usr/bin/env python3
"""Forward paper test of luckylawless1/btc-race-bot (GitHub, Nov 2026, a make.fun "Race a BTC trading bot live for 24
hours" entry): slow EMA regime rider on 1m bars, long only. Opened 25 Nov 2026 by the scout; backtest in LABEL, opened at
any p because the user asked to try weak ideas too. Fake money only.

On closed 1m Binance bars (the repo's main.ts, numbers from its README): flat, at least 240 bars since the last exit
signal, the close above EMA140 by 0.2% and above EMA50 and not more than 2% above EMA140 -> long at the next open. Out at
the next open when the close is 2% under EMA140, 2% under the highest close since entry, or 3% under the entry. EMAs
seeded with the first close of the bars fetched. One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_ema140.json       BTC, ETH, SOL
  state_fwd_ema140_twin.json  control: random entry minutes (1 in 400 free bars after the same cooldown), the same exits
  python3 fwd_ema140.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
M1 = 60 * 1000
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the repo trades only cbBTC; ETH and SOL as every scout account
SLOW, FAST, CLEAR, CHASE = 140, 50, 0.002, 0.02         # from the repo
OUT_EMA, TRAIL, HARD, COOL = 0.02, 0.02, 0.03, 240      # from the repo
TWIN_P = 1 / 400                       # my choice: about the rule's entry rate once the cooldown is over
# also mine: the repo's "stop entering past a 12% equity drawdown" is dropped (the zoo-style verdict judges the account)
LABEL = ("EMA140 1 นาที (luckylawless1 บอทแข่ง make.fun) BTC ETH SOL: ปิดเหนือ EMA140 0.2% และเหนือ EMA50 ไม่เกิน EMA140 +2% "
         "ออกเมื่อปิดต่ำกว่า EMA140 2% หรือต่ำกว่าปิดสูงสุด 2% หรือต่ำกว่าทุน 3% พัก 240 แท่ง "
         "(backtest Binance 1 นาที 60 วันถึง 25 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 44 ไม้ -1.29% ETH 60 ไม้ -1.15% "
         "SOL 80 ไม้ -1.18% ต่อไม้ ก่อนหัก -0.59/-0.45/-0.48% ชนะ 15-18% ตัวแฝดเข้าสุ่ม -1.30/-1.27/-1.16% "
         "permutation 200 รอบ p 0.91/0.76/0.95 ไม่ต่างจากสุ่ม ช่วงนั้นถือเฉยๆ -29 ถึง -43%)")
ACCOUNTS = {"state_fwd_ema140.json": ("rule", LABEL),
            "state_fwd_ema140_twin.json": ("random", "EMA140 1 นาที ตัวควบคุม: เข้านาทีสุ่ม ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1m"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ema(c, n):
    a, v, out = 2 / (n + 1), c[0], []
    for x in c:
        v += a * (x - v); out.append(v)
    return out


def ind(b):   # same as the scout's /tmp/scout_1351/bt.py run_b
    c = [x["c"] for x in b]
    return ema(c, SLOW), ema(c, FAST)


def entry_ok(c, e140, e50):
    return c > e140 * (1 + CLEAR) and c > e50 and c <= e140 * (1 + CHASE)


def exit_now(c, e140, hc, entry):
    return c < e140 * (1 - OUT_EMA) or c < hc * (1 - TRAIL) or c < entry * (1 - HARD)


def trades(b):
    """The backtest (same trades as the scout's /tmp/scout_1351/bt.py run_b): list of (entry bar, entry, exit bar, exit)."""
    e140, e50 = ind(b)
    out, pos, cool, i = [], None, -10 ** 9, SLOW
    while i < len(b) - 1:
        c = b[i]["c"]
        if pos is None:
            if i - cool >= COOL and entry_ok(c, e140[i], e50[i]):
                pos = dict(i=i + 1, e=b[i + 1]["o"], hc=None); i += 1; continue
        else:
            pos["hc"] = c if pos["hc"] is None else max(pos["hc"], c)
            if exit_now(c, e140[i], pos["hc"], pos["e"]):
                out.append((pos["i"], pos["e"], i + 1, b[i + 1]["o"])); pos, cool = None, i
        i += 1
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen, cool = s.setdefault("seen", {}), s.setdefault("cool", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    e140, e50 = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < SLOW:
            continue
        seen[sym] = x["t"]
        p, c = s["pos"].get(sym), x["c"]
        if p:
            if x["t"] < p["entry_t"]:
                continue
            p["hc"] = c if p.get("hc") is None else max(p["hc"], c)
            if exit_now(c, e140[i], p["hc"], p["entry"]):
                why = "ปิดต่ำกว่า EMA140 2%" if c < e140[i] * (1 - OUT_EMA) else "ปิดต่ำกว่าปิดสูงสุด 2%" if c < p["hc"] * (1 - TRAIL) else "ต่ำกว่าทุน 3%"
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], why)
                cool[sym] = x["t"]
            continue
        if x["t"] - cool.get(sym, -10 ** 15) < COOL * M1:
            continue
        go = entry_ok(c, e140[i], e50[i]) if mode == "rule" else rng.random() < TWIN_P
        if not go:
            continue
        e, t, usd = bars[i + 1]["o"], bars[i + 1]["t"], s["start_usd"] / 3
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "ปิดเหนือ EMA140 0.2% และ EMA50" if mode == "rule" else "สุ่มเวลา"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, hc=None, entry_t=t, t=iso(t), why=why)
        s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_ema140 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
