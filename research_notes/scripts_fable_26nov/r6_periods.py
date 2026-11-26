import numpy as np, time, sys
import r6_delist as R
bounds = [("2025-07", "2025-12"), ("2026-01", "2026-03"), ("2026-04", "2026-05"), ("2026-06", "2026-11")]
for lag, hold, stop in ((5, 60, .3), (15, 60, .3), (15, 120, .3), (15, 240, .3), (15, 600, .3), (30, 240, .3), (15, 240, .15)):
    tr = R.run("both", lag, hold, stop, 0.003, show=False); out = []
    for a, b in bounds:
        r = np.array([x[1] for x in tr if a <= time.strftime("%Y-%m", time.gmtime(x[0] / 1000)) <= b])
        out.append(f"{a}..{b}: n={len(r)} mean={r.mean()*100:+.1f} med={np.median(r)*100:+.1f} wr={(r>0).mean()*100:.0f}")
    print(f"lag{lag} hold{hold} stop{int(stop*100)} | " + " | ".join(out))
