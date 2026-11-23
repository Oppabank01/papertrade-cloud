#!/usr/bin/env python3
"""fwd_rsi2us's bar walk gives the same trades as a plain backtest loop (network: Yahoo, 5 years)."""
import fwd_overnight as O
import fwd_rsi2us as F
from byttrade import new_state

O.URL = O.URL.replace("range=3mo", "range=5y")
for sym in F.SYMS:
    b = O.fetch(sym)
    want, i = [], 5
    while i < len(b) - 1:
        if b[i]["closed"] and F.rsi2(b, i) < F.TH:
            k = i + 1
            while k < len(b) - 1 and b[k]["closed"]:
                if b[k]["c"] > sum(y["c"] for y in b[k - 4:k + 1]) / 5 or k - i >= F.MAXB:
                    break
                k += 1
            else:
                break                                   # still open at the end
            want.append(round(b[k + 1]["o"] / b[i + 1]["o"] - 1, 6)); i = k + 1
        else:
            i += 1
    s = new_state("t"); s["seen"] = {sym: b[4]["t"]}; s["sleeve"] = {sym: 100.0}
    F.step(s, sym, b, "rule", None); F.step(s, sym, b, "rule", None)
    got = [x["ret"] for x in s["log"] if x["kind"] == "sell"]
    assert got == want, (sym, len(got), len(want), got[:5], want[:5])
    print(sym, len(got), "trades match the backtest; ok", f"mean {sum(got) / len(got) * 100:+.2f}%")
