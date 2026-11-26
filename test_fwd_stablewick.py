#!/usr/bin/env python3
"""fwd_stablewick: fills a 0.985 bid on a wick, sells at 0.999 on a later bar, times out after 30 days (no network: stubs)."""
import random
import fwd_stablewick as S
from byttrade import new_state

M = S.M
t0 = 1_800_000_000_000
b = [(t0, 1.0, 1.0, 0.999, 1.0), (t0 + M, 0.99, 0.99, 0.97, 0.98), (t0 + 2 * M, 0.98, 0.9995, 0.98, 0.999)]
s = new_state("t"); s["mode"] = "rule"
S.step(s, "USDC", b[:2], random.Random(1))
assert "USDC" in s["pos"] and s["pos"]["USDC"]["entry"] == 0.985 and not [x for x in s["log"] if x["kind"] == "sell"]
S.step(s, "USDC", b[2:], random.Random(1))
sell = s["log"][-1]
assert sell["kind"] == "sell" and sell["px"] == 0.999 and abs(sell["ret"] - (0.999 / 0.985 - 1)) < 1e-6 and not s["pos"]
usd = s["start_usd"] * S.SIZE
assert abs(s["cash"] - (s["start_usd"] - usd * (1 + S.COST) + usd / 0.985 * 0.999 * (1 - S.COST))) < 1e-9

gap = [(t0 + M, 0.98, 0.98, 0.98, 0.98)]                              # open below the bid fills at the open
s2 = new_state("t"); s2["mode"] = "rule"
S.step(s2, "TUSD", gap, random.Random(1))
assert s2["pos"]["TUSD"]["entry"] == 0.98
S.step(s2, "TUSD", [(t0 + (S.HOLD + 1) * M, 0.9, 0.95, 0.9, 0.93)], random.Random(1))
assert s2["log"][-1]["why"] == "ครบ 30 วัน" and s2["log"][-1]["px"] == 0.93

pages = {t0: [[t0 + i * M, "1", "1", "1", "1"] for i in range(1000)], t0 + 1000 * M: [[t0 + (1000 + i) * M, "1", "1", "1", "1"] for i in range(6)]}
kl = lambda u: pages.get(int(u.split("startTime=")[1].split("&")[0]), [])
assert len(S.bars("USDC", t0, t0 + 1005 * M, kl)) == 1005                # pages, drops the still-open last bar
print("ok")
