#!/usr/bin/env python3
"""Forward paper test of XSectRsiStrategy (Moontaehyeon01/tradingAI, a Freqtrade futures bot the author runs live), opened
28 Nov 2026 by the scout. Fake money only.

Rule, on Binance daily bars of the 18 coins below: at every 00:00 UTC open, rank the coins by RSI14 (Cutler, plain means of
the last 14 close-to-close moves, as in the repo) of the closes through yesterday. Long the first 3 of the ranking that are
not cooling down, short the last 3, at that open. Exit at an open after 3 days, or after 4 if the coin is still in the
same-side top 3 that day. Take profit at 2.0 x the stdev of its last 180 three-day returns (clipped 5%..100%, fixed at
entry), safety stop 60%, both checked on the daily high/low (a gap through fills at the open, both touched = stop).
After any exit the coin cannot be re-entered for 48 h. One position per coin, a sixth of the start each, 0.35% per side.
Scout backtest 2019-07 to 2026-11 (bt.py in /tmp/scout_0801, 18 coins listed today, so survivorship bias): 4,652 trades,
pre-cost +0.34%/trade, after cost -0.36% (long +0.08%, short -0.82%), negative in 7 of 8 years; random picks with the
same exits -0.64% (best of 20 seeds -0.52%); permutation 200 p 0.030 (pre-cost). Not a pass; opened because the user
wants weak ideas tried live.
Numbers I chose: XMR dropped (not on Binance spot), 1x without the repo's 2x leverage, funding and BTC-vol sizing; the
take profit is fixed at entry instead of recomputed daily; the 5%/100% clip is from the repo comment; at least 8 ranked
coins needed; the first 3 non-cooling coins of the ranking are the target set and a coin already held counts as one of them.
  state_fwd_xsrsi.json       the rule
  state_fwd_xsrsi_twin.json  control: random eligible coins each day for the free slots, same exits
  python3 fwd_xsrsi.py"""
import random, statistics as st
import byttrade as B
from byttrade import iso, load, save

COINS = "BTC ETH SOL XRP ZEC DOGE ARB UNI T BNB SUI FIL ADA PEPE EGLD LINK NEAR AAVE".split()
DAY = 86400 * 1000
K, HOLD, MAXH, TPM, TPW, TPMIN, TPMAX, STOP, COST, MINU = 3, 3, 4, 2.0, 180, 0.05, 1.0, 0.60, 0.0035, 8
ACCOUNTS = {"state_fwd_xsrsi.json": ("rule", "จัดอันดับ RSI14 ข้าม 18 เหรียญ ทุกวัน long 3 บน short 3 ล่าง ถือ 3-4 วัน (backtest 2019-2026 4,652 ไม้ หลังหัก -0.36% ต่อไม้ ก่อนหัก +0.34% p 0.030 ตัวแฝดสุ่ม -0.64%)"),
            "state_fwd_xsrsi_twin.json": ("random", "จัดอันดับ RSI ตัวควบคุม: สุ่มเหรียญเข้าช่องว่างทุกวัน ออกแบบเดียวกัน")}


def fetch_daily(sym):
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=1d")
    try:
        return B.fetch(sym)
    finally:
        B.URL = old


def rsi(c):
    d = [c[i] - c[i - 1] for i in range(len(c) - 14, len(c))]
    g, l = sum(max(x, 0) for x in d) / 14, sum(max(-x, 0) for x in d) / 14
    if g == 0 and l == 0:
        return None
    return 100.0 if l == 0 else 100 - 100 / (1 + g / l)


def tp_of(c):
    r = [c[i] / c[i - 3] - 1 for i in range(3, len(c))][-TPW:]
    if len(r) < 60:
        return None
    return min(max(TPM * st.stdev(r), TPMIN), TPMAX)


def close(s, c, px, t, why):
    p = s["pos"].pop(c)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=c, side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def day_open(s, m, t, mode, rng):
    sc = {}
    for c in COINS:
        d = m.get(c, {})
        if t in d and t - DAY in d:
            h = [x["c"] for x in sorted(d.values(), key=lambda x: x["t"]) if x["t"] < t]
            if len(h) >= 15:
                v = rsi(h)
                if v is not None:
                    sc[c] = (v, h)
    order = sorted(sc, key=lambda c: -sc[c][0]) if len(sc) >= MINU else []
    top, bot = order[:K], order[::-1][:K]
    for c in list(s["pos"]):
        p = s["pos"][c]
        if t not in m.get(c, {}):
            continue
        age = (t - p["entry_t"]) // DAY
        if age >= MAXH or (age >= HOLD and c not in (top if p["d"] > 0 else bot)):
            close(s, c, m[c][t]["o"], t, "ครบ %d วัน" % age)
            s["free"][c] = t + 2 * DAY
    if not order:
        return
    for side, lst in ((1, order), (-1, order[::-1])):
        n = sum(1 for p in s["pos"].values() if p["d"] == side)
        if mode == "rule":
            cands = [c for c in lst if s["free"].get(c, 0) <= t][:K]
        else:
            cands = [c for c in order if s["free"].get(c, 0) <= t and c not in s["pos"]]
            rng.shuffle(cands)
        for c in cands:
            if n >= K:
                break
            if c in s["pos"]:
                continue
            e, usd = m[c][t]["o"], s["start_usd"] / 6
            if side > 0 and s["cash"] < usd * (1 + COST):
                continue
            s["cash"] += (-usd if side > 0 else usd) - usd * COST
            why = ("RSI14 อันดับต้น %.1f" if side > 0 else "RSI14 อันดับท้าย %.1f") % sc[c][0] if mode == "rule" else "สุ่มเหรียญ"
            s["pos"][c] = dict(side="long" if side > 0 else "short", d=side, qty=side * usd / e, entry=e, last=e, usd=usd,
                               entry_t=t, t=iso(t), tp=tp_of(sc[c][1]), why=why)
            s["log"].append(dict(kind="buy", t=iso(t), coin=c, side=s["pos"][c]["side"], px=e, usd=usd, why=why))
            n += 1


def day_bar(s, m, t):
    for c in list(s["pos"]):
        if t not in m.get(c, {}):
            continue
        x, p = m[c][t], s["pos"][c]
        d, e = p["d"], p["entry"]
        stop, tgt = e * (1 - d * STOP), (None if p["tp"] is None else e * (1 + d * p["tp"]))
        if d > 0:
            px = x["o"] if x["o"] <= stop else stop if x["l"] <= stop else (max(tgt, x["o"]) if tgt and x["h"] >= tgt else None)
        else:
            px = x["o"] if x["o"] >= stop else stop if x["h"] >= stop else (min(tgt, x["o"]) if tgt and x["l"] <= tgt else None)
        if px is not None:
            close(s, c, px, t + DAY, "stop 60%" if (px - e) * d < 0 else "ถึงเป้า %.0f%%" % (p["tp"] * 100))
            s["free"][c] = t + 3 * DAY


def step(s, bars, mode, rng):
    """bars: {coin: daily bars from byttrade.fetch}. Opens are handled as soon as the day's bar exists, highs/lows once it closed."""
    m = {c: {x["t"]: x for x in b} for c, b in bars.items()}
    grid = sorted({t for d in m.values() for t in d})
    done = [t for t in grid if all(m[c][t]["closed"] for c in m if t in m[c])]
    if not done:
        return
    s.setdefault("free", {})
    if s.get("seen") is None:
        s["seen"] = s["opened"] = done[-1]
        return
    for t in grid:
        if t > s["opened"]:
            day_open(s, m, t, mode, rng)
            s["opened"] = t
        if t in done and t > s["seen"]:
            day_bar(s, m, t)
            s["seen"] = t
    for c, p in s["pos"].items():
        if c in bars:
            p["last"] = bars[c][-1]["c"]


def main():
    bars = {}
    for c in COINS:
        try:
            bars[c] = fetch_daily(c + "USDT")
        except Exception as e:
            print("fwd_xsrsi fetch failed", c, type(e).__name__)
            return                                     # the ranking needs every coin: skip the run rather than rank a subset
    rng = random.Random()
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        step(s, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
