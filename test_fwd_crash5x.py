#!/usr/bin/env python3
"""fwd_crash5x's hour walk matches a plain loop over the last ~41 days of Binance 1 h bars (network), with forced signals."""
import fwd_crash5x as F
from byttrade import new_state

F.COIN_DROP = -0.02                                          # the last 41 days were calm: loosen so trades happen

btcb = F.fetch("BTC"); btc = {x["t"]: x["c"] for x in btcb}
fake = {t: 100.0 for t in btc}                               # BTC flat except: force -6% on every 97th hour
for k, t in enumerate(sorted(btc)):
    if k % 97 == 0 and k > 24: fake[t] = 94.0
for coin in ("SOL", "DOGE"):
    b = F.fetch(coin)
    b = [dict(x, closed=True) for x in b]
    want, i = [], 24
    while i < len(b) - 1:
        x = b[i]; t = x["t"]
        if fake.get(t) and fake.get(t - 24 * F.H) and fake[t] / fake[t - 24 * F.H] - 1 <= -0.05 and x["c"] / b[i - 24]["c"] - 1 <= F.COIN_DROP:
            e = b[i + 1]["o"]; j = i + 1; out = None
            while j < len(b):
                if b[j]["l"] / e - 1 <= F.LIQ: out = -1.0; break
                if j - i >= F.HOLD: out = max(F.LEV * (b[j]["c"] / e - 1) - 2 * F.COST * F.LEV, -1.0); break
                j += 1
            if out is None: break
            want.append(round(out, 6)); i = j + 1
        else:
            i += 1
    s = new_state("t"); s["seen_c"] = {coin: b[23]["t"]}
    F.step(s, coin, b, fake, "rule", None)
    got = [x["ret"] for x in s["log"] if x["kind"] == "sell"]
    assert got == want, (coin, got, want)
    print(coin, len(got), "forced-signal trades match", got[:4])
