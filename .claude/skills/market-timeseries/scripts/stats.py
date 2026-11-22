"""Honest-evaluation statistics, standard library only.

Sources (see ../references/evidence.md):
  PSR / DSR  Bailey & Lopez de Prado 2014, SSRN 2460551
  PBO (CSCV) Bailey, Borwein, Lopez de Prado, Zhu 2015, SSRN 2326253
  DM test    Diebold & Mariano 1995 (one-sided, h=1 unless given)
  Permutation test on OHLC bars: Masters, "Permutation and Randomization Tests for Trading System Development" (2020)
"""
import math
import random
import statistics as st
from itertools import combinations

N = st.NormalDist()
EULER = 0.5772156649


def sharpe(r):
    """Per-period Sharpe (not annualized). 0 when flat."""
    if len(r) < 2:
        return 0.0
    sd = st.pstdev(r)
    return st.fmean(r) / sd if sd else 0.0


def moments(r):
    m, sd = st.fmean(r), st.pstdev(r)
    if not sd:
        return 0.0, 3.0
    skew = sum((x - m) ** 3 for x in r) / len(r) / sd ** 3
    kurt = sum((x - m) ** 4 for x in r) / len(r) / sd ** 4   # raw kurtosis, normal = 3
    return skew, kurt


def psr(r, sr_star=0.0):
    """Probability that the true per-period Sharpe exceeds sr_star, given skew/kurtosis and length."""
    t, sr = len(r), sharpe(r)
    g3, g4 = moments(r)
    den = 1 - g3 * sr + (g4 - 1) / 4 * sr * sr
    if t < 3 or den <= 0:
        return 0.0
    return N.cdf((sr - sr_star) * math.sqrt(t - 1) / math.sqrt(den))


def expected_max_sharpe(trial_sharpes):
    """SR0: the best Sharpe you would expect from len(trials) tries when every true Sharpe is zero."""
    n = len(trial_sharpes)
    if n < 2:
        return 0.0
    v = st.pvariance(trial_sharpes)
    return math.sqrt(v) * ((1 - EULER) * N.inv_cdf(1 - 1 / n) + EULER * N.inv_cdf(1 - 1 / (n * math.e)))


def dsr(best_returns, trial_sharpes):
    """Deflated Sharpe Ratio of the chosen strategy, judged against all trials that were tried."""
    return psr(best_returns, expected_max_sharpe(trial_sharpes))


def pbo(matrix, blocks=16):
    """Probability of backtest overfitting via CSCV.
    matrix: list of rows (time), each a list of per-config returns. Returns (pbo, n_combos).
    Uses per-block sums so 12,870 combos stay fast in pure Python."""
    t, n = len(matrix), len(matrix[0])
    if n < 2 or t < blocks * 2:
        return float("nan"), 0
    size = t // blocks
    agg = []  # per block, per config: (count, sum, sumsq)
    for b in range(blocks):
        rows = matrix[b * size:(b + 1) * size]
        agg.append([(len(rows), sum(r[j] for r in rows), sum(r[j] ** 2 for r in rows)) for j in range(n)])

    def sr(sel, j):
        c = sum(agg[b][j][0] for b in sel)
        s = sum(agg[b][j][1] for b in sel)
        q = sum(agg[b][j][2] for b in sel)
        var = q / c - (s / c) ** 2
        return (s / c) / math.sqrt(var) if var > 1e-18 else 0.0

    below, total = 0, 0
    for is_sel in combinations(range(blocks), blocks // 2):
        oos_sel = [b for b in range(blocks) if b not in is_sel]
        is_sr = [sr(is_sel, j) for j in range(n)]
        best = max(range(n), key=is_sr.__getitem__)
        oos = [sr(oos_sel, j) for j in range(n)]
        rank = sum(x < oos[best] for x in oos) + 0.5 * (sum(x == oos[best] for x in oos) - 1) + 1
        w = rank / (n + 1)
        below += math.log(w / (1 - w)) <= 0
        total += 1
    return below / total, total


def bootstrap_mean_ci(x, n=2000, alpha=0.05, seed=7):
    """Percentile CI of the mean (iid resampling; fine for trade lists, too narrow for autocorrelated daily series)."""
    if len(x) < 2:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    means = sorted(st.fmean(rng.choices(x, k=len(x))) for _ in range(n))
    return means[int(n * alpha / 2)], means[int(n * (1 - alpha / 2)) - 1]


def trade_summary(x):
    """What an honest trade report shows: mean AND median, the mean without the best 1%, win rate, CI."""
    s = sorted(x)
    k = max(1, len(s) // 100)
    lo, hi = bootstrap_mean_ci(x)
    return dict(n=len(x), mean=st.fmean(x), median=st.median(x), mean_wo_top1pct=st.fmean(s[:-k]) if len(s) > k else float("nan"),
                win=sum(v > 0 for v in x) / len(x), ci95=(lo, hi), best=s[-1], worst=s[0])


def max_drawdown(returns):
    eq = peak = 1.0
    dd = 0.0
    for r in returns:
        eq *= 1 + r
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    return dd


def dm_test(err_model, err_base, h=1, power=2):
    """One-sided Diebold-Mariano: small p means the model's loss is lower than the baseline's.
    Uses a Newey-West variance with h-1 lags."""
    d = [abs(a) ** power - abs(b) ** power for a, b in zip(err_model, err_base)]
    t, m = len(d), st.fmean(d)
    gamma = lambda k: sum((d[i] - m) * (d[i - k] - m) for i in range(k, t)) / t
    var = gamma(0) + 2 * sum(gamma(k) for k in range(1, h))
    if var <= 0:
        return 0.0, 1.0
    stat = m / math.sqrt(var / t)
    return stat, N.cdf(stat)


def permute_bars(b, start=1, rng=None):
    """A pattern-free copy of OHLC bars: the close-to-open gaps and the intrabar moves (open to high, low, close) of the
    bars from `start` on are shuffled separately in log space, then prices are rebuilt from the last untouched close.
    Bars before `start` stay as they are, the final close is unchanged and every bar keeps a valid high/low.
    Use start=1 for an in-sample test, start = end of the first training window for a walk-forward test."""
    rng = rng or random.Random()
    start = max(1, start)
    tail = b[start:]
    gaps = [math.log(x["o"] / prev["c"]) for prev, x in zip(b[start - 1:-1], tail)]
    moves = [(math.log(x["h"] / x["o"]), math.log(x["l"] / x["o"]), math.log(x["c"] / x["o"])) for x in tail]
    rng.shuffle(gaps)
    rng.shuffle(moves)
    out, c = [dict(x) for x in b[:start]], b[start - 1]["c"]
    for x, g, (h, l, cl) in zip(tail, gaps, moves):
        o = c * math.exp(g)
        c = o * math.exp(cl)
        out.append(dict(x, o=o, h=o * math.exp(h), l=o * math.exp(l), c=c))
    return out


def permutation_test(score, b, n=1000, start=1, seed=7):
    """score(bars) must run the WHOLE search (every rule and setting you tried) and return its best result, so each
    permuted path gets the same chance to look good by luck. Returns (real, p, permuted results).
    p = (1 + paths that matched or beat the real result) / (n + 1); below 0.01 in-sample or 0.05 walk-forward (1 year)
    means the edge is unlikely to come from noise."""
    rng = random.Random(seed)
    real = score(b)
    dist = [score(permute_bars(b, start, rng)) for _ in range(n)]
    return real, (1 + sum(v >= real for v in dist)) / (n + 1), dist
