#!/usr/bin/env python3
"""Polymarket daily temperature buckets: buy the side priced 0.60-0.93 (in practice "No" on a bucket the market gives
7-40%), opened 24 Nov 2026. Fake money only, same public read-only APIs as poly_fav.py.

Same scan, sizing, filters and settlement as poly_fav.py, only "temperature" questions. Why (calibration I pulled on
24 Nov: 200 random closed daily-temperature events of the last 3 weeks, 2,200 buckets, CLOB price history, both sides):
  24 h before the end: priced 0.60-0.85 n 712 at 0.698 won 0.841 (event z 5.4); 0.85-0.93 n 268 at 0.892 won 0.955 (z 3.7)
  36, 12 and 6 h give the same picture (0.60-0.85 wins 82-84% at about 0.70). Mirror: buckets priced 0.15-0.40 win 15-18%.
  Who pays: buyers of a single bucket at 20-35c (a lottery ticket on one temperature), the same longshot bias Kalshi's
  temperature markets show (1-5c buckets -78%). Caveat: history prices are trades/mids, the live ask is worse by the spread.
Stale-price check (24 Nov): buckets whose history price moved 3+ times in the 6 h before the lead point, 24 h lead:
  0.60-0.85 n 446 at 0.698 won 0.816 (z 4.1), so the edge is not just stale quotes.
poly_weather.py (forecast model) is a different idea and lost its first 2 buys.
  state_poly_wx.json        buys temperature outcomes with best ask 0.60-0.93
  state_poly_wx_long.json   control: temperature outcomes with best ask 0.15-0.40, expected to lose
  state_poly_wx_twin.json   random outcome of each market the two above buy, same moment and size
  python3 poly_fav_weather.py run | status"""
import sys
from pathlib import Path

import poly_fav as F

HERE = Path(__file__).parent
FAV, LONG, TWIN = (str(HERE / f"state_poly_{n}.json") for n in ("wx", "wx_long", "wx_twin"))
F.LABELS.update({FAV: "Polymarket อุณหภูมิรายวัน ซื้อฝั่งราคา 0.60-0.93 (ส่วนใหญ่คือ 'ไม่ใช่ช่องนี้') ไม้ละ 5% ถือจนรู้ผล",
                 LONG: "Polymarket อุณหภูมิ ตัวควบคุม: ซื้อฝั่ง 0.15-0.40 (ทายช่องเดียว)",
                 TWIN: "Polymarket อุณหภูมิ ตัวควบคุม: สุ่มฝั่งในตลาดเดียวกัน"})
F.FAV_LO, F.FAV_HI, F.LONG_LO, F.LONG_HI = 0.60, 0.93, 0.15, 0.40
F.UNIVERSE = 2100                                      # chosen: temperature markets are low volume, rotate deeper like poly_fav_exact
_tradable = F.tradable


def tradable(m, now):
    return _tradable(m, now) if "temperature" in (m.get("question") or "") else "not temperature"


F.tradable = tradable                                  # cmd_run looks tradable up in poly_fav at call time


def main(cmd):
    if cmd == "status":
        for f in (FAV, LONG, TWIN):
            s = F.load(f)
            print(f"{Path(f).stem:<22} {F.P.value(s) / s['start_usd'] - 1:+.1%} open {len(s['pos'])}")
        return
    F.cmd_run(FAV, LONG, TWIN, HERE / "data" / "poly_fav_weather_log.jsonl")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "run")
