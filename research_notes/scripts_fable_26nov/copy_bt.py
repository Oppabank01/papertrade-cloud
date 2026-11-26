# Copy-trade backtest: rank wallets on the earlier half (realized PnL), copy their later buys, compare with random-wallet / random-time controls.
import pickle, random, statistics as S, bisect, sys, math, time
from collections import defaultdict
SOL = "So11111111111111111111111111111111111111112"
COST, STOP, ARM, TRAIL, DELAY, CHASE, LIQ, MINBUY = 0.02, 0.08, 0.20, 0.15, 30, 0.10, 35000, 10
grad = pickle.load(open("../grad.pkl", "rb")); raw = pickle.load(open("raw.pkl", "rb"))
import os
rpc = pickle.load(open("rpc.pkl", "rb")) if os.path.exists("rpc.pkl") else {}
SRC = {}
P = {}   # pool -> dict(bars, ts, res, px, sym)
EV = []  # (t, wallet, pool, side, tokens, usd, price)
for m, v in grad.items():
    if not v or not v.get("bars"): continue
    p = v["pool"]
    if p not in raw["trades"] and p not in rpc: continue
    rows = raw["trades"][p]["rows"] if p in raw["trades"] else rpc[p]["rows"]; SRC[p] = "gecko" if p in raw["trades"] else "rpc"
    if not rows: continue
    b = {x[0]: x for x in v["bars"]}
    for x in raw["bars2"].get(p, []): b[x[0]] = x
    bars = [b[k] for k in sorted(b)]
    inf = raw["info"].get(p, {})
    P[p] = dict(bars=bars, ts=[x[0] for x in bars], res=inf.get("res", 0), px=inf.get("px", 0), sym=v["sym"])
    for (t, w, kind, fa, ta, fam, tam, pf, pt, vol, th) in rows:
        if fa == SOL and ta != SOL: EV.append((t, w, p, "buy", tam, vol, pt))
        elif ta == SOL and fa != SOL: EV.append((t, w, p, "sell", fam, vol, pf))
EV.sort()
def liq(p, price):
    d = P[p]
    return d["res"] * math.sqrt(price / d["px"]) if d["px"] > 0 and price > 0 else 0
def realized(evs):
    """average-cost realized PnL per wallet; sells matched only against observed inventory"""
    inv = defaultdict(lambda: [0.0, 0.0]); pnl = defaultdict(float); coins = defaultdict(set); wins = defaultdict(lambda: defaultdict(float))
    for t, w, p, side, tok, usd, px in evs:
        s = inv[(w, p)]
        if side == "buy": s[0] += tok; s[1] += usd
        elif s[0] > 0:
            q = min(tok, s[0]); cost = s[1] * q / s[0]; g = usd * q / tok - cost
            s[0] -= q; s[1] -= cost; pnl[w] += g; coins[w].add(p); wins[w][p] += g
    return pnl, coins, wins
def sim(p, t_sig, fill, t_exit=None, use_liq=True, chase=True):
    """returns (ret, entry_t, exit_t, why) or None if filtered"""
    d = P[p]; bars = d["bars"]; i = bisect.bisect_left(d["ts"], t_sig + DELAY)
    if i >= len(bars) or bars[i][0] - t_sig > 300: return None
    e = bars[i][1]
    if e <= 0: return None
    if chase and fill > 0 and e > fill * (1 + CHASE): return None
    if use_liq and liq(p, e) < LIQ: return None
    peak = e; x = None; why = "end"
    for j in range(i, len(bars)):
        t, o, h, l, c, vol = bars[j]
        if t_exit is not None and t >= t_exit + DELAY and j > i: x, why = o, "leader"; break
        sp = e * (1 - STOP) if peak < e * (1 + ARM) else max(peak * (1 - TRAIL), e * (1 - STOP))
        if l <= sp: x, why = min(o, sp), ("trail" if peak >= e * (1 + ARM) else "stop"); break
        peak = max(peak, h)
    if x is None: x = bars[-1][4]; t = bars[-1][0]
    return (x / e * (1 - COST) ** 2 - 1, bars[i][0], t, why)
def rep(name, r):
    if len(r) < 2: print(f"{name:<34} n {len(r)}"); return
    m = S.mean(r); sd = S.stdev(r) or 1e-9; s = sorted(r)
    x1 = S.mean(s[:-1]); x5 = S.mean(s[:-5]) if len(s) > 5 else float("nan")
    print(f"{name:<34} n {len(r):5d} mean {m:+7.2%} med {S.median(r):+7.2%} win {sum(x>0 for x in r)/len(r):4.0%} t {m/sd*len(r)**.5:+5.2f} exbest {x1:+7.2%} extop5 {x5:+7.2%} best {s[-1]:+.0%}")
def run(K=20, use_liq=True, rank="pnl", seed=1, verbose=True, split_q=0.5, mincoins=2):
    Tsplit = EV[int(len(EV) * split_q)][0]
    IS = [e for e in EV if e[0] < Tsplit]; OOS = [e for e in EV if e[0] >= Tsplit]
    pnl, coins, wins = realized(IS)
    elig = [w for w in pnl if len(coins[w]) >= mincoins and pnl[w] > 0]
    if rank == "pnl": elig.sort(key=lambda w: -pnl[w])
    else: elig.sort(key=lambda w: (-sum(g > 0 for g in wins[w].values()) / len(wins[w]), -pnl[w]))
    leaders = set(elig[:K])
    sells = defaultdict(list)
    for t, w, p, side, tok, usd, px in OOS:
        if side == "sell": sells[(w, p)].append(t)
    def nxt_sell(w, p, t):
        s = sells.get((w, p), []); k = bisect.bisect_right(s, t); return s[k] if k < len(s) else None
    rule, busy, ctrl, ctrl_by_pool, lead_sizes = [], {}, [], defaultdict(list), []
    for t, w, p, side, tok, usd, px in OOS:
        if side != "buy" or usd < MINBUY: continue
        r = sim(p, t, px, nxt_sell(w, p, t), use_liq)
        if r is None: continue
        if w in leaders:
            lead_sizes.append(usd)
            if busy.get(p, 0) > r[1]: continue   # already holding this coin
            busy[p] = r[2]; rule.append((r[1], r[2], r[0], p, w, r[3], usd))
        else:
            ctrl.append((r[0], usd)); ctrl_by_pool[p].append(r[0])
    rr = [x[2] for x in rule]; rng = random.Random(seed)
    # control B: random minute in the same coin, OOS span, same filters except no leader exit
    cb = []
    for _ in range(200):
        for x in rule:
            d = P[x[3]]; lo = bisect.bisect_left(d["ts"], Tsplit)
            for _try in range(20):
                if lo >= len(d["ts"]): break
                tt = d["ts"][rng.randrange(lo, len(d["ts"]))] - DELAY
                r = sim(x[3], tt, 0, None, use_liq, chase=False)
                if r: cb.append(r[0]); break
    out = dict(K=K, liq=use_liq, rank=rank, n=len(rr), mean=S.mean(rr) if rr else float("nan"))
    if not verbose: return out, rr, [c[0] for c in ctrl]
    print(f"\n=== K={K} liq>={LIQ if use_liq else 0} rank={rank} mincoins={mincoins}  split {time.strftime('%d %b %H:%M', time.gmtime(Tsplit+7*3600))} +07  IS events {len(IS)} OOS events {len(OOS)}")
    print(f"eligible wallets (>=2 coins closed, pnl>0) {len(elig)}; leaders {len(leaders)}; leaders with an OOS trade taken {len({x[4] for x in rule})}; coins traded {len({x[3] for x in rule})}")
    print("exit reasons", {k: sum(1 for x in rule if x[5] == k) for k in ("stop", "trail", "leader", "end")})
    rep("RULE copy leaders", rr)
    cc = [c[0] for c in ctrl]; rep("CTRL A all non-leader buys", cc)
    if lead_sizes:
        q = sorted(lead_sizes)[len(lead_sizes) // 4]; rep(f"CTRL A2 non-leader buys >=${q:.0f}", [c[0] for c in ctrl if c[1] >= q])
    cm = [rng.choice(ctrl_by_pool[x[3]]) for _ in range(200) for x in rule if ctrl_by_pool[x[3]]]
    rep("CTRL A3 same-coin non-leader buy", cm); rep("CTRL B same-coin random minute", cb)
    if rr and len(cc) >= len(rr):
        n = len(rr); m = S.mean(rr); bs = [S.mean(rng.sample(cc, n)) for _ in range(3000)]
        print(f"p(random-wallet draw of n={n} has mean >= rule) = {sum(b >= m for b in bs)/len(bs):.3f};  ctrl draw mean 5%..95%: {sorted(bs)[150]:+.2%} .. {sorted(bs)[2850]:+.2%}")
        md = S.median(rr); bm = [S.median(rng.sample(cc, n)) for _ in range(3000)]
        print(f"p(random-wallet draw median >= rule median) = {sum(b >= md for b in bm)/len(bm):.3f}")
    # portfolio: 20% of equity per trade, max 2 open
    eq, open_, taken = 1.0, [], 0
    for et, xt, r, p, w, why, usd in sorted(rule):
        for o in [o for o in open_ if o[0] <= et]: eq += o[1]; open_.remove(o)
        if len(open_) < 2: open_.append((xt, eq * 0.2 * r)); taken += 1
    eq += sum(o[1] for o in open_)
    print(f"portfolio 20%/trade max 2 open: took {taken}/{len(rule)} trades, equity {eq-1:+.2%}")
    return out, rr, cc
def diag_hold(K=20, mincoins=1, hold=1800, split_q=0.5):
    """NOT the rule: no stop/trail, just hold 30 min (or to last bar). Shows whether leader buys carry any raw signal."""
    Tsplit = EV[int(len(EV) * split_q)][0]
    pnl, coins, wins = realized([e for e in EV if e[0] < Tsplit])
    elig = sorted([w for w in pnl if len(coins[w]) >= mincoins and pnl[w] > 0], key=lambda w: -pnl[w]); leaders = set(elig[:K])
    L, C = [], []
    for t, w, p, side, tok, usd, px in EV:
        if t < Tsplit or side != "buy" or usd < MINBUY: continue
        d = P[p]; i = bisect.bisect_left(d["ts"], t + DELAY)
        if i >= len(d["bars"]) or d["bars"][i][0] - t > 300: continue
        e = d["bars"][i][1]; j = min(bisect.bisect_right(d["ts"], d["bars"][i][0] + hold) - 1, len(d["bars"]) - 1)
        if e <= 0: continue
        (L if w in leaders else C).append(d["bars"][j][4] / e * (1 - COST) ** 2 - 1)
    print(f"\n--- diagnostic, not the rule: 30-min hold, no stop, 2% per side (K={K}, mincoins={mincoins}) ---")
    rep("leader buys", L); rep("non-leader buys", C)
if __name__ == "__main__":
    print("pools with trades", len(P), "(gecko", sum(v == "gecko" for v in SRC.values()), "rpc", sum(v == "rpc" for v in SRC.values()), ")", "events", len(EV), "wallets", len({e[1] for e in EV}), "buys", sum(e[3] == "buy" for e in EV))
    tt = [e[0] for e in EV]; print("event span +07:", time.strftime('%d %b %H:%M', time.gmtime(tt[0]+7*3600)), "to", time.strftime('%d %b %H:%M', time.gmtime(tt[-1]+7*3600)))
    print("pools with est. liquidity now >= 35K:", sum(1 for d in P.values() if d["res"] >= LIQ), " ever >=35K (by peak bar close):", sum(1 for p, d in P.items() if max(liq(p, x[4]) for x in d["bars"]) >= LIQ))
    # skill persistence: in-sample vs out-of-sample realized PnL of the same wallets
    Ts = EV[len(EV) // 2][0]; a, ca, _ = realized([e for e in EV if e[0] < Ts]); b, cb_, _ = realized([e for e in EV if e[0] >= Ts])
    both = [w for w in a if w in b]
    if len(both) > 5:
        ra = {w: i for i, w in enumerate(sorted(both, key=lambda w: a[w]))}; rb = {w: i for i, w in enumerate(sorted(both, key=lambda w: b[w]))}
        n = len(both); rho = 1 - 6 * sum((ra[w] - rb[w]) ** 2 for w in both) / (n * (n * n - 1))
        top = sorted(both, key=lambda w: -a[w])[:20]
        print(f"wallets with realized PnL in both halves {n}; Spearman IS vs OOS PnL {rho:+.3f}; top-20 IS wallets: {sum(b[w] > 0 for w in top)}/{len(top)} positive OOS, sum OOS ${sum(b[w] for w in top):+.0f}; all wallets positive OOS {sum(b[w] > 0 for w in both)/n:.0%}")
    run(20, True, "pnl")                       # primary (pre-registered): rule as stated, leaders need >=2 coins
    run(20, False, "pnl")                      # same without the liquidity filter (more trades)
    run(20, True, "pnl", mincoins=1)           # looser leaderboard: >=1 coin with a closed round trip
    run(20, False, "pnl", mincoins=1)
    print("\n--- sensitivity (one line each: rule vs random-wallet control) ---")
    n_trials = 4
    for K in (10, 50):
        for lq in (True, False):
            for mc in (2, 1):
                o, rr, cc = run(K, lq, "pnl", verbose=False, mincoins=mc); n_trials += 1
                rep(f"K={K} liq={int(lq)} mc={mc} RULE", rr); rep("    ctrl", cc)
    for lq in (True, False):
        o, rr, cc = run(20, lq, "winrate", verbose=False, mincoins=1); n_trials += 1; rep(f"rank=winrate K=20 liq={int(lq)} mc=1 RULE", rr); rep("    ctrl", cc)
    for q in (0.35, 0.65):
        o, rr, cc = run(20, False, "pnl", verbose=False, mincoins=1, split_q=q); n_trials += 1; rep(f"split={q} K=20 liq=0 mc=1 RULE", rr); rep("    ctrl", cc)
    print("configurations tried:", n_trials)
    diag_hold(20, 1); diag_hold(20, 2)
