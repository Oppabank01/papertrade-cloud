# R6 vs control: same symbols, random entry minute in random windows from the 30 days before the announcement, same exits/costs/funding.
import pickle, numpy as np, math, sys
import r6_delist as R
C = pickle.load(open(R.PFX + "_ctl.pkl", "rb"))
SEEDS = 300
rng = np.random.default_rng(3)
print("\n== control (same symbols, random time in prior 30 days), %d seeds ==" % SEEDS)
for lag, hold, stop in ((5, 240, 0.30), (15, 240, 0.30), (15, 600, 0.30), (30, 240, 0.30), (15, 240, 0.15)):
    tr = R.run("both", lag, hold, stop, 0.003, show=False); r = np.array([x[1] for x in tr]); s = np.sort(r)
    means = []; meds = []; ex5 = []; wrs = []
    for k in range(SEEDS):
        rr = []
        for (ta, sym), v in R.EV.items():
            ws = C.get((ta, sym)) or []
            if not ws: continue
            w = ws[int(rng.integers(len(ws)))]
            if len(w) < hold + 20: continue
            a = np.array(w, dtype=float); i = int(rng.integers(0, len(a) - hold - 5))
            x = R.trade(dict(a=a, ft=v["ft"], fr=v["fr"]), a[i, 0], 0, hold, stop, 0.003)
            if x: rr.append(x[0])
        rr = np.array(rr); means.append(rr.mean()); meds.append(np.median(rr)); ex5.append(np.sort(rr)[:-5].mean()); wrs.append((rr > 0).mean())
    means = np.array(means)
    print(f"lag{lag} hold{hold} stop{int(stop*100)}: RULE n={len(r)} mean={r.mean()*100:+.2f} med={np.median(r)*100:+.2f} wr={(r>0).mean()*100:.0f} ex5={s[:-5].mean()*100:+.2f} | CONTROL n~{len(rr)} mean={means.mean()*100:+.2f} (sd {means.std()*100:.2f}, max {means.max()*100:+.2f}) med={np.mean(meds)*100:+.2f} wr={np.mean(wrs)*100:.0f} ex5={np.mean(ex5)*100:+.2f} | seeds with control>=rule: {(means>=r.mean()).sum()}/{SEEDS}; rule ex5 vs best control mean: {s[:-5].mean()*100:+.2f} vs {means.max()*100:+.2f}")
# stop-outs
tr = R.run("both", 15, 240, 0.30, 0.003, show=False); r = np.array([x[1] for x in tr])
print("stop-outs at lag15/240/30%:", int((r < -0.28).sum()), "of", len(r), "| mean if every stop-out filled at -45% instead:", round((np.where(r < -0.28, -0.45, r)).mean() * 100, 2))
