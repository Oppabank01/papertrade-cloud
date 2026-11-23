#!/usr/bin/env python3
"""Polymarket mid favourites (opened 23 Nov 2026 11:40). Fake money only, same public read-only APIs as poly_fav.py.

Same scan, filters, sizing and settlement as poly_fav.py (imported, not copied); only the price ranges and files differ:
  state_poly_mid.json       buys outcomes with best ask 0.60-0.85 (mid favourites)
  state_poly_mid_dog.json   control: outcomes with best ask 0.15-0.40 (mid underdogs), expected to lose
  state_poly_mid_twin.json  random outcome of each market the two above buy, same moment and size
Why (data/poly_fav_calib.json, 5,948 resolved markets, 91% sports, price 6 h before end, before the spread):
  0.60-0.70 priced 0.645 won 0.678, 0.70-0.80 priced 0.750 won 0.837, 0.80-0.85 priced 0.822 won 0.896
  (+4% to +10% per $ after the taker fee). Caveat: if a market had no gameStartTime the "6 h before" point may be in play,
  which would flatter favourites; the live scan never buys in play. Ranges chosen by me from those buckets.
  python3 poly_fav_mid.py run | status"""
import sys
from pathlib import Path

import poly_fav as F

HERE = Path(__file__).parent
MID, DOG, TWIN = (str(HERE / f"state_poly_{n}.json") for n in ("mid", "mid_dog", "mid_twin"))
F.LABELS.update({MID: "Polymarket ซื้อตัวเต็งระดับกลาง 0.60-0.85 ตลาดจบใน 48 ชม. ไม้ละ 5% ถือจนตัดสินผล",
                 DOG: "Polymarket ตัวควบคุม: ซื้อตัวรองระดับกลาง 0.15-0.40 ตลาดแบบเดียวกัน",
                 TWIN: "Polymarket ตัวควบคุม: สุ่มฝั่งในตลาดเดียวกับตัวเต็งกลาง/ตัวรองกลาง"})
F.FAV_LO, F.FAV_HI, F.LONG_LO, F.LONG_HI = 0.60, 0.85, 0.15, 0.40


def main(cmd):
    if cmd == "status":
        for f in (MID, DOG, TWIN):
            s = F.load(f)
            print(f"{Path(f).stem:<22} {F.P.value(s) / s['start_usd'] - 1:+.1%} open {len(s['pos'])}")
        return
    F.cmd_run(MID, DOG, TWIN, HERE / "data" / "poly_fav_mid_log.jsonl")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "run")
