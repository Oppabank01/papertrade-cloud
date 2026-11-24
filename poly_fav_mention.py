#!/usr/bin/env python3
"""Polymarket "mention" markets (Will X say "word" during Y?): buy the side priced 0.70-0.95, opened 24 Nov 2026. Fake money
only, same public read-only APIs as poly_fav.py.

Same scan, sizing, filters and settlement as poly_fav.py, only questions with ' say "'. Why (calibration I pulled on 24 Nov:
150 random closed events tagged mention-markets of the last 60 days, 2,293 markets, CLOB price history, both sides):
  6 h before the end:  priced 0.85-0.95 n 213 at 0.90 won 0.97 (event z 3.9); 0.60-0.85 n 656 at 0.71 won 0.79 (z 1.9)
  24 h before the end: same direction but weaker (0.85-0.95 at 0.90 won 0.93, z 1.2)
  Mirror: words priced 5-15c were said 2% of the time (z -4.3). Who pays: buyers of "Yes, they will say it" lottery tickets.
Band 0.70-0.95 chosen by me from those buckets; the 6 h result is the strong one, so this is a real test.
  state_poly_say.json        buys mention outcomes with best ask 0.70-0.95
  state_poly_say_long.json   control: mention outcomes with best ask 0.05-0.30
  state_poly_say_twin.json   random outcome of each market the two above buy, same moment and size
  python3 poly_fav_mention.py run | status"""
import sys
from pathlib import Path

import poly_fav as F

HERE = Path(__file__).parent
FAV, LONG, TWIN = (str(HERE / f"state_poly_{n}.json") for n in ("say", "say_long", "say_twin"))
F.LABELS.update({FAV: "Polymarket ทายคำพูด (จะพูดคำนี้ไหม) ซื้อฝั่งราคา 0.70-0.95 ไม้ละ 5% ถือจนรู้ผล",
                 LONG: "Polymarket ทายคำพูด ตัวควบคุม: ซื้อฝั่ง 0.05-0.30",
                 TWIN: "Polymarket ทายคำพูด ตัวควบคุม: สุ่มฝั่งในตลาดเดียวกัน"})
F.FAV_LO, F.FAV_HI, F.LONG_LO, F.LONG_HI = 0.70, 0.95, 0.05, 0.30
F.UNIVERSE = 2700                                      # chosen: mention markets are low volume, rotate deeper like poly_fav_exact
_tradable = F.tradable


def tradable(m, now):
    return _tradable(m, now) if ' say "' in (m.get("question") or "") else "not a mention market"


F.tradable = tradable                                  # cmd_run looks tradable up in poly_fav at call time


def main(cmd):
    if cmd == "status":
        for f in (FAV, LONG, TWIN):
            s = F.load(f)
            print(f"{Path(f).stem:<22} {F.P.value(s) / s['start_usd'] - 1:+.1%} open {len(s['pos'])}")
        return
    F.cmd_run(FAV, LONG, TWIN, HERE / "data" / "poly_fav_mention_log.jsonl")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "run")
