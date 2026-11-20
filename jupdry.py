#!/usr/bin/env python3
"""Dry run for a possible 300 THB real-money test of the Grok expert ledgers (S8, S9). Nothing is signed or sent: for each
new LTRADE line it asks Jupiter (public quote API, no wallet) what that trade would really fill at, scaled to a 300 THB
account, and logs the gap to the DexScreener price now (execution cost) and to Grok's own price (cost plus read delay)
in data/jup_dry.json. Called from grokveto.py on the Mac right after each chat read.
"""
import json
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
LOG = HERE / "data" / "jup_dry.json"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SCALE = 8.5 / 50                # 300 THB is about $8.5 against Grok's $50 fake ledger
TRADE = re.compile(r"^LTRADE S([89]|\d\d) (BUY|SELL) (\S+) (\S+) price=([\d.]+).*?\bt=(\d\d:\d\d).*?\busd=([\d.]+)", re.M)


def get(url, body=None):
    req = urllib.request.Request(url, json.dumps(body).encode() if body else None,
                                 {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def decimals(mint):
    return get("https://api.mainnet-beta.solana.com", {"jsonrpc": "2.0", "id": 1, "method": "getTokenSupply", "params": [mint]})["result"]["value"]["decimals"]


def dex_price(mint):
    pairs = get(f"https://api.dexscreener.com/tokens/v1/solana/{mint}")
    p = max((p for p in pairs if p["baseToken"]["address"] == mint), key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
    return float(p["priceUsd"])


def quote(side, mint, usd):
    """(fill price in USD per token, price impact %) for `usd` dollars at the current route."""
    dec, px = decimals(mint), dex_price(mint)
    if side == "BUY":
        q = get(f"https://lite-api.jup.ag/swap/v1/quote?inputMint={USDC}&outputMint={mint}&amount={int(usd * 1e6)}&slippageBps=300")
        return usd / (int(q["outAmount"]) / 10 ** dec), px, float(q["priceImpactPct"]) * 100
    raw = int(usd / px * 10 ** dec)
    q = get(f"https://lite-api.jup.ag/swap/v1/quote?inputMint={mint}&outputMint={USDC}&amount={raw}&slippageBps=300")
    return (int(q["outAmount"]) / 1e6) / (raw / 10 ** dec), px, float(q["priceImpactPct"]) * 100


def run(text, now=None):
    """Quote every LTRADE S8/S9 line not logged yet; trades over 15 min old (backfill, missed reads) are logged as late, unquoted."""
    now = now or datetime.now()
    log = json.loads(LOG.read_text()) if LOG.exists() else []
    done = {x["line"] for x in log}
    for m in TRADE.finditer(text):
        line = m[0][:160]
        if line in done:
            continue
        s, side, sym, mint, gpx, hm, usd = m.groups()
        h, mi = map(int, hm.split(":"))
        age = (now.hour * 60 + now.minute - h * 60 - mi) % 1440
        row = dict(line=line, s=int(s), side=side, sym=sym, t=hm, quoted=now.strftime("%H:%M"), delay_min=age, usd=round(float(usd) * SCALE, 2))
        if age > 15:
            row["late"] = True
        else:
            try:
                fill, px, impact = quote(side, mint, max(row["usd"], 0.5))
                sign = 1 if side == "BUY" else -1           # positive = worse for us
                row |= dict(fill=fill, dex=px, impact_pct=round(impact, 3),
                            cost_vs_dex_pct=round(sign * (fill / px - 1) * 100, 2),
                            cost_vs_grok_pct=round(sign * (fill / float(gpx) - 1) * 100, 2))
            except Exception as e:          # no route or API error: record it, never guess a fill
                row["error"] = repr(e)[:120]
            time.sleep(1)
        log.append(row)
        done.add(line)
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=0))
    return log
