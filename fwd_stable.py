#!/usr/bin/env python3
"""Forward paper test: buy BTC / ETH after a jump in total USD stablecoin supply (new money arriving), opened 23 Nov 2026.
Fake money only.

Data: DefiLlama stablecoincharts/all (public, no key), daily total circulating peggedUSD. Rule: 7-day supply growth on
snapshot day d, as a z-score against the previous 90 days of 7-day growth, above 1.5 -> buy at the open of day d+2 (the
snapshot is stamped 00:00 UTC of day d; one extra day so it is surely published), sell at the open 10 days later; no new
entry while holding. Half the start per coin, 0.35% per side. Settings chosen by me (7 d, z 1.5, hold 10) from 12 tried.
Backtest 2020-2026 after costs: BTC 49 trades +3.08%/trade (random entry days p 0.003), ETH 49 +3.92% p 0.003; better than
random days in most years including 2026 (BTC +1.2% vs -1.5%), worse in 2025 (BTC -2.0% vs -0.7%). About 7 trades a year.
  state_fwd_stable.json       the rule
  state_fwd_stable_twin.json  control: random days (1 in 40 free days), same 10-day hold
  python3 fwd_stable.py"""
import json, random, urllib.request
import byttrade as B
from byttrade import iso, load, save

COST, K, LOOK, Z, HOLD, TWIN_P = 0.0035, 7, 90, 1.5, 10, 1 / 40
DAY = 86400 * 1000
SYMS = ["BTCUSDT", "ETHUSDT"]
URL = "https://stablecoins.llama.fi/stablecoincharts/all"
ACCOUNTS = {"state_fwd_stable.json": ("rule", "ซื้อ BTC ETH หลัง stablecoin ถูกพิมพ์เพิ่มผิดปกติ (โต 7 วัน z>1.5 จาก 90 วัน) ถือ 10 วัน (backtest +3.1%/ไม้ p 0.003 ปีละราว 7 ไม้)"),
            "state_fwd_stable_twin.json": ("random", "stablecoin ตัวควบคุม: ซื้อวันสุ่ม ถือ 10 วันเหมือนกัน")}


def fetch_daily(sym):
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=1d")
    try:
        return B.fetch(sym)
    finally:
        B.URL = old


def fetch_supply():
    raw = json.loads(urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())
    return {int(x["date"]) // 86400: x["totalCirculatingUSD"].get("peggedUSD", 0) for x in raw}


def zscore(sup, d):
    ch = lambda x: sup[x] / sup[x - K] - 1 if x in sup and sup.get(x - K) else None
    w = [c for c in (ch(x) for x in range(d - LOOK, d)) if c is not None]
    c = ch(d)
    if c is None or len(w) < LOOK * 0.9:
        return None
    m = sum(w) / len(w)
    sd = (sum((x - m) ** 2 for x in w) / len(w)) ** 0.5
    return (c - m) / sd if sd > 0 else None


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px * (1 - COST)
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, sup, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        nxt, p = bars[i + 1], s["pos"].get(sym)
        if p and nxt["t"] >= p["exit_t"]:
            close(s, sym, nxt["o"], nxt["t"], "ครบ 10 วัน")
        if sym in s["pos"]:
            continue
        if mode == "rule":
            z = zscore(sup, x["t"] // DAY - 1)        # bar of day d+1 just closed -> snapshot day d, buy at the open of d+2
            go = z is not None and z > Z
        else:
            go = rng.random() < TWIN_P
        usd = s["start_usd"] / 2
        if not go or s["cash"] < usd * (1 + COST):
            continue
        e = nxt["o"]
        s["cash"] -= usd * (1 + COST)
        why = f"stablecoin โต 7 วัน z {z:+.1f}" if mode == "rule" else "วันสุ่ม"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=nxt["t"], exit_t=nxt["t"] + HOLD * DAY,
                             t=iso(nxt["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nxt["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, bars = random.Random(), {}
    for sym in SYMS:
        try:
            bars[sym] = fetch_daily(sym)
        except Exception as e:
            print("fwd_stable fetch failed", sym, type(e).__name__)
    states = {f: load(f, label) for f, (mode, label) in ACCOUNTS.items()}
    fresh = any(not isinstance(s.get("seen"), dict) or sym not in s["seen"] or [x for x in b if x["closed"]][-1]["t"] > s["seen"][sym]
                for s in states.values() for sym, b in bars.items())
    if not fresh:
        return                                          # no new daily bar: skip the 3 MB supply download
    try:
        sup = fetch_supply()
    except Exception as e:
        print("fwd_stable supply fetch failed", type(e).__name__)
        return
    for f, (mode, label) in ACCOUNTS.items():
        s = states[f]
        if not isinstance(s.get("seen"), dict):
            s["seen"] = {}
        for sym, b in bars.items():
            step(s, sym, b, sup, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
