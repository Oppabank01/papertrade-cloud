#!/usr/bin/env python3
"""Forward paper test of the v3 rule of evangelosbalalas/Kraken-Crypto-Trading-Bot (GitHub, 27 Nov 2026: BTC/ETH, SMA100
+/-2% regime filter, inverse-vol weights, weekly rebalance, 50% vol target). Backtested by the scout in the 29 Nov 00:44 run
(rule rewritten from Kraken_bot.py, repo code not run). Opened at any p because the user asked to try weak ideas too.
Fake money only.

On closed daily Binance bars (all numbers from the repo's settings): the BTC regime turns on when the BTC close is above
its SMA100 x 1.02 and off when below SMA100 x 0.98, else keeps its state. Regime off -> both coins flat at the next open.
Regime on -> on the first on day and every 7 days after it, score = 0.5 x 30-day return + 0.5 x 90-day return per coin;
hold each coin whose score > 0, flat the others, changes at the next open; between those days nothing changes.
The repo holds inverse-vol weights scaled to 50% annual vol (a portfolio); an account here holds one fixed-size position
per coin instead (my choice, so trades can be counted), half of the start per coin, long only, no stop, 0.35% per side.
  state_fwd_krakenreg.json       BTC, ETH
  state_fwd_krakenreg_twin.json  control: random entry days (TWIN_P per flat coin-day), out TWIN_HOLD days later
  python3 fwd_krakenreg.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch, H4

COST, DAY = 0.0035, 86400 * 1000
SYMS = ["BTCUSDT", "ETHUSDT"]                # the repo's universe (Kraken BTC/USD, ETH/USD; Binance spot here)
SMA, BAND, REB = 100, 0.02, 7                # from the repo (SMA_DAYS, REGIME_BAND, REBALANCE_DAYS)
TWIN_P, TWIN_HOLD = 1 / 70, 67               # my choice: about the rule's rate (48 trades in 9 years) and mean hold (67 days)
LABEL = ("BTC เหนือ SMA100 (บอท Kraken) BTC ETH รายวัน: BTC ปิดเหนือ SMA100 2% เปิดโหมดถือ หลุดใต้ 2% ขายหมด "
         "ระหว่างโหมดถือทุก 7 วันถือเหรียญที่ครึ่งผลตอบแทน 30 วันบวกครึ่ง 90 วันเป็นบวก "
         "(backtest Binance รายวัน 2017-2026 หลังหัก 0.35%/ข้าง 48 ไม้ +50.5% ต่อไม้ มัธยฐาน -2.2% ตัดไม้ดีสุด 1% +20.6% "
         "ชนะ 42% ถือเฉลี่ย 67 วัน ตัวแฝดเข้าสุ่มถือเท่ากัน +11.4% แบบพอร์ตตาม repo +2,806% DD 42% ถือ 50/50 เฉยๆ +565% DD 88% "
         "ปี 2025 +7.5% 2026 -16.0% permutation 200 รอบก่อนหัก p 0.005)")
ACCOUNTS = {"state_fwd_krakenreg.json": ("rule", LABEL),
            "state_fwd_krakenreg_twin.json": ("random", "BTC เหนือ SMA100 ตัวควบคุม: เข้าวันสุ่ม ถือ 67 วัน")}


def fetch_daily(sym):   # as fwd_minifund.fetch_daily
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=1d")
    try:
        return fetch(sym)
    finally:
        B.URL = old


def regime(c):
    out, on, s = [], False, 0.0
    for t in range(len(c)):
        s += c[t]
        if t >= SMA:
            s -= c[t - SMA]
        if t < SMA - 1:
            on = False
        elif c[t] > s / SMA * (1 + BAND):
            on = True
        elif c[t] < s / SMA * (1 - BAND):
            on = False
        out.append(on)
    return out


def score(c, t):
    return 0.5 * (c[t] / c[t - 30] - 1) + 0.5 * (c[t] / c[t - 90] - 1)


def targets(btc, other):
    """Wanted holding (0/1) of `other` at each bar's close; btc and other aligned by time, oldest first."""
    cb, co = [x["c"] for x in btc], [x["c"] for x in other]
    reg, out, last, cur = regime(cb), [], None, 0
    for t in range(len(cb)):
        if t < SMA:
            out.append(0)
            continue
        if not reg[t]:
            last, cur = None, 0
        elif last is None or t - last >= REB:
            cur, last = int(score(co, t) > 0), t
        out.append(cur)
    return out


def align(btc, other):
    tb = {x["t"]: x for x in btc}
    o2 = [x for x in other if x["t"] in tb]
    return [tb[x["t"]] for x in o2], o2


def trades(btc, other, first=SMA):
    """The backtest (same rule as the scout's /tmp/scout_0044/bt.py trades()): list of dict(t, e, x)."""
    btc, other = align(btc, other)
    tg, out, p = targets(btc, other), [], None
    for i in range(first, len(other) - 1):
        if p is None and tg[i]:
            p = dict(t=other[i + 1]["t"], e=other[i + 1]["o"])
        elif p is not None and not tg[i]:
            out.append(dict(t=p["t"], e=p["e"], x=other[i + 1]["o"]))
            p = None
    return out


def close(s, sym, px, t, why):   # as fwd_minifund.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, btc, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    btc, bars = align(btc, bars)
    tg, reg = targets(btc, bars), regime([y["c"] for y in btc])
    for i, x in enumerate(bars):
        if not x["closed"] or not btc[i]["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < SMA:
            continue
        seen[sym] = x["t"]
        p, nb = s["pos"].get(sym), bars[i + 1]
        if mode == "rule":
            w = tg[i]
            why_out = "BTC หลุดใต้ SMA100 2%" if not reg[i] else "โมเมนตัม 30/90 วันติดลบ"
        elif p:
            w = 1 if nb["t"] - p["entry_t"] < TWIN_HOLD * DAY else 0
            why_out = f"ครบ {TWIN_HOLD} วัน"
        else:
            w = 1 if rng.random() < TWIN_P else 0
        if p and not w:
            close(s, sym, nb["o"], nb["t"], why_out)
        elif not p and w:
            e, usd = nb["o"], s["start_usd"] / len(SYMS)
            if s["cash"] < usd * (1 + COST):
                continue
            s["cash"] -= usd + usd * COST
            why = "BTC เหนือ SMA100 และโมเมนตัม 30/90 วันบวก" if mode == "rule" else "สุ่มวัน"
            s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=nb["t"], t=iso(nb["t"]),
                                 why=why)
            s["log"].append(dict(kind="buy", t=iso(nb["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_daily(sym)
        except Exception as e:
            print("fwd_krakenreg fetch failed", sym, type(e).__name__)
    if "BTCUSDT" not in cache:
        return
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, cache["BTCUSDT"], bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
