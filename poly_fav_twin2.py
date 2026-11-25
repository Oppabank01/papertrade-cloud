#!/usr/bin/env python3
"""Second random-side control for poly_fav (opened 25 Nov 2026). Fake money only, public read-only APIs.

state_poly_fav_twin.json ran out of cash on 25 Nov (47 settled trades, -$14.26 of $14.75), so it can no longer buy and the
fav vs control comparison would freeze at 47 control trades (z 1.9 at that point). This account restarts the control with a
fresh 500 THB: for every buy state_poly_fav.json makes after this account opened, it buys a random outcome of the same
market, same size (5% of the start), at the live ask, a few seconds after (same cloud run, right after poly_fav.py).
The fav account itself is unchanged.
  state_poly_fav_twin2.json
  python3 poly_fav_twin2.py"""
import json, random, time
from pathlib import Path

import polymarket as P
import poly_fav as F

HERE = Path(__file__).parent
TWIN2 = str(HERE / "state_poly_fav_twin2.json")
LABEL = "Polymarket ตัวควบคุมชุดที่ 2 ของตัวเต็ง: สุ่มฝั่งในตลาดเดียวกับ poly_fav ที่ซื้อใหม่ ขนาดเท่ากัน (ชุดแรกเงินหมด 25 พ.ย.)"


def run(fav_path=F.FAV, twin_path=TWIN2, rng=None):
    rng = rng or random.Random()
    sf, st = F.load(fav_path), F.load(twin_path)
    st["label"] = LABEL
    if "after" not in st:                              # first run: only follow fav buys from now on
        st["after"] = P.now_iso()
    new = [dict(x, cond=sf["pos"][x["token"]]["cond"]) for x in sf["log"]
           if x["kind"] == "buy" and x["t"] > st["after"] and x["token"] in sf["pos"]]   # the buy log has no condition id
    later = [x["t"] for x in sf["log"] if x["kind"] == "buy" and x["t"] > st["after"]]
    if later:
        st["after"] = max(later)
        conds = list({x["cond"] for x in new})
        try:
            mk = P.markets(conds)
        except Exception as e:
            print(f"fav twin2 markets fetch: {type(e).__name__}")
            mk = {}
        for x in new:
            m = mk.get(x["cond"])
            if not m or x["cond"] in st["done"]:
                continue
            tk = F.tokens(m)
            if not tk:
                continue
            oi = rng.randrange(len(tk))
            try:
                bk = P.books([tk[oi]])
            except Exception:
                continue
            why = P.buy(st, tk[oi], m, oi, bk.get(tk[oi]), f"สุ่มฝั่ง {oi} คู่กับ fav {x.get('pair', '')}", pair=x.get("pair"), event=x.get("event"))
            if why is None:
                st["done"][x["cond"]] = int(time.time())
            else:
                st["log"].append(dict(kind="skip", t=P.now_iso(), pair=x.get("pair"), why=why))
    st["done"] = {k: v for k, v in st["done"].items() if v > time.time() - 10 * 86400}
    F.settle_and_mark(st)
    P.save(twin_path, st)
    print(f"fav twin2: {len(new)} new fav buys | {P.value(st) / st['start_usd'] - 1:+.1%} open {len(st['pos'])}")


if __name__ == "__main__":
    run()
