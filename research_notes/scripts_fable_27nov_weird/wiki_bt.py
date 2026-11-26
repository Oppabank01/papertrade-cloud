#!/usr/bin/env python3
"""Idea 4: Wikipedia pageview spikes (Wikimedia REST, keyless, daily, user agent only) as a top/bottom signal.
Signal day D: z of log(views) vs the prior 30 days >= Z. Pageviews for D are published during D+1, so entry = open of day D+2 (UTC).
Trade on Binance spot daily bars, hold 1/3/7 days, stop 15% checked first. Cost 0.15%/side. Cooldown = hold. Control: same coin, random days."""
import sys, urllib.parse, numpy as np
from wlib import *
ART = {"BTC": "Bitcoin", "ETH": "Ethereum", "DOGE": "Dogecoin", "SOL": "Solana_(blockchain_platform)", "SHIB": "Shiba_Inu_(cryptocurrency)", "XRP": "XRP_Ledger",
       "ADA": "Cardano_(blockchain_platform)", "LTC": "Litecoin", "LINK": "Chainlink_(blockchain_oracle)", "DOT": "Polkadot_(blockchain_platform)",
       "AVAX": "Avalanche_(blockchain_platform)", "TRX": "Tron_(blockchain)", "BCH": "Bitcoin_Cash", "XLM": "Stellar_(payment_network)", "XMR": "Monero",
       "BNB": "Binance", "UNI": "Uniswap", "ZEC": "Zcash", "ETC": "Ethereum_Classic", "XTZ": "Tezos", "ALGO": "Algorand_(blockchain)", "FIL": "Filecoin",
       "NEAR": "Near_Protocol", "POL": "Polygon_(blockchain)", "DASH": "Dash_(cryptocurrency)", "HBAR": "Hedera_(distributed_ledger)", "ICP": "Internet_Computer",
       "AAVE": "Aave", "TON": "TON_(blockchain)", "PEPE": "Pepe_(cryptocurrency)", "TRUMP": "$Trump", "EOS": "EOS.IO", "LUNC": "Terra_(blockchain)", "ATOM": "Cosmos_(blockchain)"}
V = {}; K = {}
for c, art in ART.items():
    try: j = get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{urllib.parse.quote(art, safe='')}/daily/20150701/20261125", tries=2)
    except Exception as e: print(c, art, "no data", e); continue
    it = j.get("items", [])
    if len(it) < 400: print(c, art, "short", len(it)); continue
    import calendar
    v = {calendar.timegm(time.strptime(x["timestamp"][:8], "%Y%m%d")) * 1000: x["views"] for x in it}
    sym = {"POL": "MATICUSDT"}.get(c, c + "USDT")
    a = klines(sym, "1d", 0)
    if c == "POL": a = np.vstack([a, klines("POLUSDT", "1d", 0)]) if len(klines("POLUSDT", "1d", 0)) else a
    if len(a) < 300: print(c, "no klines"); continue
    V[c] = v; K[c] = a
    print(c, art, "views days", len(v), "median", int(np.median(list(v.values()))), "bars", len(a), ts(a[0, 0]), flush=True)
def events(c, Z, direction, minviews=300):
    a = K[c]; v = V[c]; tidx = {int(t): i for i, t in enumerate(a[:, 0])}; ev = []
    days = sorted(v)
    lv = {d: math.log(max(1, v[d])) for d in days}
    for d in days:
        prior = [lv[d - k * D] for k in range(1, 31) if d - k * D in lv]
        if len(prior) < 25 or v[d] < minviews: continue
        z = (lv[d] - np.mean(prior)) / max(0.15, np.std(prior))
        if z < Z: continue
        i = tidx.get(d)
        if i is None or i < 1 or i + 2 >= len(a): continue
        ret = a[i, 4] / a[i - 1, 4] - 1          # price change on the spike day itself
        if direction == "up" and ret <= 0.03: continue
        if direction == "dn" and ret >= -0.03: continue
        ev.append(i + 2)
    return ev
rows = []
for Z in (2, 3, 4):
    for direction in ("any", "up", "dn"):
        for hold in (1, 3, 7):
            for side in (1, -1):
                tr = []; ctl_m = []; meta = []
                for c in K:
                    last = -1
                    for i in events(c, Z, direction):
                        if i <= last: continue
                        x = sim(K[c], i, side, hold, 0.15)
                        if x: tr.append((x[0], x[1])); meta.append(c); last = x[2]
                st = stats(tr)
                if st["n"] < 8: print(f"wiki Z{Z} {direction} hold{hold} side{side} n={st['n']}"); continue
                cm = []
                for k in range(100):
                    rng = np.random.default_rng(k); rr = []
                    for c in meta:
                        x = sim(K[c], int(rng.integers(40, len(K[c]) - hold - 1)), side, hold, 0.15)
                        if x: rr.append(x[1])
                    cm.append(np.mean(rr) * 100)
                cm = np.array(cm)
                print(fmt(f"wiki Z>={Z} dir={direction} hold{hold}d {'LONG' if side > 0 else 'SHORT'}", st, dict(mean=cm.mean(), med=float('nan'), p=(cm >= st['mean']).mean())), f"coins={len(set(meta))}", flush=True)
# BTC/ETH only + level of attention (slow signal): views 7d avg vs 90d avg
print("\n=== per-coin, Z>=3 any, hold 7, LONG ===")
for c in K:
    tr = []; last = -1
    for i in events(c, 3, "any"):
        if i <= last: continue
        x = sim(K[c], i, 1, 7, 0.15)
        if x: tr.append((x[0], x[1])); last = x[2]
    st = stats(tr)
    if st["n"] >= 8: print(fmt(c, st))
