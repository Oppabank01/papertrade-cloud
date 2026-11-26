"""Pre-FOMC drift and CPI-day moves in BTC/ETH (Binance spot 1h). Scheduled FOMC statements 2018-2026 at 14:00 New York
(emergency meetings left out). CPI at 08:30 New York, 2021-2025 (dates typed from memory: flagged).
Windows are in hours relative to the event hour T (the bar that contains the release). Enter at a bar open, exit at a bar
close, optional stop checked first. Cost 0.15%/side. Control: same weekday and same clock hour on other weeks (all of them,
plus 200 random draws of the same n)."""
import time, calendar, numpy as np, r2lib as L
FOMC = """2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01 2018-09-26 2018-11-08 2018-12-19
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16 2026-10-28""".split()
CPI = """2021-01-13 2021-02-10 2021-03-10 2021-04-13 2021-05-12 2021-06-10 2021-07-13 2021-08-11 2021-09-14 2021-10-13 2021-11-10 2021-12-10
2022-01-12 2022-02-10 2022-03-10 2022-04-12 2022-05-11 2022-06-10 2022-07-13 2022-08-10 2022-09-13 2022-10-13 2022-11-10 2022-12-13
2023-01-12 2023-02-14 2023-03-14 2023-04-12 2023-05-10 2023-06-13 2023-07-12 2023-08-10 2023-09-13 2023-10-12 2023-11-14 2023-12-12
2024-01-11 2024-02-13 2024-03-12 2024-04-10 2024-05-15 2024-06-12 2024-07-11 2024-08-14 2024-09-11 2024-10-10 2024-11-13 2024-12-11
2025-01-15 2025-02-12 2025-03-12 2025-04-10 2025-05-13 2025-06-11 2025-07-15 2025-08-12 2025-09-11""".split()
def us_dst(y, m, d):
    def nth_sun(y, m, n):
        c = calendar.monthcalendar(y, m); s = [w[6] for w in c if w[6]]; return s[n - 1]
    a = (3, nth_sun(y, 3, 2)); b = (11, nth_sun(y, 11, 1)); return a <= (m, d) < b
def ev_ms(s, hh, mm=0):
    y, m, d = map(int, s.split("-")); off = 4 if us_dst(y, m, d) else 5
    return (calendar.timegm((y, m, d, hh + off, 0, 0)) ) * 1000      # hour bar that contains the release
H = L.H
def run(sym, evs, a_h, b_h, side, stop, name):
    A = L.klines(sym, "1h", 1514764800000); t = A[:, 0].astype(np.int64)
    tr = []
    for T in evs:
        i = int(np.searchsorted(t, T + a_h * H))
        if i >= len(t) or t[i] != T + a_h * H: continue
        x = L.sim(A, i, side, b_h - a_h, stop)
        if x: tr.append((x[0], x[1]))
    st = L.stats(tr)
    if st["n"] < 8: return
    # control: same weekday/hour entries on all other weeks in the same date range
    allr = []; ev_set = set(evs)
    T0 = evs[0] % (7 * 24 * H); ks = range(int((t[0] - T0) // (7 * 24 * H)) + 1, int((t[-1] - T0) // (7 * 24 * H)))
    cand = []
    for k in ks:
        for wd_shift in (0,):
            Tc = T0 + k * 7 * 24 * H
            if Tc in ev_set or Tc < evs[0] - 30 * 24 * H: continue
            i = int(np.searchsorted(t, Tc + a_h * H))
            if i < len(t) and t[i] == Tc + a_h * H:
                x = L.sim(A, i, side, b_h - a_h, stop)
                if x: cand.append(x[1])
    cand = np.array(cand); ms = np.array([np.random.default_rng(z).choice(cand, st["n"]).mean() * 100 for z in range(300)])
    print(L.fmt(name, st, dict(mean=float(cand.mean() * 100), med=float(np.median(cand) * 100), p=float((ms >= st["mean"]).mean()))))
for lab, days, hh in (("FOMC", FOMC, 14), ("CPI", CPI, 8)):
    evs = [ev_ms(s, hh) for s in days]
    print(f"\n=== {lab}: {len(evs)} events, first {L.ts(evs[0])} last {L.ts(evs[-1])} UTC ===")
    for sym in ("BTCUSDT", "ETHUSDT"):
        for a_h, b_h in ((-24, 0), (-48, 0), (-12, 0), (-72, 0), (-24, -1), (0, 1), (0, 4), (0, 24), (1, 25), (2, 26), (-24, 24), (0, 72)):
            for side in (1, -1):
                for stop in (None, 0.05):
                    if stop and (b_h - a_h) < 24: continue
                    run(sym, evs, a_h, b_h, side, stop, f"{lab} {sym[:3]} {'long' if side>0 else 'short'} T{a_h:+d}h..T{b_h:+d}h stop {stop}")
