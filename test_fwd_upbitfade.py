#!/usr/bin/env python3
"""fwd_upbitfade: parses Upbit listing titles, enters at h1 and covers at h24 at Binance 1 h opens (no network: stubs)."""
import random
import fwd_upbitfade as U
from byttrade import new_state

n = [dict(id=1, title="로켓풀(RPL), 아큐라스트(ACU) 신규 거래지원 안내 (KRW 마켓)", first_listed_at="2026-11-24T13:25:48+09:00"),
     dict(id=2, title="제로지(0G) 거래 유의 종목 지정 안내", listed_at="2026-11-24T15:00:00+09:00")]
got = U.listings(n)
assert [g[1] for g in got] == ["RPL", "ACU"], got
ts = got[0][2]
h0 = -(-ts // U.H) * U.H
px = {h0 + U.H: 10.0, h0 + 24 * U.H: 9.0}
kl = lambda u: [[int(u.split("startTime=")[1].split("&")[0]), str(px[int(u.split("startTime=")[1].split("&")[0])])]] if int(u.split("startTime=")[1].split("&")[0]) in px else []
s = new_state("t"); s["mode"] = "rule"
U.step(s, [got[0]], h0, random.Random(1), kl); assert not s["pos"] and len(s["queue"]) == 1      # waits for h1
U.step(s, [], h0 + U.H + 61000, random.Random(1), kl); p = s["pos"][got[0][0]]; assert p["entry"] == 10.0 and p["d"] == -1
U.step(s, [], h0 + 24 * U.H + 61000, random.Random(1), kl)
sell = s["log"][-1]
assert sell["kind"] == "sell" and abs(sell["ret"] - 0.1) < 1e-9 and not s["pos"]
assert abs(sell["pnl"] - (s["start_usd"] * U.SIZE * 0.1 - s["start_usd"] * U.SIZE * 0.9 * U.COST)) < 1e-9
print("ok")
