import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import grokscout as g
tpl = 'RECIPE: {"label": "<what>", "source": "<post url>", "entry": {"min": {}}, "exit": {}} .'
t = "prompt " + tpl + g.START + ' RECIPE: none RECIPE: {"label":"dip buy","source":"https://x.com/a/status/1","claim":"10x","entry":{"min":{"liquidity":50000},"max":{"price_change_percent1h":-20},"safe":true},"exit":{"STOP":-0.2,"PER_TRADE":0.9,"MAX_HOLD_H":null}}How was RECIPE: {"label":"x","source":"https://x.com/b","entry":{"min":{"foo":1}},"exit":{}}'
r = g.replies(t); assert r[0] == "none" and r[1]["label"] == "dip buy" and len(r) == 3, r
s = g.to_spec(r[1], 1); assert s["exit"]["PER_TRADE"] == 0.5 and s["entry"]["safe"] is True and s["name"] == "g_scout_1", s
try: g.to_spec(r[2], 2); raise SystemExit("bad key accepted")
except AssertionError: pass
print("grokscout ok")
