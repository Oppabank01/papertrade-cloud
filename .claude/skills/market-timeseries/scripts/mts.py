#!/usr/bin/env python3
"""market-timeseries: fetch bars, run honest backtests, check forecast claims. Standard library only.

  mts.py data   binance BTCUSDT 1d            # cache bars, print range
  mts.py trend  binance BTCUSDT [--cost 0.0035] [--lookbacks 10,20,50,100,200] [--holdout 0.3]
  mts.py bracket gecko MINT1,MINT2 [--stops -0.08,-0.15] [--targets 0.2,0.4] [--hold 96] [--every 16]
  mts.py forecast preds.csv                   # columns: actual,pred (returns, same horizon)

Sources: binance (api.binance.com spot, from 2017), binanceth (api.binance.th, last 1000 bars),
yahoo (stocks/ETFs, daily), gecko (Solana token mint -> deepest pool, 15m bars, ~10 days).
"""
import argparse
import csv
import json
import math
import statistics as st
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import stats as S  # noqa: E402

CACHE = Path.home() / ".cache" / "market-timeseries"
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


# ---------- data ----------

def _binance(base, sym, interval, full):
    out, start = [], 0
    while True:
        k = get(f"{base}/klines?symbol={sym}&interval={interval}&limit=1000" + (f"&startTime={start}" if full else ""))
        out += [dict(t=x[0], o=float(x[1]), h=float(x[2]), l=float(x[3]), c=float(x[4]), v=float(x[5]), close_t=x[6]) for x in k]
        if not full or len(k) < 1000:
            break
        start = k[-1][0] + 1
        time.sleep(0.3)
    now = time.time() * 1000
    return [b for b in out if b.pop("close_t") < now]          # closed bars only


def _yahoo(sym, interval):
    # range=max silently returns monthly bars; an explicit period keeps the requested interval
    r = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=0&period2={int(time.time())}&interval={interval}&events=split,div")["chart"]["result"][0]
    q, adj = r["indicators"]["quote"][0], (r["indicators"].get("adjclose") or [{}])[0].get("adjclose")
    out = []
    for i, t in enumerate(r["timestamp"]):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c) or not c:
            continue
        f = (adj[i] / c) if adj and adj[i] else 1.0                 # dividend/split adjusted, same factor on OHLC
        out.append(dict(t=t * 1000, o=o * f, h=h * f, l=l * f, c=c * f, v=q["volume"][i] or 0))
    return out[:-1] if out and time.time() - out[-1]["t"] / 1000 < 86400 else out   # drop today's live bar


def _gecko(mint, minutes=15):
    pools = [p for p in get(f"https://api.dexscreener.com/tokens/v1/solana/{mint}") if p.get("chainId") == "solana"]
    pool = max(pools, key=lambda p: (p.get("liquidity") or {}).get("usd", 0))["pairAddress"]
    L = get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/minute?aggregate={minutes}&limit=1000")
    return [dict(t=x[0] * 1000, o=x[1], h=x[2], l=x[3], c=x[4], v=x[5]) for x in reversed(L["data"]["attributes"]["ohlcv_list"])]


def bars(source, sym, interval="1d", max_age_h=12):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{source}_{sym}_{interval}.json"
    if f.exists() and time.time() - f.stat().st_mtime < max_age_h * 3600:
        return json.loads(f.read_text())
    b = {"binance": lambda: _binance("https://api.binance.com/api/v3", sym, interval, True),
         "binanceth": lambda: _binance("https://api.binance.th/api/v1", sym, interval, False),
         "yahoo": lambda: _yahoo(sym, interval),
         "gecko": lambda: _gecko(sym)}[source]()
    f.write_text(json.dumps(b))
    return b


def periods_per_year(source):
    return 252 if source == "yahoo" else 365


def day(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d")


# ---------- trend rules (long or flat, decided at the close, earning from the next bar) ----------

def positions(c, h, l, rule, n):
    pos, p = [0] * len(c), 0
    for i in range(n, len(c)):
        if rule == "tsmom":
            p = 1 if c[i] > c[i - n] else 0
        elif rule == "sma":
            p = 1 if c[i] > sum(c[i - n + 1:i + 1]) / n else 0
        elif rule == "breakout":   # Donchian: enter above the prior n-bar high, exit below the prior n/2-bar low
            if not p and c[i] > max(h[i - n:i]):
                p = 1
            elif p and c[i] < min(l[i - max(2, n // 2):i]):
                p = 0
        pos[i] = p
    return pos


def strat_returns(c, pos, cost, start):
    """r[t] = pos[t-1] * bar return - cost on every change of position (cost = one side incl. slippage)."""
    out = []
    for t in range(start, len(c)):
        r = pos[t - 1] * (c[t] / c[t - 1] - 1)
        out.append(r - cost * abs(pos[t - 1] - pos[t - 2]))
    return out


def ledger(key, n):
    """Count every configuration ever tried on a dataset: the honest N for deflating Sharpe."""
    f = CACHE / "trials.jsonl"
    with f.open("a") as o:
        o.write(json.dumps(dict(t=int(time.time()), key=key, n=n)) + "\n")
    return sum(json.loads(x)["n"] for x in f.read_text().splitlines() if json.loads(x)["key"] == key)


def line(name, r, ppy, pos=None):
    tot = math.prod(1 + x for x in r) - 1
    yrs = len(r) / ppy
    cagr = (1 + tot) ** (1 / yrs) - 1 if yrs and tot > -1 else -1
    s = f"{name:<16} total {tot:+8.0%}  CAGR {cagr:+6.1%}  Sharpe {S.sharpe(r) * math.sqrt(ppy):5.2f}  maxDD {S.max_drawdown(r):5.1%}"
    if pos is not None:
        s += f"  in market {sum(pos) / len(pos):4.0%}  trades {sum(abs(a - b) for a, b in zip(pos[1:], pos)) // 2}"
    return s


def cmd_trend(a):
    b = bars(a.source, a.symbol, a.interval)
    c, h, l = [x["c"] for x in b], [x["h"] for x in b], [x["l"] for x in b]
    lbs = [int(x) for x in a.lookbacks.split(",")]
    start = max(lbs) + 2
    ppy = periods_per_year(a.source)
    bh = [c[t] / c[t - 1] - 1 for t in range(start, len(c))]
    trials = {}
    for rule in a.rules.split(","):
        for n in lbs:
            p = positions(c, h, l, rule, n)
            trials[f"{rule}{n}"] = (strat_returns(c, p, a.cost, start), p[start - 1:-1])
    total = ledger(f"{a.source}:{a.symbol}:{a.interval}", len(trials))
    print(f"{a.symbol} {a.interval} {day(b[start]['t'])} to {day(b[-1]['t'])}, {len(bh)} bars, cost {a.cost:.2%} per side")
    print(line("buy and hold", bh, ppy))
    for k, (r, p) in trials.items():
        print(line(k, r, ppy, p))
    srs = [S.sharpe(r) for r, _ in trials.values()]
    best = max(trials, key=lambda k: S.sharpe(trials[k][0]))
    print(f"\nBest in full sample: {best}. Trials this run {len(trials)}, ever on this data {total}.")
    print(f"  DSR (prob. true Sharpe > 0 after {len(trials)} tries): {S.dsr(trials[best][0], srs):.2f}   PSR vs 0: {S.psr(trials[best][0]):.2f}")
    print(f"  DSR vs buy-and-hold is not computed; compare the lines above. Excess over B&H: "
          f"Sharpe diff {(S.sharpe(trials[best][0]) - S.sharpe(bh)) * math.sqrt(ppy):+.2f}")
    m = [list(row) for row in zip(*[r for r, _ in trials.values()])]
    pb, nc = S.pbo(m)
    print(f"  PBO (CSCV, 16 blocks, {nc} splits): {pb:.2f}  (above 0.05 = the in-sample pick is not reliable)")
    cut = int(len(bh) * (1 - a.holdout))
    pick = max(trials, key=lambda k: S.sharpe(trials[k][0][:cut]))
    print(f"\nWalk-forward: choose on first {1 - a.holdout:.0%} ({day(b[start]['t'])}..{day(b[start + cut]['t'])}), test once on the rest")
    print(f"  picked {pick}")
    print("  " + line(f"{pick} OOS", trials[pick][0][cut:], ppy))
    print("  " + line("B&H OOS", bh[cut:], ppy))
    print("\nBy year (picked rule vs buy and hold):")
    yrs = {}
    for i, t in enumerate(range(start, len(c))):
        yrs.setdefault(day(b[t]["t"])[:4], []).append((trials[pick][0][i], bh[i]))
    for y, v in yrs.items():
        print(f"  {y}: {math.prod(1 + x for x, _ in v) - 1:+7.1%}  vs  {math.prod(1 + z for _, z in v) - 1:+7.1%}")


# ---------- bracket (stop / target) on candles ----------

def bracket_trade(b, i, stop, tp, hold, cost):
    """Enter at bar i close. Bar high/low decide exits; a bar touching both counts as the stop (conservative)."""
    e = b[i]["c"]
    gross = None
    for x in b[i + 1:i + 1 + hold]:
        if x["o"] <= e * (1 + stop):         # gapped through the stop: fill at the open
            gross = x["o"] / e - 1
            break
        if x["l"] <= e * (1 + stop):
            gross = stop
            break
        if x["h"] >= e * (1 + tp):
            gross = tp
            break
    if gross is None:
        gross = b[min(i + hold, len(b) - 1)]["c"] / e - 1
    return (1 + gross) * (1 - cost) ** 2 - 1


def cmd_bracket(a):
    data = {}
    for s in a.symbols.split(","):
        try:
            data[s] = bars(a.source, s, a.interval)
        except Exception as e:
            print(f"skip {s[:10]}: {str(e)[:60]}")
        time.sleep(a.sleep)
    print(f"{len(data)} series, entries every {a.every} bars, max hold {a.hold} bars, cost {a.cost:.2%} per side")
    print("Survivorship warning: series picked today (volume leaders, listed coins) over-represent survivors.\n")
    combos = [(float(s), float(t)) for s in a.stops.split(",") for t in a.targets.split(",")]
    for sp, tp in combos:
        r = [bracket_trade(b, i, sp, tp, a.hold, a.cost) for b in data.values() for i in range(0, len(b) - a.hold - 1, a.every) if b[i]["c"] > 0]
        if r:
            d = S.trade_summary(r)
            print(f"stop {sp:+.0%} target {tp:+.0%}: n {d['n']} win {d['win']:.0%} mean {d['mean']:+.2%} "
                  f"[{d['ci95'][0]:+.2%},{d['ci95'][1]:+.2%}] median {d['median']:+.2%} mean w/o top1% {d['mean_wo_top1pct']:+.2%}")
    r = [b[i + a.hold]["c"] / b[i]["c"] * (1 - a.cost) ** 2 - 1 for b in data.values() for i in range(0, len(b) - a.hold - 1, a.every) if b[i]["c"] > 0]
    if r:
        d = S.trade_summary(r)
        print(f"hold only:            n {d['n']} win {d['win']:.0%} mean {d['mean']:+.2%} median {d['median']:+.2%} mean w/o top1% {d['mean_wo_top1pct']:+.2%}")
    print(f"\n{len(combos) + 1} configurations tried: the best one is optimistic by construction.")


# ---------- forecast claims ----------

def cmd_forecast(a):
    rows = list(csv.DictReader(open(a.csv)))
    y = [float(r["actual"]) for r in rows]
    p = [float(r["pred"]) for r in rows]
    n = len(y)
    base = {"zero (random walk)": [0.0] * n, "persistence (last value)": [0.0] + y[:-1]}
    print(f"{n} forecasts")
    for name, bp in base.items():
        em, eb = [a_ - b_ for a_, b_ in zip(y, p)], [a_ - b_ for a_, b_ in zip(y, bp)]
        stat, pv = S.dm_test(em, eb)
        print(f"vs {name}: MAE {st.fmean(map(abs, em)):.5f} vs {st.fmean(map(abs, eb)):.5f}, DM one-sided p {pv:.3f}")
    hit = sum((pi > 0) == (yi > 0) for pi, yi in zip(p, y)) / n
    up = sum(yi > 0 for yi in y) / n
    z = (hit - max(up, 1 - up)) / math.sqrt(max(up, 1 - up) * (1 - max(up, 1 - up)) / n)
    print(f"direction hit rate {hit:.1%} vs always-guess-majority {max(up, 1 - up):.1%} (z {z:+.2f}, p {1 - S.N.cdf(z):.3f})")
    print("A model only counts if it beats these baselines with p < 0.05 after counting how many models were tried.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("data")
    d.add_argument("source"); d.add_argument("symbol"); d.add_argument("interval", nargs="?", default="1d")
    t = sub.add_parser("trend")
    t.add_argument("source"); t.add_argument("symbol"); t.add_argument("--interval", default="1d")
    t.add_argument("--rules", default="tsmom,sma,breakout"); t.add_argument("--lookbacks", default="10,20,50,100,200")
    t.add_argument("--cost", type=float, default=0.0035, help="one side, fee+slippage (Binance TH 0.25%%+0.1%%)")
    t.add_argument("--holdout", type=float, default=0.3)
    br = sub.add_parser("bracket")
    br.add_argument("source"); br.add_argument("symbols"); br.add_argument("--interval", default="15m")
    br.add_argument("--stops", default="-0.08,-0.15,-0.25"); br.add_argument("--targets", default="0.2,0.4,1.0")
    br.add_argument("--hold", type=int, default=96); br.add_argument("--every", type=int, default=16)
    br.add_argument("--cost", type=float, default=0.02); br.add_argument("--sleep", type=float, default=6.0)
    f = sub.add_parser("forecast")
    f.add_argument("csv")
    a = ap.parse_args()
    if a.cmd == "data":
        b = bars(a.source, a.symbol, a.interval)
        print(f"{a.symbol}: {len(b)} bars {day(b[0]['t'])} to {day(b[-1]['t'])}, cached in {CACHE}")
    else:
        {"trend": cmd_trend, "bracket": cmd_bracket, "forecast": cmd_forecast}[a.cmd](a)


if __name__ == "__main__":
    main()
