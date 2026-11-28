#!/usr/bin/env python3
"""Forward paper test of weekly cross-sectional low-volatility long-short among big coins, opened 28 Nov 2026 by the scout.
Fake money only.

Source: runningshark/factor_study_failureprove (pre-registered study, 26 Nov 2026): of 14 factor candidates on Binance top-30
by volume (delisted coins included), X6 "low volatility" was one of only 3 not judged failed and left "to watch on paper".
Rule here: every Monday at the 00:00 UTC daily open, among the 27 coins below that have the 31 daily closes before that
Monday, rank by the stdev of the last 30 close-to-close returns. Long the third with the lowest stdev, short the third
with the highest, half the account per side, equal weight, held to next Monday's open. A coin that stays on the same side
is not sold and rebought (no cost) but still books one trade per week; 0.35% per side on coins that change.
Scout backtest 2019-2026 (/tmp/scout_1121/bt.py, Binance spot daily, coins listed today, so survivorship bias against the
short leg): 381 weeks, pre-cost -0.22%/week, after cost -0.34% (median +0.11%, win 52%), 2024+ 151 weeks +0.09%/week;
random long-short picks (paying full turnover) -0.49%; permutation 200 (best of MAX and low-vol, pre-cost) p 0.891.
Not a pass; opened because the user wants weak ideas tried live.
Numbers I chose: the 27 coins (same list as fwd_xsmom, not top-30 by volume), 30-day window and thirds from the study,
at least 12 eligible coins, no funding (spot paper short), 0.35% per side instead of the study's 0.10%.
  state_fwd_lowvol.json       the rule
  state_fwd_lowvol_twin.json  control: random thirds long and short each Monday, same schedule and cost
  python3 fwd_lowvol.py"""
import random, statistics as st, time
import byttrade as B
from byttrade import iso, load, save

COST, LOOK, MINU = 0.0035, 30, 12
DAY = 86400 * 1000
COINS = "BTC ETH BNB SOL XRP ADA DOGE TRX AVAX LINK DOT LTC BCH XLM ATOM ETC FIL NEAR UNI AAVE HBAR ICP APT ARB OP SUI INJ".split()
ACCOUNTS = {"state_fwd_lowvol.json": ("rule", "low-vol ข้ามเหรียญ: ทุกจันทร์ long 1 ใน 3 ที่ผันผวน 30 วันต่ำสุด short 1 ใน 3 ที่สูงสุด จาก 27 เหรียญใหญ่ (backtest 381 สัปดาห์ หลังหัก -0.34%/สัปดาห์ ปี 2024+ +0.09% p 0.89 ตัวแฝดสุ่ม -0.49%)"),
            "state_fwd_lowvol_twin.json": ("random", "low-vol ตัวควบคุม: สุ่ม 1 ใน 3 long และ 1 ใน 3 short ทุกจันทร์ ต้นทุนเดียวกัน")}


def signal(cl):
    return st.pstdev([cl[i] / cl[i - 1] - 1 for i in range(1, len(cl))])


def fetch_daily(sym):
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=1d")
    try:
        return B.fetch(sym)
    finally:
        B.URL = old


def mondays_after(t0, m):
    return sorted(d for d in m["BTC"] if d > t0 and (d // DAY + 3) % 7 == 0)


def sides(m, d, mode, rng, sig=signal):
    """(longs, shorts) for Monday d; m = {coin: {t: bar}}. Uses only the 31 closes before d and the open of d."""
    el = {}
    for c, x in m.items():
        if d in x and all(d - j * DAY in x for j in range(1, LOOK + 2)):
            el[c] = sig([x[d - j * DAY]["c"] for j in range(LOOK + 1, 0, -1)])
    if len(el) < MINU:
        return [], []
    k = len(el) // 3
    order = sorted(el, key=lambda c: (el[c], c))
    if mode == "rule":
        return order[:k], order[-k:]
    order = sorted(el); rng.shuffle(order)
    return order[:k], order[k:2 * k]


def week(s, m, d, mode, rng, sig=signal):
    lo, sh = sides(m, d, mode, rng, sig)
    want = {**{c: 1 for c in lo}, **{c: -1 for c in sh}}
    for c, p in list(s["pos"].items()):
        if d not in m.get(c, {}):
            continue                                  # no price for this coin today: keep holding, try next week
        price = m[c][d]["o"]
        keep = want.get(c) == p["d"]
        out = abs(p["qty"]) * price * COST if not keep else 0.0
        ret = (price / p["entry"] - 1) * p["d"]
        s["pos"].pop(c)
        s["cash"] += p["qty"] * price - out
        s["log"].append(dict(kind="sell", t=iso(d), coin=c, side=p["side"], px=price, usd=p["usd"], ret=round(ret, 6),
                             pnl=p["usd"] * ret - out, cost_side=COST, why="ครบสัปดาห์" + ("" if keep else " เปลี่ยนฝั่ง/หลุดอันดับ")))
    s["last"] = s.get("last", {})
    new = [(c, dd) for c, dd in want.items() if c not in s["pos"]]
    if not new or not lo:
        s["last"] = {c: p["d"] for c, p in s["pos"].items()}
        return
    eq = s["cash"] + sum(p["qty"] * m[c][d]["o"] if d in m.get(c, {}) else p["qty"] * p["last"] for c, p in s["pos"].items())
    usd = eq * 0.5 / len(lo)
    for c, dd in new:
        price = m[c][d]["o"]
        cost = usd * COST if s["last"].get(c) != dd else 0.0
        s["cash"] += (-usd if dd > 0 else usd) - cost
        why = ("ผันผวน 30 วันต่ำ" if dd > 0 else "ผันผวน 30 วันสูง") if mode == "rule" else "สุ่มฝั่ง"
        s["pos"][c] = dict(side="long" if dd > 0 else "short", d=dd, qty=dd * usd / price, entry=price, last=price, usd=usd, t=iso(d), why=why)
        s["log"].append(dict(kind="buy", t=iso(d), coin=c, side=s["pos"][c]["side"], px=price, usd=usd, why=why))
    s["last"] = {c: p["d"] for c, p in s["pos"].items()}


def step(s, bars, mode, rng, sig=signal):
    """bars: {coin: daily bars from byttrade.fetch}; a Monday is handled once its bar exists (its open is final)."""
    m = {c: {x["t"]: x for x in b} for c, b in bars.items() if b}
    if "BTC" not in m:
        return
    if s.get("seen") is None:
        s["seen"] = max(m["BTC"])
        return
    for d in mondays_after(s["seen"], m):
        week(s, m, d, mode, rng, sig)
        s["seen"] = d
    for c, p in s["pos"].items():
        if c in bars and bars[c]:
            p["last"] = bars[c][-1]["c"]


def run(accounts, name, sig=signal):
    states = {f: load(f, label) for f, (mode, label) in accounts.items()}
    now = time.time() * 1000
    last_monday = (now // DAY - (now // DAY + 3) % 7) * DAY
    if all(s.get("seen") is not None and s["seen"] >= last_monday for s in states.values()) and int(now / 1000) % 21600 > 1800:
        return                                         # nothing new: skip the 27 downloads (marks still refresh about every 6 h)
    bars = {}
    for c in COINS:
        try:
            bars[c] = fetch_daily(c + "USDT")
        except Exception as e:
            print(name, "fetch failed", c, type(e).__name__)
            return                                     # the ranking needs every coin: skip the run rather than rank a subset
    rng = random.Random()
    for f, (mode, label) in accounts.items():
        step(states[f], bars, mode, rng, sig)
        save(f, states[f])


if __name__ == "__main__":
    run(ACCOUNTS, "fwd_lowvol")
