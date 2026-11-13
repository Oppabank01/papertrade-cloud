#!/usr/bin/env python3
"""Cloud stand-in for agents.py's scan: fetch GMGN's 5m Solana ranking once and save it for recipes.py."""
import json
import time
from pathlib import Path

import grok

r = grok.gm("/v1/market/rank", chain="sol", interval="5m", limit=50, order_by="volume", direction="desc")
rank = (r.get("data") or r).get("rank", [])
(Path(__file__).with_name("data") / "rank5m_latest.json").write_text(json.dumps(dict(t=time.time(), rank=rank)))
print(f"rank saved: {len(rank)}")
