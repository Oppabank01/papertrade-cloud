#!/usr/bin/env python3
"""Offline check for grokveto.py (Mac-only): approvals become v_grok orders dated at queue time, stats count decisions."""
import json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grokveto as g
d = Path(tempfile.mkdtemp())
g.QUEUE, g.ORDERS = d / "q.json", d / "o.json"
g.QUEUE.write_text(json.dumps([dict(id="c1001", mint="M1", sym="AAA", t=1000), dict(id="c1002", mint="M2", sym="BBB", t=1000)]))
txt = ("prompt VETO <id> APPROVE Created routines " + g.VETO + " VETO c1001 APPROVE M1 reason=fresh CEX listing newsVETO c1002 REJECT M2 reason=dev dumping"
       "VETO c1001 REJECT M1 reason=second opinion ignored VETO c9999 APPROVE MX reason=not in queue")
orders, stats = g.veto_files(txt)
assert [(o["id"], o["mint"], o["t"]) for o in orders] == [("c1001", "M1", 1000)] and "CEX listing" in orders[0]["why"], orders
assert stats == {"approve": 1, "reject": 1}, stats
print("grokveto ok")
