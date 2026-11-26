# Binance USDT-M perp event rules on 1h bars vs random controls. usage: python3 cex_bt.py [seeds]
from cexlib import *
nset = 0
print("\n== R1 funding extremes (entry at open of first bar after settlement) ==")
for thr in (-0.003, -0.005, -0.01):
    for hold in (8, 24, 72):
        ev = {s: [bar_after(D[s], ft) for ft, fr in zip(D[s]["ft"], D[s]["fr"]) if fr <= thr] for s in SY}
        ev = {s: v for s, v in ev.items() if v}
        evaluate(f"R1 long  fund<={thr*100:.1f}% h{hold} sl15", ev, +1, hold, 0.15); nset += 1
        evaluate(f"R1s short fund<={thr*100:.1f}% h{hold} sl15", ev, -1, hold, 0.15); nset += 1
for thr in (0.001, 0.002, 0.004):
    for hold in (24, 72):
        ev = {s: [bar_after(D[s], ft) for ft, fr in zip(D[s]["ft"], D[s]["fr"]) if fr >= thr] for s in SY}
        ev = {s: v for s, v in ev.items() if v}
        evaluate(f"R1p short fund>=+{thr*100:.1f}% h{hold} sl15", ev, -1, hold, 0.15); nset += 1
print("\n== R2 pump fade: 24h return >= X at an hourly close, short next open ==")
for thr in (0.3, 0.5, 1.0):
    for hold in (8, 24, 72):
        ev = {}
        for s in SY:
            c = D[s]["c"]
            if len(c) < 60: continue
            r24 = c[24:] / c[:-24] - 1; idx = np.nonzero(r24 >= thr)[0] + 24 + 1
            idx = idx[idx >= 48]          # skip first 2 days after listing (covered by R3)
            if len(idx): ev[s] = idx.tolist()
        evaluate(f"R2 short r24>=+{thr*100:.0f}% h{hold} sl25", ev, -1, hold, 0.25); nset += 1
print("\n== R3 new perp listing short (listed since Jul 2025) ==")
for eh in (1, 24):
    for hold in (72, 168, 336):
        ev = {s: [eh] for s in SY if D[s]["ob"] >= 1751328000000 and abs(D[s]["t"][0] - D[s]["ob"]) < 6 * H}
        evaluate(f"R3 short list+{eh}h h{hold} sl40", ev, -1, hold, 0.40); nset += 1
print("\n== R4 wick bounce long / R5 1h pump fade short (vol >= 5x 24h avg) ==")
for side, nm, thrs, stop in ((+1, "R4 long 1h<=-", (0.08, 0.12, 0.20), 0.10), (-1, "R5 short 1h>=+", (0.08, 0.12, 0.20), 0.15)):
    for thr in thrs:
        for hold in (1, 4, 24):
            ev = {}
            for s in SY:
                d = D[s]; c = d["c"]; o = d["o"]; q = d["q"]
                if len(c) < 80: continue
                r1 = c / o - 1
                cs = np.cumsum(q); av = np.zeros(len(q)); av[24:] = (cs[23:-1] - np.concatenate(([0], cs[:-25]))) / 24
                m = ((r1 <= -thr) if side > 0 else (r1 >= thr)) & (q >= 5 * av) & (av > 0)
                idx = np.nonzero(m)[0] + 1; idx = idx[idx >= 48]
                if len(idx): ev[s] = idx.tolist()
            evaluate(f"{nm}{thr*100:.0f}% h{hold} sl{int(stop*100)}", ev, side, hold, stop); nset += 1
print("\nsettings tried:", nset)
