#!/usr/bin/env python3
"""fwd_upbitwarn: picks new caution designations only, shorts at the next 1 h open after notice+2 min and first sight, books 72 h (no network)."""
import random
import fwd_upbitwarn as U
from byttrade import new_state

ns = [dict(id=1, title="거래 유의 종목 지정 안내 (AAA, BBB) (AAA)(BBB)", listed_at="2026-11-20T10:30:00+09:00"),
      dict(id=2, title="유의 종목 지정 기간 연장 안내 (CCC)", listed_at="2026-11-20T10:30:00+09:00"),
      dict(id=3, title="유의 종목 지정 해제 안내 (DDD)", listed_at="2026-11-20T10:30:00+09:00"),
      dict(id=4, title="신규 거래지원 안내 (EEE)", listed_at="2026-11-20T10:30:00+09:00")]
w = U.warnings(ns)
assert [x[1] for x in w] == ["AAA", "BBB"]
H, ts = U.H, w[0][2]
s = new_state("t"); s["mode"] = "rule"
U.step(s, [(w[0][0], "AAA", ts, ts + 20 * 60 * 1000)], ts + 20 * 60 * 1000, random.Random(1), lambda u: [])
t0 = s["queue"][0]["t0"]
assert t0 % H == 0 and t0 >= ts + 20 * 60 * 1000 and t0 - ts < H + 20 * 60 * 1000
fall = [[t0 + i * H, "10", "10.5", "0", "9"] for i in range(72)]
U.step(s, [], t0 + 73 * H, random.Random(1), lambda u: fall)
sell = s["log"][-1]
assert sell["kind"] == "sell" and abs(sell["ret"] - 0.1) < 1e-9 and sell["why"] == "ครบ 72 ชม."
px, why = U.trade([(0, 10.0, 12.0 if i == 3 else 10.2, 10.0) for i in range(72)])
assert abs(px - 11.5 * 1.001) < 1e-9 and why == "stop +15%"
print("ok")
