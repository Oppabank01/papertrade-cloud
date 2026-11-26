#!/usr/bin/env python3
"""Forward paper test: resting bid at 0.985 on fiat-backed stablecoin/USDT pairs, sell at 0.999 (opened 27 Nov 2026). Fake money only.

Rule (from the 27 Nov weird-idea hunt): keep a limit buy at 0.985 on USDC, TUSD, FDUSD and USD1 against USDT on Binance spot.
A fill counts only when a 1-minute low trades strictly below 0.985 (fill min(open, 0.985)). Then a limit sell at 0.999,
filled only by a later 1-minute high strictly above 0.999; not sold in 720 h: sell at that bar's close. No stop.
A quarter of the start per pair, one position per pair, 0.15% per side. Bars: data-api.binance.vision 1 m klines (reachable
from GitHub), read from where the last run stopped, so missed cron runs still book the same fills.
Who loses: panic sellers and liquidation engines market-selling a stablecoin into a thin book.
Backtest 2018 - Nov 2026: 70 trades on 43 separate days, mean +1.16%, median +1.12%, 99% winners, without best 5 +1.10%,
halves +1.15 / +1.17, 2023-2026 +1.19% (n 23); random-time entries with the same exit -0.06%. About 0.5 fills a month
across the pairs. The risk not in the sample: a fiat-backed coin that never re-pegs (USDC hit 0.87 in Mar 2023).
  state_fwd_stablewick.json        the rule
  state_fwd_stablewick_twin.json   control: buys a random pair at a random minute (about once a week), same exit
  python3 fwd_stablewick.py"""
import json, random, time, urllib.request
from byttrade import iso, load, save

PAIRS = ["USDC", "TUSD", "FDUSD", "USD1"]
COST, SIZE, BID, ASK, HOLD, M = 0.0015, 0.25, 0.985, 0.999, 720 * 60, 60 * 1000
TWIN_P = 1 / 40320                                        # per pair-minute: about one twin buy a week over the 4 pairs
KL = "https://data-api.binance.vision/api/v3/klines?symbol={}USDT&interval=1m&startTime={}&limit=1000"
ACCOUNTS = {"state_fwd_stablewick.json": ("rule", "ตั้งรับ stablecoin ที่ 0.985 ขาย 0.999 (USDC TUSD FDUSD USD1 บน Binance, backtest 70 ไม้ เฉลี่ย +1.16% ชนะ 99%)"),
            "state_fwd_stablewick_twin.json": ("random", "ตั้งรับ stablecoin ตัวควบคุม: ซื้อนาทีสุ่ม ขาย 0.999 เหมือนกัน")}


def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())


def bars(sym, t0, now, kl=get):
    """[(t, o, h, l, c)] closed 1 m bars from t0 to now."""
    out = []
    while t0 < now - M:
        k = kl(KL.format(sym, t0))
        k = [x for x in k if x[0] + M <= now]
        if not k:
            break
        out += [(x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in k]
        t0 = k[-1][0] + M
    return out


def step(s, sym, b, rng):
    """Walk closed bars of one pair: buy, then sell. Updates s in place."""
    for t, o, h, l, c in b:
        p = s["pos"].get(sym)
        if p is None:
            hit = l < BID if s["mode"] == "rule" else rng.random() < TWIN_P
            if not hit:
                continue
            px = min(o, BID) if s["mode"] == "rule" else o
            usd = min(s["start_usd"] * SIZE, s["cash"])
            if usd <= 0:
                continue
            s["cash"] -= usd * (1 + COST)
            s["pos"][sym] = dict(side="long", coin=sym, qty=usd / px, entry=px, last=px, usd=usd, t=iso(t), t_ms=t)
            s["log"].append(dict(kind="buy", t=iso(t), coin=sym, px=px, usd=usd, why=f"{sym} ต่ำกว่า {BID}" if s["mode"] == "rule" else "นาทีสุ่ม"))
            continue                                     # the sell needs a later bar
        p["last"] = c
        if h > ASK:
            px, why = ASK, f"ขายที่ {ASK}"
        elif t - p["t_ms"] >= HOLD * M:
            px, why = c, "ครบ 30 วัน"
        else:
            continue
        s["pos"].pop(sym)
        ret = px / p["entry"] - 1
        s["cash"] += p["qty"] * px * (1 - COST)
        s["log"].append(dict(kind="sell", t=iso(t), coin=sym, px=px, usd=p["usd"], ret=round(ret, 6),
                             pnl=p["qty"] * px * (1 - COST) - p["usd"] * (1 + COST), cost_side=COST, why=why))


def main():
    now, rng = time.time() * 1000, random.Random()
    cache = {}
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        s["mode"] = mode
        last = s.setdefault("last_t", {})
        for sym in PAIRS:
            t0 = last.get(sym) or (now // M - 1) * M     # first run: start from now, no backfill
            if (sym, t0) not in cache:
                try:
                    cache[(sym, t0)] = bars(sym, int(t0), now)
                except Exception as e:
                    print("fwd_stablewick", sym, type(e).__name__)
                    cache[(sym, t0)] = None
            b = cache[(sym, t0)]
            if b is None:
                continue
            step(s, sym, b, rng)
            if b:
                last[sym] = b[-1][0] + M
        save(f, s)


if __name__ == "__main__":
    main()
