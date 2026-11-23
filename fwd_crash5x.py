#!/usr/bin/env python3
"""Crash bounce at 5x: buy alts that fell hard on a day the whole market fell, opened 23 Nov 2026. Fake money only.

Rule on Binance 1 h bars: when a closed hour shows BTC down 5%+ over 24 h and a coin down 15%+ over 24 h, go long that
coin at 5x at the next hour's open and close after 24 h; liquidated (margin lost) if any hour's low is 18% under entry.
Each trade puts a fifth of the account's current equity up as margin, at most 5 open, one per coin. 0.25% per side on
the notional (fees plus slip), so 2.5% of margin per round trip.
Backtest 2017-2026, 23 big coins listed on Binance today: 1,015 signals on 210 days, 1x +3.7% a trade vs -0.4% on random
24 h holds (p < 0.002), positive every year; 5x +10.6% a trade, 136 liquidated (13%), 51 doubled. Signals bunch on the
same crash days, so the real sample is about 210 days, and coins that died (LUNA, FTT) are missing, which flatters a
bounce rule. crash.py's c_crashbounce_24h_500 runs the same signal at 1x on Hyperliquid; this is the leveraged version
(IDEAS_QUEUE #2 from the Fable pass). About 23 signal days a year: nothing happens on most nights.
  state_fwd_crash5x.json        the rule
  state_fwd_crash5x_twin.json   control: same coins, a random closed hour about as often (1 in 2,000 coin-hours), same 5x exit
  python3 fwd_crash5x.py"""
import random, time
import byttrade as B
from byttrade import iso, load, save

COINS = "ETH SOL XRP BNB DOGE ADA AVAX LINK DOT LTC BCH TRX NEAR ATOM UNI AAVE FIL ETC APT ARB OP SUI INJ".split()
LEV, HOLD, LIQ, COST, SLOTS, TWIN_P = 5, 24, -0.18, 0.0025, 5, 1 / 2000
BTC_DROP, COIN_DROP = -0.05, -0.15
H = 3600 * 1000
ACCOUNTS = {"state_fwd_crash5x.json": ("rule", "ช้อนเหรียญวันตลาดพัง 5x: BTC -5% และเหรียญ -15% ใน 24 ชม. long 5x ถือ 24 ชม. (backtest 1x +3.7% ต่อไม้ บวกทุกปี)"),
            "state_fwd_crash5x_twin.json": ("random", "ช้อนวันตลาดพัง 5x ตัวควบคุม: เหรียญเดียวกัน ชั่วโมงสุ่ม ถือ 24 ชม. 5x")}


def fetch(sym):
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=1h")
    try:
        return B.fetch(sym + "USDT")
    finally:
        B.URL = old


def step(s, coin, b, btc, mode, rng):
    """b: coin 1 h bars, btc: {t: close}. Walk closed hours after seen[coin]."""
    seen = s.setdefault("seen_c", {})
    if coin not in seen:
        seen[coin] = [x for x in b if x["closed"]][-1]["t"]
        return
    for i in range(24, len(b)):
        x = b[i]
        if not x["closed"] or x["t"] <= seen[coin]:
            continue
        seen[coin] = x["t"]
        p = s["pos"].get(coin)
        if p:
            low = x["l"] / p["entry"] - 1
            n = (x["t"] - p["t0"]) // H + 1
            if low <= LIQ or n >= HOLD:
                ret = -1.0 if low <= LIQ else LEV * (x["c"] / p["entry"] - 1) - 2 * COST * LEV
                ret = max(ret, -1.0)
                s["pos"].pop(coin)
                s["cash"] += p["usd"] * (1 + ret)
                s["log"].append(dict(kind="sell", t=iso(x["t"] + H), coin=coin, side="long", px=x["c"] if low > LIQ else p["entry"] * (1 + LIQ),
                                     usd=p["usd"], ret=round(ret, 6), pnl=p["usd"] * ret, cost_side=COST * LEV,
                                     why="ถูกล้างพอร์ต (-18%)" if low <= LIQ else "ครบ 24 ชม."))
            else:
                p["last"] = x["c"]
            continue
        if len(s["pos"]) >= SLOTS:
            continue
        bt = btc.get(x["t"]), btc.get(x["t"] - 24 * H)
        if mode == "rule":
            go = bt[0] and bt[1] and bt[0] / bt[1] - 1 <= BTC_DROP and x["c"] / b[i - 24]["c"] - 1 <= COIN_DROP
        else:
            go = rng.random() < TWIN_P
        if not go or i + 1 >= len(b):
            continue                                        # (the forming hour is always in b, so i + 1 exists)
        usd = (s["cash"] + sum(q["usd"] for q in s["pos"].values())) / SLOTS
        usd = min(usd, s["cash"])
        s["cash"] -= usd
        s["pos"][coin] = dict(side="long", d=1, entry=b[i + 1]["o"], t0=b[i + 1]["t"], usd=usd, last=x["c"], t=iso(x["t"] + H), lev=LEV,
                              why=f"BTC {bt[0] / bt[1] - 1:+.1%} เหรียญ {x['c'] / b[i - 24]['c'] - 1:+.1%}" if mode == "rule" else "ชั่วโมงสุ่ม")
        s["log"].append(dict(kind="buy", t=iso(x["t"] + H), coin=coin, side="long", px=b[i + 1]["o"], usd=usd, why=s["pos"][coin]["why"]))


def main():
    try:
        bb = fetch("BTC")
    except Exception as e:
        print("fwd_crash5x fetch failed BTC", type(e).__name__)
        return
    btc = {x["t"]: x["c"] for x in bb}
    states = {f: load(f, label) for f, (mode, label) in ACCOUNTS.items()}
    closed = [x for x in bb if x["closed"]]
    drop = closed[-1]["c"] / btc.get(closed[-1]["t"] - 24 * H, closed[-1]["c"]) - 1
    busy = any(s["pos"] for s in states.values()) or any("seen_c" not in s for s in states.values())
    if drop > -0.04 and not busy and int(time.time()) % 21600 > 1800:
        return                                              # quiet market: skip 23 downloads; a 6 h window catches up
    rng = random.Random()
    for c in COINS:
        try:
            b = fetch(c)
        except Exception as e:
            print("fwd_crash5x fetch failed", c, type(e).__name__)
            continue
        for f, (mode, label) in ACCOUNTS.items():
            step(states[f], c, b, btc, mode, rng)
    for f in ACCOUNTS:
        save(f, states[f])


if __name__ == "__main__":
    main()
