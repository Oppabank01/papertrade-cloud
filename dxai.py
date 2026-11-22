#!/usr/bin/env python3
"""Forward paper test built from DXRG's "What LLM Trading Agents Actually Do in Production" (arXiv 2609.05663, Sep 2026),
opened 23 Nov 2026 because the user asked to try weak ideas too. Fake money only.

The paper's LLM agents (Hyperliquid perps, Jun-Aug 2026) picked symbols shown on a top-3 "gainers" leaderboard 1.75x
more than rank 4 (p.6, Fig. 3), over-entered chase states above +0.75% in 1h (p.11), and a fixed 2%/4% stop/target
bracket beat every discretionary exit (+39.0 bps per position, p.10 s6.2). The LLM entry is replaced here by a stated
rule that copies that behaviour; the paper itself says chase entries lose (forward 4h -6.9 bps, p.11), so this is a
test of "the bracket rescues the crowd's entry", not an expected winner.
Backtest before opening (Binance 1h, Nov 2024 - Nov 2026, 15 coins, 0.35%/side, /private/tmp/claude-501/arxiv_dxai/
analyse.py): 3,453 trades, win 31.7%, mean -82.5 bps, median -269.3 bps (gross -12.5 bps); random entries with the same
bracket -76.5 bps (rule beat 7.5% of 200 seeds); permutation p 0.821. A loser: opened only because the user asked.

On closed 1h Binance bars of 15 fixed coins: rank by 24h return; each of the top 3 whose last 1h bar rose more than
0.75% -> long at the next open. Stop -2%, target +4% from the entry, closed at the 24th bar's close if neither hit
(the 24 h cap, the 24 h ranking window, the coin list picked today and reading 2%/4% as price moves rather than
leveraged returns are my choices: the paper does not state them).
Gap through the stop fills at the open; a bar touching both counts as the stop. At most 3 positions, one per coin,
a quarter of the account value each, 0.35% per side.
  state_dxai.json       the rule
  state_dxai_twin.json  control: random entries (1 in 76 free coin-bars, the rule's rate) on the same coins, same bracket
Acts only when a new 1h bar has closed; a failed fetch of any coin means no action that run.  python3 dxai.py"""
import json, random, time, urllib.request
from byttrade import iso, load, save

H1, COST, TWIN_P = 3600 * 1000, 0.0035, 1 / 76
STOP, TGT, HOLD, CHASE, TOP, MAXPOS, LOOK = 0.02, 0.04, 24, 0.0075, 3, 3, 24
SYMS = [c + "USDT" for c in "BTC ETH SOL XRP DOGE BNB ADA AVAX LINK LTC DOT BCH NEAR SUI TRX".split()]
URL = "https://data-api.binance.vision/api/v3/klines?symbol={}&interval=1h&limit=1000"
ACCOUNTS = {"state_dxai.json": ("rule", "DXAI ไล่ top 3 ขึ้นแรง 24 ชม. ที่แท่ง 1 ชม. ล่าสุดขึ้นเกิน 0.75% stop 2% เป้า 4% ถือไม่เกิน 24 ชม. (จากเปเปอร์ LLM เทรด)"),
            "state_dxai_twin.json": ("random", "DXAI ตัวควบคุม: เข้าสุ่มเหรียญเดียวกัน stop 2% เป้า 4% ถือไม่เกิน 24 ชม.")}


def fetch(sym):
    now = time.time() * 1000
    raw = json.loads(urllib.request.urlopen(urllib.request.Request(URL.format(sym), headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())
    return [dict(t=k[0], o=float(k[1]), h=float(k[2]), l=float(k[3]), c=float(k[4]), closed=k[6] < now) for k in raw]


def exit_px(p, x):
    """Exit price for one closed bar, or None. Order: gap stop, stop, gap target, target, 24 h cap."""
    o, h, l = x["o"], x["h"], x["l"]
    if o <= p["stop"]:
        return o, "stop (เปิดทะลุ)"
    if l <= p["stop"]:
        return p["stop"], "stop 2%"
    if h >= p["tgt"]:
        return max(p["tgt"], o), "ถึงเป้า 4%"
    if x["t"] >= p["entry_t"] + (HOLD - 1) * H1:
        return x["c"], "ครบ 24 ชม."
    return None


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px - p["qty"] * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def picks(idx, bars, mode, rng, free):
    """Coins to buy at this bar, in order. idx: sym -> index of the bar that just closed."""
    if mode == "rule":
        r24 = {m: bars[m][i]["c"] / bars[m][i - LOOK]["c"] - 1 for m, i in idx.items()}
        top = sorted(r24, key=lambda m: -r24[m])[:TOP]
        return [m for m in top if m in free and bars[m][idx[m]]["c"] / bars[m][idx[m] - 1]["c"] - 1 > CHASE]
    return [m for m in SYMS if m in idx and m in free and rng.random() < TWIN_P]


def step(s, cache, mode, rng):
    """cache: sym -> bars (oldest first, the last may be forming). Walks every 1h bar closed in all coins after s['seen']."""
    pos = {m: {x["t"]: i for i, x in enumerate(b)} for m, b in cache.items()}
    common = sorted(set.intersection(*({x["t"] for x in b if x["closed"]} for b in cache.values())))
    if s.get("seen") is None:
        s["seen"] = common[-1]
        return
    for t in common:
        idx = {m: pos[m][t] for m in cache}
        if t <= s["seen"] or any(i + 1 >= len(cache[m]) or i < LOOK for m, i in idx.items()):
            continue
        s["seen"] = t
        exited = set()
        for m in list(s["pos"]):
            p = s["pos"][m]
            if t >= p["entry_t"]:
                hit = exit_px(p, cache[m][idx[m]])
                if hit:
                    close(s, m, hit[0], t + H1, hit[1]); exited.add(m)
        free = {m for m in cache if m not in s["pos"] and m not in exited}
        eq = s["cash"] + sum(p["qty"] * cache[m][idx[m]]["c"] for m, p in s["pos"].items())
        for m in picks(idx, cache, mode, rng, free):
            usd = min(eq / 4, s["cash"] / (1 + COST))   # a quarter of the account value, so it shrinks after losses
            if len(s["pos"]) >= MAXPOS or usd < s["start_usd"] / 100:
                break
            nxt = cache[m][idx[m] + 1]
            e = nxt["o"]
            why = "ติด top 3 ขึ้น 24 ชม. + แท่ง 1 ชม. ขึ้นเกิน 0.75%" if mode == "rule" else "สุ่มเข้า"
            s["cash"] -= usd * (1 + COST)
            s["pos"][m] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, stop=e * (1 - STOP), tgt=e * (1 + TGT),
                               entry_t=nxt["t"], t=iso(nxt["t"]), why=why)
            s["log"].append(dict(kind="buy", t=iso(nxt["t"]), coin=m[:-4], side="long", px=e, usd=usd, why=why))
    for m, p in s["pos"].items():
        p["last"] = cache[m][-1]["c"]


def main():
    states = {f: load(f, label) for f, (mode, label) in ACCOUNTS.items()}
    seen = [s.get("seen") for s in states.values()]
    if all(seen) and time.time() * 1000 < min(seen) + 2 * H1 + 60_000:   # no new 1h bar has closed yet
        return
    cache = {}
    for m in SYMS:
        try:
            cache[m] = fetch(m)
        except Exception as e:
            print("dxai fetch failed", m, type(e).__name__)
            return
    rng = random.Random()
    for f, (mode, _) in ACCOUNTS.items():
        step(states[f], cache, mode, rng)
        save(f, states[f])


if __name__ == "__main__":
    main()
