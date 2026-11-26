"""fwd_don20atr.py walking daily bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns, gives
the same entries and exits as its backtest fwd_don20atr.trades() on the full history (checked equal to the scout's
/tmp/scout_pine22.py don20_trades on BTC, ETH, SOL, BNB, XRP 2017-2026)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_don20atr as F, byttrade as B


def flat_start(full, tr):
    """A bar about 1500 bars from the end where the backtest is flat: after a trade's exit bar, before the next signal."""
    idx, a = {x["t"]: k for k, x in enumerate(full)}, F.pine_atr(full)
    for (t0, _, _), (t1, _, _) in zip(tr, tr[1:]):
        sig = idx[t0] - 1
        if sig < len(full) - 1500:
            continue
        stop, tgt = full[sig]["c"] - F.SL * a[sig], full[sig]["c"] + F.TP * a[sig]
        ex = next(j for j in range(sig + 1, len(full)) if F.hit(full[j], stop, tgt) is not None)
        if ex < idx[t1] - 2:
            return idx[t1] - 2
    raise AssertionError("no flat start")


for sym in ("BTCUSDT", "SOLUSDT"):
    full = [dict(x, closed=True) for x in mts.bars("binance", sym, "1d", max_age_h=24 * 30)]
    tr = F.trades(full)
    start = flat_start(full, tr)
    want = [(round(e, 6), round(x, 6)) for t, e, x in tr if t > full[start]["t"]]
    s = B.new_state("t"); s["seen"] = {sym: full[start]["t"]}
    for k in range(start + 2, len(full) + 1):
        w = full[max(0, k - 1000):k]
        F.step(s, sym, w[:-1] + [dict(w[-1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    assert len(got) >= 15, len(got)
    print(f"{sym}: {len(got)} trades match the backtest")

t = B.new_state("t"); t["seen"] = {"SOLUSDT": full[-800]["t"]}
for k in range(len(full) - 798, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(t, "SOLUSDT", w[:-1] + [dict(w[-1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print("ok")
