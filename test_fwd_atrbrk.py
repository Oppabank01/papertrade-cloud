"""fwd_atrbrk.py walking 4h bars one at a time (the last one still forming) gives the same trades as its backtest
fwd_atrbrk.trades(), the function the backtest numbers in its LABEL came from."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_atrbrk as F, byttrade as B

for SYM in ("BTCUSDT", "PAXGUSDT"):
    b = [dict(x, closed=True) for x in mts.bars("binance", SYM, "4h")[-1300:]]
    S0, n = 400, len(b)
    want = [(round(e, 6), round(x, 6)) for e, x, _ in F.trades(b[:-1], first=S0 + 1)]   # the walk never closes on the forming bar
    s = B.new_state("t"); s["seen"] = {SYM: b[S0]["t"]}
    for k in range(S0 + 2, n + 1):
        F.step(s, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
    assert got == want, (SYM, len(got), len(want), got[:3], want[:3])
    assert len(got) > 5, (SYM, len(got))
    assert all(x["side"] == "long" for x in s["log"]), SYM   # the short leg never fires (see fwd_atrbrk docstring)
    t = B.new_state("t"); t["seen"] = {SYM: b[S0]["t"]}
    for k in range(S0 + 2, n + 1):
        F.step(t, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
    assert any(x["kind"] == "sell" for x in t["log"])
    print(f"{SYM}: {len(got)} trades match the backtest")
print("ok")
