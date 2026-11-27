"""fwd_icc.py walking bars one at a time gives the same entries and exits as the scout's backtest (scout_1813/icc.py)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_icc as P, byttrade as B


def backtest(b, start):
    a, out, su, p = P.atr14(b), [], {}, None
    for i in range(start, len(b) - 1):
        x = b[i]
        if p:
            px = P.exit_px(p, x)
            if px is None and i - p["i"] + 1 >= P.HOLD:
                px = x["c"]
            if px is not None:
                out.append((round(p["entry"], 6), round(px, 6)))
                p = None
            continue
        if not a[i]:
            continue
        stop = P.setup_step(su, b, i, a[i])
        if stop is None:
            continue
        e = b[i + 1]["o"]
        if e <= stop:
            continue
        p = dict(entry=e, i=i + 1, stop=stop, tgt=e + P.RR * (e - stop))
    return out, p


total = 0
for sym in ("XRPUSDT", "ETHUSDT"):
    b = [dict(x, closed=True) for x in mts.bars("binance", sym, "4h")[-3000:]]
    want, open_p = backtest(b, 401)
    s = B.new_state("t"); s["seen"] = {sym: b[400]["t"]}
    for k in range(402, len(b) + 1):
        P.step(s, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    assert (sym in s["pos"]) == (open_p is not None), sym
    assert len(got) > 3, (sym, len(got))
    total += len(got)
    t = B.new_state("t"); t["seen"] = {sym: b[400]["t"]}
    for k in range(402, len(b) + 1):
        P.step(t, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
    assert any(x["kind"] == "sell" for x in t["log"]), sym
print(f"{total} trades match the backtest; ok")
