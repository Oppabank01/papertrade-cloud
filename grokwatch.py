#!/usr/bin/env python3
"""Cloud price log for every Solana mint the Grok Bot routines mention (19-20 Nov 2026), independent of what Grok reports.
Each run (~5 min) takes a DexScreener snapshot (deepest pool) of every mint for 24 h after the cloud first sees it in
data/grok_chat_archive.txt (LTRADE, VETO and SEEN lines, pushed by the Mac readers) and appends it to data/grok_watch.csv,
so skipped coins and other exit points can be scored later. Read-only, no keys, paper test only.

  python3 grokwatch.py
"""
import csv
import json
import re
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ARCH, SEEN, CSV = HERE / "data" / "grok_chat_archive.txt", HERE / "data" / "grok_watch_seen.json", HERE / "data" / "grok_watch.csv"
MINT = re.compile(r"^(?:LTRADE S\d (?:BUY|SELL) \S+|VETO c\d+ (?:APPROVE|REJECT)|SEEN S\d \S+) ([1-9A-HJ-NP-Za-km-z]{32,44})\b", re.M)
COLS = "t mint sym price liq fdv vol_m5 vol_h1 buys_m5 sells_m5 ch_m5 ch_h1".split()


def mints(text):
    return list(dict.fromkeys(MINT.findall(text)))


def row(p, t):
    g = lambda k, s: (p.get(k) or {}).get(s)
    return dict(t=t, mint=p["baseToken"]["address"], sym=p["baseToken"].get("symbol"), price=p.get("priceUsd"),
                liq=g("liquidity", "usd"), fdv=p.get("fdv"), vol_m5=g("volume", "m5"), vol_h1=g("volume", "h1"),
                buys_m5=g("txns", "m5") and p["txns"]["m5"].get("buys"), sells_m5=g("txns", "m5") and p["txns"]["m5"].get("sells"),
                ch_m5=g("priceChange", "m5"), ch_h1=g("priceChange", "h1"))


def deepest(pairs, want, t):
    """{mint: row} keeping the pool with the most liquidity per wanted mint."""
    out = {}
    for p in pairs:
        r = row(p, t)
        if r["mint"] in want and (r["liq"] or 0) >= (out.get(r["mint"], {}).get("liq") or -1):
            out[r["mint"]] = r
    return out


def main():
    if not ARCH.exists():
        return
    now = int(time.time())
    seen = json.loads(SEEN.read_text()) if SEEN.exists() else {}
    for m in mints(ARCH.read_text()):
        seen.setdefault(m, now)
    SEEN.write_text(json.dumps(seen, indent=0))
    live = [m for m, t0 in seen.items() if now - t0 < 86400]
    rows = {}
    for i in range(0, len(live), 30):     # DexScreener takes up to 30 addresses per call
        url = "https://api.dexscreener.com/tokens/v1/solana/" + ",".join(live[i:i + 30])
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
                rows |= deepest(json.load(r), set(live), now)
        except Exception as e:            # an API error is a missed snapshot, never a guessed price
            print(f"grokwatch: {e!r}"[:160])
    new = not CSV.exists()
    with CSV.open("a", newline="") as f:
        w = csv.DictWriter(f, COLS)
        if new:
            w.writeheader()
        w.writerows(rows.values())


if __name__ == "__main__":
    main()
