#!/usr/bin/env python3
"""fwd_cbprem's bar-by-bar walk gives the same trades as a plain loop over the last ~2,000 hours (network: Coinbase + Binance)."""
import json, sys, time, urllib.request
from datetime import datetime, timezone
sys.path.insert(0, "/Users/oppabank/.claude/skills/market-timeseries/scripts")
import mts
import fwd_cbprem as F
from byttrade import new_state

end, cb = int(time.time()) // 3600 * 3600, {}
for k in range(7):
    t1 = end - k * 300 * 3600
    f = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
    cb.update({r[0] * 1000: r[4] for r in json.loads(urllib.request.urlopen(urllib.request.Request(
        F.CB.format(f(t1 - 300 * 3600), f(t1)), headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())})
lo = min(cb)
bars = [dict(x, closed=True) for x in mts.bars("binance", "BTCUSDT", "1h") if x["t"] >= lo]
bars[-1]["closed"] = False
z = F.zscores(bars, cb)
want, nxt = [], -1
for i in range(len(bars) - 1):
    if i < nxt or z[i] is None or abs(z[i]) <= F.Z or i + 1 + F.HOLD_H >= len(bars):
        continue
    d = 1 if z[i] > 0 else -1
    a, c = bars[i + 1], bars[i + 1 + F.HOLD_H]
    assert c["t"] - a["t"] == F.HOLD_H * F.H1, "gap in Binance 1h bars"
    want.append(round((c["o"] / a["o"] - 1) * d, 5)); nxt = i + F.HOLD_H
s = new_state("t"); s["seen"] = bars[0]["t"]
F.step(s, bars, cb, "rule", None)
got = [x["ret"] for x in s["log"] if x["kind"] == "sell"]
assert got == want, (len(got), len(want), got[:5], want[:5])
print(len(got), "trades match the plain loop; ok")
