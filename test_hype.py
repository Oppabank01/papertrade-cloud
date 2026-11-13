#!/usr/bin/env python3
"""Offline check: hype mirrors each source buy once, with its own sizing."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import hype, agents, grok
d = Path(tempfile.mkdtemp()); hype.HERE = d; agents.STATE = d / "state_hype.json"
(d / "state_agents.json").write_text(json.dumps({"log": [{"t": "2026-11-13T02:00:00", "kind": "buy", "mint": "M", "sym": "T"}]}))
agents.save(dict(start_usd=10, cash=10, pos={}, log=[], mirrored=[]))
grok.pair = lambda m: {"priceUsd": "1.0"}
hype.cmd_mirror(); hype.cmd_mirror()
s = agents.load()
assert list(s["pos"]) == ["M"] and abs(s["pos"]["M"]["cost"] - 4.0) < 1e-9, s["pos"]
assert len([x for x in s["log"] if x["kind"] == "buy"]) == 1
print("hype ok")
