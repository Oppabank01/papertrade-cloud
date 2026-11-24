"""fwd_simpletrend.py walking bars one at a time gives the same entries and exits as the scout's backtest (/tmp/scout_1202/bt.py run())."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_simpletrend as F, byttrade as B

for sym in ("ETHUSDT", "SOLUSDT"):
    b = [dict(x, closed=True) for x in mts.bars("binance", sym, "4h")[-1300:]]
    k, want, i, n = F.ind(b), [], 401, len(b)
    while i < n - 1:
        d = F.signal(k[i])
        if not d:
            i += 1; continue
        p = dict(d=d, entry=b[i + 1]["o"], entry_t=b[i + 1]["t"], best=b[i + 1]["o"])
        j, px = i + 1, None
        while j < n:
            px, _ = F.bar_exit(p, b[j])
            if px is not None:
                nxt = j + 1; break
            if j + 1 < n and F.exit_signal(k[j], d):
                px, nxt = b[j + 1]["o"], j + 1; break
            j += 1
        if px is None:
            break
        want.append((round(p["entry"], 6), round(px, 6))); i = nxt
    s = B.new_state("t"); s["seen"] = {sym: b[400]["t"]}
    for m in range(402, n + 1):
        F.step(s, sym, b[:m - 1] + [dict(b[m - 1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    assert len(got) > 5
    t = B.new_state("t"); t["seen"] = {sym: b[400]["t"]}
    for m in range(402, n + 1):
        F.step(t, sym, b[:m - 1] + [dict(b[m - 1], closed=False)], "random", random.Random(m))
    assert any(x["kind"] == "sell" for x in t["log"])
    print(f"{sym}: {len(got)} trades match the backtest")
print("ok")
