#!/usr/bin/env python3
"""Fetch Bitkub 1h bars (public tradingview/history endpoint) for every THB pair + the matching Binance spot USDT pair.
Saves bk_<SYM>.npy [t_ms,o,h,l,c,vol_base] and uses wlib.klines for Binance. Listing date = created_at from /api/v3/market/symbols."""
import sys, json, time, os, numpy as np, datetime as dt
from wlib import *
syms = get("https://api.bitkub.com/api/v3/market/symbols")["result"]
meta = {}
for s in syms:
    if s["quote_asset"] != "THB": continue
    meta[s["base_asset"]] = int(dt.datetime.fromisoformat(s["created_at"]).timestamp() * 1000)
json.dump(meta, open(f"{SCR}/bk_meta.json", "w"))
print("bitkub THB pairs", len(meta), flush=True)
now = int(time.time())
def bk(sym):
    fn = f"{SCR}/bk_{sym}.npy"
    if os.path.exists(fn): return np.load(fn)
    rows = {}; a = 1514764800
    while a < now:
        b = min(now, a + 400 * 86400)
        try: j = json.loads(raw(f"https://api.bitkub.com/tradingview/history?symbol={sym}_THB&resolution=60&from={a}&to={b}", tries=3))
        except Exception as e: print("ERR", sym, e); j = {}
        if j.get("s") == "ok":
            for k in range(len(j["t"])): rows[j["t"][k]] = (j["t"][k] * 1000, j["o"][k], j["h"][k], j["l"][k], j["c"][k], j["v"][k])
        a = b; time.sleep(0.15)
    arr = np.array([rows[k] for k in sorted(rows)], dtype=np.float64) if rows else np.zeros((0, 6))
    np.save(fn, arr); return arr
MAJ = {"BTC", "ETH", "USDT", "XRP", "DOGE", "ADA", "BNB", "SOL"}
def one(x):
    n, (s, cr) = x
    a = bk(s)
    if s == "USDT" or not len(a): print(n, s, len(a)); return
    start = 1514764800000 if s in MAJ else max(1609459200000, cr - 30 * D)
    start = min(start, max(1514764800000, cr - 30 * D)) if s in MAJ else start
    b = klines(s + "USDT", "1h", start)
    print(n, s, "bitkub", len(a), ts(a[0, 0]), "created", ts(cr), "binance", len(b), ts(b[0, 0]) if len(b) else "-", flush=True)
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(4) as ex: list(ex.map(one, enumerate(sorted(meta.items()))))
