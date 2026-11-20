import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import grokscout as g
tpl = 'RECIPE: {"label": "<what>", "source": "<post url>", "entry": {"min": {}}, "exit": {}} .'
t = "prompt " + tpl + g.START + ' RECIPE: none RECIPE: {"label":"dip buy","source":"https://x.com/a/status/1","claim":"10x","entry":{"min":{"liquidity":50000},"max":{"price_change_percent1h":-20},"safe":true},"exit":{"STOP":-0.2,"PER_TRADE":0.9,"MAX_HOLD_H":null}}How was RECIPE: {"label":"x","source":"https://x.com/b","entry":{"min":{"foo":1}},"exit":{}}'
r = g.replies(t); assert r[0] == "none" and r[1]["label"] == "dip buy" and len(r) == 3, r
s = g.to_spec(r[1], 1); assert s["exit"]["PER_TRADE"] == 0.5 and s["entry"]["safe"] is True and s["name"] == "g_scout_1", s
try: g.to_spec(r[2], 2); raise SystemExit("bad key accepted")
except AssertionError: pass
m = {"t15s10": "old LEDGER S1 15:00 x", "t15s12": "Created routine “Meme 1h test v2”", "t15s9": "LEDGER S1 14:00 y", "sep-t16s1": "LEDGER S1 junk",
     "t16s100": "LEDGER S1 20:25 cash=3 open=LEDGER S8 20:29 cash=5VETO c12 REJECT M reason=no", "t16u": "VETO c1 my prompt", "t15s13": "LTRADE S1 BUY A M price=1"}
assert g.seq("t16u") < g.seq("t16s0") < g.seq("t16s10") and g.seq("t2s5") < g.seq("t16u") and g.seq("sep-t16s1") is None
assert g.as_text(m).splitlines() == ["LTRADE S1 BUY A M price=1", "LEDGER S1 20:25 cash=3 open=", "LEDGER S8 20:29 cash=5", "VETO c12 REJECT M reason=no"], g.as_text(m)
d = g.by_day("LEDGER S8 23:50 a\nLTRADE S8 x\nLEDGER S8 00:03 b\nLEDGER S8 00:01 c")
assert [(x.day, y.count("LEDGER")) for x, y in d] == [(19, 1), (20, 2)], d
assert g.seq("t18s352") < g.seq("tbs763") and g.seq("tbu") is not None and g.seq("sep-tbs1") is None
print("grokscout ok")
