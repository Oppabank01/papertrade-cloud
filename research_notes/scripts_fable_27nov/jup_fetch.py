#!/usr/bin/env python3
"""5-min OHLCV from Jupiter's public chart API (datapi.jup.ag, no key, one call per mint, works for dead coins too)
for every data/rank_hist mint whose liquidity ever reached MIN_LIQ. GeckoTerminal was rate-limited to ~1 call/2 min
on this IP on 26 Nov, so it is not used. Output: <out>/<mint>.npy float64 [t, o, h, l, c, v] rows. Resumable.
  python3 jup_fetch.py <rh.pkl> <out_dir> [min_liq=30000] [max_minutes=40]"""
import json, sys, time, pickle, urllib.request, urllib.error
from pathlib import Path
import numpy as np
rows = pickle.load(open(sys.argv[1], "rb")); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
MIN_LIQ = float(sys.argv[3]) if len(sys.argv) > 3 else 30000
DEADLINE = time.time() + 60 * (float(sys.argv[4]) if len(sys.argv) > 4 else 40)
best = {}
for r in rows:
    if r[4] >= MIN_LIQ: best[r[1]] = max(best.get(r[1], 0), r[4])
mints = sorted(best, key=lambda m: -best[m]); todo = [m for m in mints if not (OUT / f"{m}.npy").exists()]
print(len(mints), "mints,", len(todo), "to fetch", flush=True)
TO = int(time.time()) * 1000; ok = fail = 0
for m in todo:
    if time.time() > DEADLINE: print("deadline", flush=True); break
    c = None
    for i in range(4):
        try:
            u = f"https://datapi.jup.ag/v2/charts/{m}?interval=5_MINUTE&to={TO}&candles=4400&type=price&quote=usd"
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
                c = json.load(r).get("candles") or []; break
        except urllib.error.HTTPError as e:
            time.sleep(30 if e.code == 429 else 4)
        except Exception:
            time.sleep(4)
    if c is None: fail += 1; continue
    a = np.array([[x["time"], x["open"], x["high"], x["low"], x["close"], x.get("volume") or 0] for x in c], dtype=np.float64).reshape(-1, 6)
    np.save(OUT / f"{m}.npy", a); ok += 1
    if ok % 50 == 0: print("ok", ok, "fail", fail, flush=True)
    time.sleep(0.9)
print("done ok", ok, "fail", fail, flush=True)
