#!/usr/bin/env python3
"""Polymarket near-certain outcomes, ask 0.985-0.995 (opened 24 Nov 2026). Fake money only, same public read-only APIs as poly_fav.py.

Same scan, filters (no in-play buys, ends within 48 h), sizing and settlement as poly_fav.py; only the price ranges and files
differ. Picking up pennies: each win pays about +0.5% to +1.5% after the taker fee, one loss costs the whole stake, so the
break-even loss rate is about 0.5% to 1.5%. Why (data/poly_fav_calib.json, price before the spread, both outcomes):
  priced 0.99-0.995: 24 h before end n 66, 6 h n 190, 1 h n 241, every one won (price 0.992); 0.995-0.9999 also all won
  priced 0.98-0.99:  6 h n 281 won 0.989 (3 lost), 1 h n 319 won 0.984 (5 lost): about break-even, so not bought here
Zero losses in about 500 rows only says the loss rate is probably under about 1%, which is the break-even zone, so this is a
real test, not a sure thing. Fast: many markets sit at 0.99 two days before the end, so it should fill 20 slots quickly.
  state_poly_sure.json        buys outcomes with best ask 0.985-0.995
  state_poly_sure_long.json   control: outcomes with best ask 0.005-0.015 (the other side of the same kind of market)
  state_poly_sure_twin.json   random outcome of each market the two above buy, same moment and size
  python3 poly_fav_sure.py run | status"""
import sys
from pathlib import Path

import poly_fav as F

HERE = Path(__file__).parent
FAV, LONG, TWIN = (str(HERE / f"state_poly_{n}.json") for n in ("sure", "sure_long", "sure_twin"))
F.LABELS.update({FAV: "Polymarket เก็บเศษ: ซื้อฝั่งที่ราคา 0.985-0.995 ตลาดจบใน 48 ชม. ไม้ละ 5% ถือจนตัดสินผล (ชนะได้น้อย แพ้เสียทั้งไม้)",
                 LONG: "Polymarket เก็บเศษ ตัวควบคุม: ซื้อฝั่ง 0.005-0.015",
                 TWIN: "Polymarket เก็บเศษ ตัวควบคุม: สุ่มฝั่งในตลาดเดียวกัน"})
F.FAV_LO, F.FAV_HI, F.LONG_LO, F.LONG_HI = 0.985, 0.995, 0.005, 0.015
F.P.PX_MIN, F.P.PX_MAX = 0.004, 0.996                  # polymarket.buy refuses fills outside 0.02-0.98 by default; this account lives there


def main(cmd):
    if cmd == "status":
        for f in (FAV, LONG, TWIN):
            s = F.load(f)
            print(f"{Path(f).stem:<22} {F.P.value(s) / s['start_usd'] - 1:+.1%} open {len(s['pos'])}")
        return
    F.cmd_run(FAV, LONG, TWIN, HERE / "data" / "poly_fav_sure_log.jsonl")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "run")
