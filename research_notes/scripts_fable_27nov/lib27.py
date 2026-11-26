"""Shared helpers: trade stats in the report format + random-control comparison."""
import numpy as np, math
def stats(tr):
    """tr: list of (time, ret) -> dict with n, mean, med, wr, ex1, ex5, h1, h2 (all % except n)"""
    tr = sorted(tr); r = np.array([x[1] for x in tr], dtype=float); n = len(r)
    if n < 6: return dict(n=n)
    s = np.sort(r); h = n // 2
    return dict(n=n, mean=r.mean() * 100, med=np.median(r) * 100, wr=(r > 0).mean() * 100,
                ex1=s[:-1].mean() * 100, ex5=(s[:-5].mean() * 100 if n > 10 else float("nan")),
                h1=r[:h].mean() * 100, h2=r[h:].mean() * 100, t=r.mean() / (r.std() + 1e-12) * math.sqrt(n), worst=s[0] * 100, best=s[-1] * 100)
def fmt(name, st, ctl=None):
    if st["n"] < 6: return f"{name:44s} n={st['n']}"
    s = (f"{name:44s} n={st['n']:4d} mean={st['mean']:+6.2f} med={st['med']:+6.2f} wr={st['wr']:3.0f} ex1={st['ex1']:+6.2f} ex5={st['ex5']:+6.2f} "
         f"h1={st['h1']:+6.2f} h2={st['h2']:+6.2f} t={st['t']:+5.1f} worst={st['worst']:+5.0f} best={st['best']:+5.0f}")
    if ctl: s += f" | ctl mean={ctl['mean']:+6.2f} med={ctl['med']:+6.2f} p={ctl['p']:.2f}"
    return s
