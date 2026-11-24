#!/usr/bin/env python3
"""Polymarket "No" on soccer exact-score markets (opened 24 Nov 2026). Fake money only, same public read-only APIs as poly_fav.py.

Same scan, sizing and settlement as poly_fav.py, only markets whose question starts "Exact Score". Why
(data/poly_fav_calib.json, 6 h before the end, price before the spread):
  exact score, outcomes priced 0.85-0.97: n 1,103 priced 0.92 won 0.96 (+4%, event z 2.8); priced 0.03-0.15: 0.08 won 0.04
  moneyline/spread/totals in the same band: +2%, -5%, +4% (none clear)
Live books only quote exact-score No at about 0.90-0.97 (the calibration's 0.60-0.85 exact-score prices are stale history,
none seen in the live scan log). poly_fav buys these too but at most 2 per run, soonest end first, so it skips most of them
(140 of 172 exact-score rows in its log: not in the shortlist); this account only looks at them, so it buys more per day. It also rotates through the top 2,700 by 24 h volume instead of 900.
  state_poly_exact.json        buys exact-score outcomes with best ask 0.85-0.97 (in practice "No")
  state_poly_exact_long.json   control: exact-score outcomes with best ask 0.03-0.15 (in practice "Yes"), expected to lose
  state_poly_exact_twin.json   random outcome of each market the two above buy, same moment and size
  python3 poly_fav_exact.py run | status"""
import sys
from pathlib import Path

import poly_fav as F

HERE = Path(__file__).parent
FAV, LONG, TWIN = (str(HERE / f"state_poly_{n}.json") for n in ("exact", "exact_long", "exact_twin"))
F.LABELS.update({FAV: "Polymarket ทายสกอร์ฟุตบอล ซื้อฝั่งที่ราคา 0.85-0.97 (ส่วนใหญ่คือ 'ไม่ใช่สกอร์นี้') ไม้ละ 5% ถือจนตัดสินผล",
                 LONG: "Polymarket ทายสกอร์ ตัวควบคุม: ซื้อฝั่ง 0.03-0.15 (ทายว่าใช่สกอร์นี้)",
                 TWIN: "Polymarket ทายสกอร์ ตัวควบคุม: สุ่มฝั่งในตลาดเดียวกัน"})
F.FAV_LO, F.FAV_HI, F.LONG_LO, F.LONG_HI = 0.85, 0.97, 0.03, 0.15
F.UNIVERSE = 2700                                      # chosen: exact-score markets are low volume, so rotate deeper (full pass about 45 min)
_tradable = F.tradable


def tradable(m, now):
    return _tradable(m, now) if (m.get("question") or "").startswith("Exact Score") else "not exact score"


F.tradable = tradable                                  # cmd_run looks tradable up in poly_fav at call time


def main(cmd):
    if cmd == "status":
        for f in (FAV, LONG, TWIN):
            s = F.load(f)
            print(f"{Path(f).stem:<22} {F.P.value(s) / s['start_usd'] - 1:+.1%} open {len(s['pos'])}")
        return
    F.cmd_run(FAV, LONG, TWIN, HERE / "data" / "poly_fav_exact_log.jsonl")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "run")
