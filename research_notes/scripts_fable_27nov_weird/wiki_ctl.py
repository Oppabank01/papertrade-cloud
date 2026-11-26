#!/usr/bin/env python3
"""Follow-up for the only wiki row with a positive mean: LONG after a pageview spike (z>=3) on a day the coin rose >3%.
Is the pageview spike adding anything beyond 'the coin had a +3% day'? Price-only matched control = same coins, every day with a >3% rise
and NO spike, same entry lag (open of D+2), same hold/stop/cost. Also year by year and the share of profit from the top trades."""
import sys, urllib.parse, calendar, numpy as np
from wlib import *
ART = {"BTC": "Bitcoin", "ETH": "Ethereum", "DOGE": "Dogecoin", "SOL": "Solana_(blockchain_platform)", "SHIB": "Shiba_Inu_(cryptocurrency)", "XRP": "XRP_Ledger",
       "ADA": "Cardano_(blockchain_platform)", "LTC": "Litecoin", "LINK": "Chainlink_(blockchain_oracle)", "DOT": "Polkadot_(blockchain_platform)",
       "XLM": "Stellar_(payment_network)", "XMR": "Monero", "BNB": "Binance", "UNI": "Uniswap", "ZEC": "Zcash", "ETC": "Ethereum_Classic", "XTZ": "Tezos",
       "FIL": "Filecoin", "AAVE": "Aave", "TON": "TON_(blockchain)", "TRUMP": "$Trump", "EOS": "EOS.IO", "LUNC": "Terra_(blockchain)"}
sig = []; ctl = []
for c, art in ART.items():
    j = get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{urllib.parse.quote(art, safe='')}/daily/20150701/20261125")
    v = {calendar.timegm(time.strptime(x["timestamp"][:8], "%Y%m%d")) * 1000: x["views"] for x in j["items"]}
    a = klines(c + "USDT", "1d", 0); lv = {d: math.log(max(1, x)) for d, x in v.items()}
    for hold in (3, 7):
        ls = -1; lc = -1
        for i in range(31, len(a) - 2):
            d = int(a[i, 0])
            if d not in v or a[i, 4] / a[i - 1, 4] - 1 <= 0.03: continue
            p = [lv[d - k * D] for k in range(1, 31) if d - k * D in lv]
            if len(p) < 25: continue
            z = (lv[d] - np.mean(p)) / max(0.15, np.std(p)); spike = z >= 3 and v[d] >= 300
            if spike and i + 2 > ls:
                x = sim(a, i + 2, 1, hold, 0.15)
                if x: sig.append((hold, x[0], x[1], c)); ls = x[2]
            if not spike and z < 1 and i + 2 > lc:
                x = sim(a, i + 2, 1, hold, 0.15)
                if x: ctl.append((hold, x[0], x[1], c)); lc = x[2]
for hold in (3, 7):
    s = [(t, r) for h, t, r, c in sig if h == hold]; k = [(t, r) for h, t, r, c in ctl if h == hold]
    print(fmt(f"wiki spike z>=3 + up>3%, long {hold}d", stats(s))); print(fmt(f"   price-only: up>3%, no spike (z<1), long {hold}d", stats(k)))
    yrs = collections.defaultdict(list)
    for t, r in s: yrs[time.gmtime(t / 1000).tm_year].append(r)
    print("   by year: " + " ".join(f"{y}:{np.mean(v)*100:+.1f}/{len(v)}" for y, v in sorted(yrs.items())))
    r = np.sort(np.array([x[1] for x in s]))[::-1]
    print(f"   total profit {r.sum()*100:+.0f} pts; top 5 trades give {r[:5].sum()*100:+.0f}; top 10 give {r[:10].sum()*100:+.0f}; mean without best 10 = {r[10:].mean()*100:+.2f}%")
