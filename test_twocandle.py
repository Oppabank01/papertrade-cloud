"""twocandle.py walking bars one at a time = the backtest rule (session on, hold 3) with one position per coin."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import twocandle as T, byttrade as B

b = [dict(x, closed=True) for x in mts.bars("binance", "SOLUSDT", "4h")[-900:]]
col, want, i = T.colors(b), [], 200
while i < len(b) - 4:
    sig, nxt = b[i], b[i + 1]
    d, f = col.get(sig["t"] // B.DAY - 1), (sig["c"] > sig["o"]) - (sig["c"] < sig["o"])
    if (nxt["t"] // 3_600_000) % 24 not in T.SESSIONS or not d or d != f or (nxt["o"] - (sig["l"] if d > 0 else sig["h"])) * d <= 0:
        i += 1; continue
    e, stop = nxt["o"], sig["l"] if d > 0 else sig["h"]
    tgt, px, j = e + (e - stop), None, i + 1
    for j in range(i + 1, i + 4):
        x = b[j]
        if (x["l"] <= stop) if d > 0 else (x["h"] >= stop): px = stop; break
        if (x["h"] >= tgt) if d > 0 else (x["l"] <= tgt): px = tgt; break
    px = b[j]["c"] if px is None else px
    want.append(round((px / e - 1) * d, 5)); i = j      # the exit bar can be the next signal bar, as in twocandle.py
s = B.new_state("t"); s.pop("seen"); s["seen"] = {"SOLUSDT": b[199]["t"]}
for k in range(201, len(b) + 1):
    T.step(s, "SOLUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)])
got = [x["ret"] for x in s["log"] if x["kind"] == "sell"]
n = min(len(got), len(want)); assert got[:n] == want[:n] and abs(len(want) - len(got)) <= 1, (len(got), len(want), got[:5], want[:5])
print(f"{len(got)} trades match, mean {sum(got) / len(got):+.3%}"); print("ok")
