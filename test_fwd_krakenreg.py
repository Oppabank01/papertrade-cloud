"""fwd_krakenreg.py walking daily bars one at a time (the last one still forming) gives the same entries and exits as its
backtest fwd_krakenreg.trades(), the function the backtest numbers in the scout's feed came from."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_krakenreg as F, byttrade as B

btc_all = [dict(x, closed=True) for x in mts.bars("binance", "BTCUSDT", "1d")]
full = {"BTCUSDT": F.trades(btc_all, btc_all), "ETHUSDT": F.trades(btc_all, mts.bars("binance", "ETHUSDT", "1d"))}
assert len(full["BTCUSDT"]) >= 24 and len(full["ETHUSDT"]) >= 24, {k: len(v) for k, v in full.items()}

for SYM in ("BTCUSDT", "ETHUSDT"):
    btc, b = F.align(btc_all[-1600:], [dict(x, closed=True) for x in mts.bars("binance", SYM, "1d")][-1600:])
    S0, n = F.SMA + 20, len(b)
    want = [(round(x["e"], 6), round(x["x"], 6)) for x in F.trades(btc, b, first=S0 + 1)]
    s = B.new_state("t"); s["seen"] = {SYM: b[S0]["t"]}
    for k in range(S0 + 2, n + 1):
        cut = lambda z: z[:k - 1] + [dict(z[k - 1], closed=False)]
        F.step(s, SYM, cut(btc), cut(b), "rule", random.Random(1))
    buys = [x for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e["px"], 6), round(p, 6)) for e, p in zip(buys, sells)]
    assert got == want[:len(got)] and len(want) - len(got) <= 1, (SYM, len(got), len(want), got[:3], want[:3])
    assert len(got) >= 5, got
    t = B.new_state("t"); t["seen"] = {SYM: b[S0]["t"]}
    for k in range(S0 + 2, n + 1):
        cut = lambda z: z[:k - 1] + [dict(z[k - 1], closed=False)]
        F.step(t, SYM, cut(btc), cut(b), "random", random.Random(k))
    ts = [x for x in t["log"] if x["kind"] == "sell"]
    assert ts and all(x["why"] == f"ครบ {F.TWIN_HOLD} วัน" for x in ts), ts[:2]
    print(SYM, f"{len(got)} trades match the backtest (full history {len(full[SYM])}); twin {len(ts)} trades; ok")
