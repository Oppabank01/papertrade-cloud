#!/usr/bin/env python3
"""Polymarket mid favourites, sports markets only (opened 24 Nov 2026). Fake money only, same public read-only APIs as poly_fav.py.

Same as poly_fav_mid.py (prices 0.60-0.85, control 0.15-0.40, random-side twin), plus one filter: the market's Gamma feeType
starts with "sports". Why: poly_fav_mid buys crypto Up/Down and daily temperature markets too, but the calibration behind it
is 91% sports. data/poly_fav_calib.json, both outcomes of each market, price before the spread, rough taker fee:
  sports 6 h before end, 0.60-0.85: n 1,632 (669 events) priced 0.733 won 0.800, about +8% per $ (event z 4.4)
  sports 1 h before end:            n 1,591 (679 events) priced 0.733 won 0.795, about +7% per $ (event z 4.0)
  other markets 6 h:                n 81 priced 0.719 won 0.790 (too few to say anything)
poly_fav_mid's first day: 23 trades, 10 won at an average price of about 0.71 (about 16 expected), sports alone 5 of 12.
Opened at the user's request on 24 Nov 2026 after that first day.
Caveat found 20 min after opening: split by market type, the sports 0.60-0.85 edge is almost all exact-score history
(priced 0.78 won 0.98), which live books never quote in that band; moneyline +1%, spread -1%, totals +2% (none clear).
So this account mostly tests moneyline/spread/totals, where the calibration shows no edge. Kept running as a test.
  state_poly_sport.json        buys sports outcomes with best ask 0.60-0.85
  state_poly_sport_dog.json    control: sports outcomes with best ask 0.15-0.40, expected to lose
  state_poly_sport_twin.json   random outcome of each market the two above buy, same moment and size
  python3 poly_fav_sport.py run | status"""
import sys
from pathlib import Path

import poly_fav as F

HERE = Path(__file__).parent
FAV, DOG, TWIN = (str(HERE / f"state_poly_{n}.json") for n in ("sport", "sport_dog", "sport_twin"))
F.LABELS.update({FAV: "Polymarket กีฬาอย่างเดียว ซื้อตัวเต็งระดับกลาง 0.60-0.85 ตลาดจบใน 48 ชม. ไม้ละ 5% ถือจนตัดสินผล",
                 DOG: "Polymarket กีฬา ตัวควบคุม: ซื้อตัวรองระดับกลาง 0.15-0.40 ตลาดแบบเดียวกัน",
                 TWIN: "Polymarket กีฬา ตัวควบคุม: สุ่มฝั่งในตลาดเดียวกับตัวเต็งกลาง/ตัวรองกลาง"})
F.FAV_LO, F.FAV_HI, F.LONG_LO, F.LONG_HI = 0.60, 0.85, 0.15, 0.40
_tradable = F.tradable


def tradable(m, now):
    return _tradable(m, now) if (m.get("feeType") or "").startswith("sports") else "not sports"


F.tradable = tradable                                  # cmd_run looks tradable up in poly_fav at call time


def main(cmd):
    if cmd == "status":
        for f in (FAV, DOG, TWIN):
            s = F.load(f)
            print(f"{Path(f).stem:<22} {F.P.value(s) / s['start_usd'] - 1:+.1%} open {len(s['pos'])}")
        return
    F.cmd_run(FAV, DOG, TWIN, HERE / "data" / "poly_fav_sport_log.jsonl")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "run")
