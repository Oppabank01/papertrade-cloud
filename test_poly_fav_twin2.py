#!/usr/bin/env python3
"""poly_fav_twin2 copies only fav buys made after it opened, one random outcome per market (no network: stubs)."""
import json, random, tempfile, os
import poly_fav_twin2 as T

d = tempfile.mkdtemp(); fav, tw = os.path.join(d, "fav.json"), os.path.join(d, "tw.json")
sf = T.F.load(fav)
sf["log"] = [dict(kind="buy", t="2026-11-25T10:00:00+07:00", token="old"), dict(kind="buy", t="2099-01-01T00:00:00+07:00", token="a1", pair="p1")]
sf["pos"] = {"a1": dict(cond="c1")}
json.dump(sf, open(fav, "w"))
m = dict(conditionId="c1", clobTokenIds=json.dumps(["a1", "a2"]), outcomes=json.dumps(["Yes", "No"]))
T.P.markets = lambda conds: {"c1": m}
T.P.books = lambda toks: {t: {"asks": [{"price": "0.5", "size": "100"}], "bids": [{"price": "0.49", "size": "100"}]} for t in toks}
bought = []
T.P.buy = lambda st, tok, mm, oi, book, why, **kw: bought.append((tok, kw.get("pair"))) or st["pos"].__setitem__(tok, dict(cond="c1", oi=oi, coin="x", qty=1, usd=0.5, last=0.5)) or None
T.F.settle_and_mark = lambda s, bk=None: None
st = T.F.load(tw); st["after"] = "2026-11-25T12:00:00+07:00"; T.P.save(tw, st)
T.run(fav, tw, random.Random(3))
assert len(bought) == 1 and bought[0][1] == "p1", bought
T.run(fav, tw, random.Random(3)); assert len(bought) == 1        # no repeat
print("ok")
