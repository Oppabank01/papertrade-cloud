#!/usr/bin/env python3
"""Hyperliquid (public info API, reachable from US runners): 1h candles (max 5000 = 208 days) and hourly funding for every
memecoin perp, live and delisted. Output hl.pkl in the perplib format.  python3 hl_fetch.py <out.pkl>"""
import json, sys, time, pickle, urllib.request
import numpy as np
MEME = """DOGE kPEPE kSHIB kBONK kFLOKI kNEIRO WIF POPCAT FARTCOIN PNUT MOODENG GOAT BOME BRETT MEME TURBO SPX PENGU TRUMP MELANIA GRIFFAIN
USELESS PEOPLE CASHCAT PURR PUMP HMSTR MYRO MEW kDOGS NEIROETH CHILLGUY AI16Z ZEREBRO VINE JELLY TST DOOD LAUNCHCOIN YZY HPOS""".split()
def post(body):
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request("https://api.hyperliquid.xyz/info", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}), timeout=25) as r:
                return json.load(r)
        except Exception as e:
            time.sleep(15 if "429" in str(e) else 4)
    return None
now = int(time.time() * 1000); out = {}
for c in MEME + ["BTC"]:
    k = post({"type": "candleSnapshot", "req": {"coin": c, "interval": "1h", "startTime": now - 5000 * 3600000, "endTime": now}}) or []
    time.sleep(1.5)
    if len(k) < 200: print("skip", c, len(k), flush=True); continue
    t = np.array([x["t"] for x in k], dtype=np.int64)
    a = np.array([[float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"]), float(x["v"]) * float(x["c"])] for x in k], dtype=np.float32)
    f = []; st = int(t[0])
    while st < now:
        d = post({"type": "fundingHistory", "coin": c, "startTime": st}); time.sleep(2.4)
        if not d: break
        f += [(x["time"], float(x["fundingRate"])) for x in d]
        if len(d) < 500: break
        st = d[-1]["time"] + 1
    out[c + "USDT"] = dict(t=t, a=a, ft=np.array([x[0] for x in f], dtype=np.int64), fr=np.array([x[1] for x in f], dtype=np.float64), ob=int(t[0]), st="TRADING",
                           kind="maj" if c == "BTC" else "meme")
    pickle.dump(out, open(sys.argv[1], "wb")); print(c, len(t), len(f), flush=True)
print("done", len(out))
