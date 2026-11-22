#!/usr/bin/env python3
"""Forward paper test of RohOnChain's "2-candle bias" (X, 21 Nov 2026), opened 23 Nov although the backtest lost
(BTC/ETH/SOL 2017-2026 win 40-47%, -0.2 to -0.47R per trade; Projects/PaperTrade/backtests/twocandle_rohonchain.py),
because the user asked to try weak ideas too. Fake money only.

At a session-opening 4h bar (00, 08, 12 UTC): if yesterday's daily candle and the 4h candle that just closed have the
same colour, enter that way at the open. Stop beyond the signal candle, target 1:1, closed at the close of the 3rd bar
(12 h). Stop counts first when a bar touches both. BTC, ETH, SOL, one third of the start each, 0.1% per side.
Settings chosen by me from the backtest grid (session filter on, hold 3 bars).  python3 twocandle.py run"""
import json, os, sys, time, urllib.request
from collections import defaultdict
from byttrade import iso, load, save, H4, DAY, RATE, THB

FILE, COST, HOLD, SESSIONS = "state_twoc.json", 0.001, 3, {0, 8, 12}
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
LABEL = "2 แท่ง RohOnChain: แท่งวันเมื่อวานกับ 4 ชม. ล่าสุดสีเดียวกันตอนเปิดเซสชัน เป้า 1:1 ถือ 12 ชม. (backtest แพ้ เปิดลองเผื่อฟลุค)"


def colors(b):
    days = defaultdict(list)
    for x in b:
        days[x["t"] // DAY].append(x)
    return {k: (v[-1]["c"] > v[0]["o"]) - (v[-1]["c"] < v[0]["o"]) for k, v in days.items() if len(v) == 6}


def step(s, sym, bars):
    """Walk closed bars after s['seen'][sym]; the last bar may be forming."""
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    col = colors([x for x in bars if x["closed"]])
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            d = p["d"]
            if (x["l"] <= p["stop"]) if d > 0 else (x["h"] >= p["stop"]):
                close(s, sym, p["stop"], x["t"] + H4, "stop")
            elif (x["h"] >= p["tgt"]) if d > 0 else (x["l"] <= p["tgt"]):
                close(s, sym, p["tgt"], x["t"] + H4, "ถึงเป้า 1:1")
            elif x["t"] >= p["entry_t"] + (HOLD - 1) * H4:
                close(s, sym, x["c"], x["t"] + H4, "ครบ 12 ชม.")
        if sym in s["pos"]:
            continue
        nxt = bars[i + 1]
        if (nxt["t"] // 3_600_000) % 24 not in SESSIONS:
            continue
        d, f = col.get(x["t"] // DAY - 1), (x["c"] > x["o"]) - (x["c"] < x["o"])
        if not d or d != f:
            continue
        e, stop = nxt["o"], (x["l"] if d > 0 else x["h"])
        if (e - stop) * d <= 0:
            continue
        usd = s["start_usd"] / 3
        if s["cash"] < usd * (1 + COST) and d > 0:
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd, stop=stop,
                             tgt=e + (e - stop), entry_t=nxt["t"], t=iso(nxt["t"]), why="วันเมื่อวานกับแท่ง 4 ชม. สีเดียวกัน")
        s["log"].append(dict(kind="buy", t=iso(nxt["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd,
                             why="วันเมื่อวานกับแท่ง 4 ชม. สีเดียวกัน"))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def main():
    import byttrade
    s = load(FILE, LABEL)
    s.pop("seen", None) if isinstance(s.get("seen"), (int, type(None))) else None
    for sym in SYMS:
        try:
            bars = byttrade.fetch(sym)
        except Exception as e:
            print("twocandle fetch failed", sym, type(e).__name__)
            continue
        step(s, sym, bars)
    save(FILE, s)


if __name__ == "__main__":
    main()
