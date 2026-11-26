#!/usr/bin/env python3
"""Cut the cached Binance USDT-M 1h klines (scripts_fable_26nov fetchers, Jul 2025 - Nov 2026, delisted symbols kept)
down to a small file: every memecoin perp + a fixed random sample of 150 non-meme alts for controls + BTC/ETH/SOL.
  python3 perp_extract.py <hunt_dir> <out.pkl> [old]"""
import pickle, sys, random, numpy as np
H, OUT = sys.argv[1], sys.argv[2]
OLD = len(sys.argv) > 3 and sys.argv[3] == "old"   # Jan-Jun 2025 out-of-sample files (old_k_*.pkl, old_f.pkl)
MEME = """1000000BOB 1000000MOG 1000BONK 1000CAT 1000CHEEMS 1000FLOKI 1000PEPE 1000RATS 1000SATS 1000SHIB 1000WHY 1000X 1MBABYDOGE
ACT AI16Z AVAAI BAN BANANAS31 BOME BRETT BROCCOLI714 BROCCOLIF3B CHILLGUY DEGEN DOGE DOGS FARTCOIN GIGGLE GOAT GRIFFAIN HIPPO JELLYJELLY
KOMA MELANIA MEME MEMEFI MEW MOODENG MUBARAK MYRO NEIRO NEIROETH PENGU PEOPLE PIPPIN PNUT PONKE POPCAT SIREN SLERF SPX SWARMS TOSHI TRUMP
TST TURBO TUT USELESS VINE WIF ZEREBRO ARC 哈基米 币安人生 我踏马来了 牛来 龙虾 DOOD HOUSE TROLL""".split()
syms = pickle.load(open(f"{H}/bn_syms.pkl", "rb")); meta = {s: (ob, st) for s, ob, st in syms}
F = pickle.load(open(f"{H}/{'old_f' if OLD else 'bn_f'}.pkl", "rb"))
memes = {m + "USDT" for m in MEME}; maj = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
others = sorted(s for s in meta if s not in memes and s not in maj and s not in ("BTCDOMUSDT", "USDCUSDT", "PAXGUSDT", "XAUTUSDT", "DEFIUSDT"))
random.Random(27).shuffle(others); ctl = set(others[:150])
out = {}
for fn in (("old_k_0.pkl", "old_k_1.pkl") if OLD else ("bn_k2_0.pkl", "bn_k2_1.pkl")):
    K = pickle.load(open(f"{H}/{fn}", "rb"))
    for s, (t, a) in K.items():
        if s in memes or s in maj or s in ctl:
            f = F.get(s) or []
            out[s] = dict(t=t, a=a, ft=np.array([x[0] for x in f], dtype=np.int64), fr=np.array([x[1] for x in f], dtype=np.float64),
                          ob=meta[s][0], st=meta[s][1], kind="meme" if s in memes else "maj" if s in maj else "alt")
    del K
pickle.dump(out, open(OUT, "wb"))
import collections; print(collections.Counter(v["kind"] for v in out.values()))
print("memes found:", sorted(s[:-4] for s, v in out.items() if v["kind"] == "meme"))
print("delisted memes:", sorted(s[:-4] for s, v in out.items() if v["kind"] == "meme" and v["st"] != "TRADING"))
