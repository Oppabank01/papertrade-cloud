#!/usr/bin/env python3
"""Forward paper test of weekly cross-sectional MAX momentum among big coins, opened 28 Nov 2026 by the scout. Fake money only.

Source: Li, Urquhart, Wang and Zhang (2021, "MAX momentum in cryptocurrency markets"): coins with the highest recent
maximum daily return kept outperforming. runningshark/factor_study_failureprove pre-registered the opposite (X7, lottery
effect: long low MAX, short high MAX) and left it "to watch"; on our 27 coins that direction lost, so this direction is
chosen after seeing it (post hoc).
Rule: every Monday at the 00:00 UTC daily open, among the 27 coins of fwd_lowvol that have the 31 daily closes before that
Monday, rank by the largest of the last 30 close-to-close returns. Long the third with the highest, short the third with
the lowest, half the account per side, equal weight, held to next Monday's open; same cost handling as fwd_lowvol.
Scout backtest 2019-2026 (/tmp/scout_1121/maxmom.py, Binance spot daily, coins listed today, so survivorship bias in favour
of the long leg): 381 weeks, pre-cost +0.41%/week, after cost +0.25% (median -0.12%, win 48%, CI -0.13..+0.61), first half
+0.65%, second half -0.14%, 2024+ -0.30% (2024 -0.07, 2025 -0.57, 2026 -0.27); random long-short picks -0.50% (best of 20
-0.17%); permutation 200 (this rule only, pre-cost) p 0.040, not below the 0.01 gate and post hoc. Opened because the user
wants weak ideas tried live.
Numbers I chose: as fwd_lowvol (27 coins, 30 days, thirds, at least 12 coins, no funding, 0.35% per side).
  state_fwd_maxmom.json       the rule
  state_fwd_maxmom_twin.json  control: random thirds long and short each Monday, same schedule and cost
  python3 fwd_maxmom.py"""
import fwd_lowvol as L

ACCOUNTS = {"state_fwd_maxmom.json": ("rule", "MAX momentum ข้ามเหรียญ: ทุกจันทร์ long 1 ใน 3 ที่มีวันพุ่งแรงสุดใน 30 วันสูงสุด short 1 ใน 3 ที่ต่ำสุด จาก 27 เหรียญใหญ่ (backtest 381 สัปดาห์ หลังหัก +0.25%/สัปดาห์ แต่ปี 2024+ -0.30% p 0.040 ตัวแฝดสุ่ม -0.50%)"),
            "state_fwd_maxmom_twin.json": ("random", "MAX momentum ตัวควบคุม: สุ่ม 1 ใน 3 long และ 1 ใน 3 short ทุกจันทร์ ต้นทุนเดียวกัน")}


def signal(cl):   # lower sorts first and is held long, so the highest max daily return gets the minus sign
    return -max(cl[i] / cl[i - 1] - 1 for i in range(1, len(cl)))


if __name__ == "__main__":
    L.run(ACCOUNTS, "fwd_maxmom", signal)
