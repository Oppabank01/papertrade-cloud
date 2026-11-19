#!/usr/bin/env python3
"""Offline check for jupdry.py: S8/S9 LTRADE lines parse, old trades are logged late without a quote, nothing repeats."""
import os, sys, tempfile
from datetime import datetime
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jupdry as j
j.LOG = Path(tempfile.mkdtemp()) / "j.json"
txt = ("LTRADE S8 BUY DCTY 9hjB price=0.02082 reason=x t=20:47 pair=P liq=585851.44 usd=10.00\n"
       "LTRADE S1 BUY X M price=1 reason=S1 t=21:00 pair=P liq=1 usd=3.00\nLTRADE S9 SELL ANTS M2 price=0.007 reason=y t=21:52 pair=P liq=1 usd=12.50")
j.quote = lambda side, mint, usd: (1.02, 1.0, 0.5) if side == "BUY" else (0.97, 1.0, 0.5)
log = j.run(txt, datetime(2026, 11, 19, 21, 58))
assert [(x["s"], x["sym"], x.get("late", False)) for x in log] == [(8, "DCTY", True), (9, "ANTS", False)], log
assert log[1]["cost_vs_dex_pct"] == 3.0 and log[1]["usd"] == 2.12 and log[1]["delay_min"] == 6, log[1]
assert len(j.run(txt, datetime(2026, 11, 19, 22, 5))) == 2
print("jupdry ok")
