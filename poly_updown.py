#!/usr/bin/env python3
"""Polymarket crypto "Up or Down" markets priced with a simple model from Binance 1-minute prices (opened 23 Nov 2026).
Fake money only: public read-only APIs, no login, no keys, no wallet, no orders anywhere.

Resolution: Up when the Chainlink BTC/USD 60 s TWAP stream at the end of the title's range is >= its value at the start
(Gamma description says "TWAP of the time range", but live prices on 23 Nov 2026 11:29 matched end-vs-start, not the average
over the range: ETH 4 h market was 0.92 Up with the last price above the start and the range average below it). Model, a
random walk with no drift: P(up) = Phi(ln(S / S0) / (vol * sqrt(tau))), S0 = Binance 1m open at the range start, S = last
trade, tau = minutes left, vol = stdev of 1m log returns over the last 360 minutes. Binance USDT pairs stand in for
Chainlink USD (a few dollars apart, which matters near 50/50).
  state_poly_updown.json       buys the side whose model probability beats its fill cost per share by EDGE or more
  state_poly_updown_twin.json  control: a random side of the same market at the same moment
Held to resolution (poly_fav.settle_and_mark), 5% of the start per buy, one buy per market. Numbers chosen by me: EDGE 0.06,
markets of 4 h or shorter, at least 2 min left and 20% of the range gone, MAX_NEW 3 per run, vol window 360 min.
  python3 poly_updown.py run | status | show   (show = model vs market for live markets, no buys)"""
import json, math, random, sys, time, urllib.request
from pathlib import Path

import polymarket as P
import poly_fav as F
from poly_arb import books

HERE = Path(__file__).parent
RULE, TWIN = (str(HERE / f"state_poly_{n}.json") for n in ("updown", "updown_twin"))
LABELS = {RULE: "Polymarket Up or Down คริปโต: คิดความน่าจะเป็นจากราคา Binance (ราคาจบเทียบราคาเริ่ม) ซื้อฝั่งที่ถูกกว่าโมเดล 6 เซนต์ขึ้นไป",
          TWIN: "Polymarket Up or Down ตัวควบคุม: สุ่มฝั่งในตลาดเดียวกัน เวลาเดียวกัน"}
COINS = {"Bitcoin": "BTCUSDT", "Ethereum": "ETHUSDT", "Solana": "SOLUSDT", "XRP": "XRPUSDT"}
EDGE, MAX_RANGE_S, MIN_LEFT_S, MIN_GONE, MAX_NEW, VOL_N = 0.06, 4 * 3600, 120, 0.2, 3, 360
KL = "https://data-api.binance.vision/api/v3/klines?symbol={}&interval=1m&limit=600"


def klines(sym):
    raw = json.loads(urllib.request.urlopen(urllib.request.Request(KL.format(sym), headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())
    return [(k[0] // 1000, float(k[1]), float(k[4]), k[6] / 1000) for k in raw]   # open time s, open, close, close time s


def model_up(k, start, end, now):
    """P(Up) from 1m bars k, or None if the range start is not inside the data."""
    first = [x for x in k if x[0] == start]
    closed = [x for x in k if x[3] < now]
    if not first or len(closed) < VOL_N + 1:
        return None
    s0, S, tau = first[0][1], k[-1][2], (end - now) / 60
    r = [math.log(b[2] / a[2]) for a, b in zip(closed[-VOL_N - 1:], closed[-VOL_N:])]
    m = sum(r) / len(r)
    sd = (sum((x - m) ** 2 for x in r) / (len(r) - 1)) ** 0.5 * math.sqrt(tau)
    z = math.log(S / s0) / sd if sd > 0 else (9 if S >= s0 else -9)
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def live_markets(now):
    rows = []
    for o in (0, 100, 200, 300):
        rows += P.get(f"{P.GAMMA}/markets", dict(closed="false", limit=100, offset=o, order="volume24hr", ascending="false",
                                                  end_date_min=F.iso(now + MIN_LEFT_S), end_date_max=F.iso(now + MAX_RANGE_S)))
    out = []
    for m in rows:
        q = m.get("question") or ""
        coin = next((c for c in COINS if q.startswith(c + " Up or Down")), None)
        start, end, tk = F.utc_ts(m.get("eventStartTime")), P.ts_of(m.get("endDate")), F.tokens(m)
        if not coin or not start or not end or not tk or not (m.get("enableOrderBook") and m.get("acceptingOrders")):
            continue
        if json.loads(m.get("outcomes") or "[]") != ["Up", "Down"] or end - start > MAX_RANGE_S or m.get("umaResolutionStatus"):
            continue
        if now - start < MIN_GONE * (end - start) or end - now < MIN_LEFT_S:
            continue
        out.append((m, COINS[coin], start, end, tk))
    return out


def cmd_run(show=False):
    now, rng = time.time(), random.Random()
    sr, st = F.load(RULE), F.load(TWIN)
    for f, s in ((RULE, sr), (TWIN, st)):
        s["label"] = LABELS.get(f, s.get("label"))
    usd = sr["start_usd"] * P.SIZE
    try:
        mk = live_markets(now)
        kl = {sym: klines(sym) for sym in {x[1] for x in mk}}
        bk = books([t for x in mk for t in x[4]], 500) if mk else {}
    except Exception as e:
        print(f"updown fetch: {type(e).__name__}: no buys this run")
        mk, bk = [], None
    cand = []
    for m, sym, start, end, tk in mk:
        p = model_up(kl[sym], int(start), int(end), now)
        if p is None:
            continue
        best = None
        for oi, pm in ((0, p), (1, 1 - p)):
            asks = P.levels(bk.get(tk[oi]), "asks")
            fill = P.fill_buy(asks, usd, P.fee_info(m)) if asks else None
            if not fill:
                continue
            cost = usd / fill[0]                    # dollars per share including the taker fee (slip added below)
            edge = pm - cost * (1 + P.SLIP)
            if show:
                print(f"  {m['question'][:58]:<58} {['Up', 'Down'][oi]:<4} model {pm:.3f} ask {asks[0][0]:.3f} cost {cost:.3f} edge {edge:+.3f} left {(end - now) / 60:.0f}m")
            if best is None or edge > best[0]:
                best = (edge, oi, pm, cost)
        if best and best[0] >= EDGE:
            cand.append((best[0], m, tk, best[1], best[2], best[3], end))
    if show:
        return
    n = 0
    for edge, m, tk, oi, pm, cost, end in sorted(cand, key=lambda x: -x[0]):
        c = m["conditionId"].lower()
        if c in sr["done"] or n >= MAX_NEW:
            continue
        why = P.buy(sr, tk[oi], m, oi, bk.get(tk[oi]), f"โมเดล {pm:.3f} ทุนต่อหุ้น {cost:.3f} ได้เปรียบ {edge:+.3f} เหลือ {(end - now) / 60:.0f} นาที",
                    model=round(pm, 4), edge=round(edge, 4))
        if why is None:
            n += 1
            sr["done"][c] = int(now)
            print(f"  BUY {sr['pos'][tk[oi]]['coin'][:70]} model {pm:.3f} cost {cost:.3f}")
            if c not in st["done"]:
                j = rng.randrange(2)
                if P.buy(st, tk[j], m, j, bk.get(tk[j]), "สุ่มฝั่ง คู่กับบัญชีโมเดล") is None:
                    st["done"][c] = int(now)
    for s in (sr, st):
        s["done"] = {k: v for k, v in s["done"].items() if v > now - 3 * 86400}
        F.settle_and_mark(s, bk)
    for f, s in ((RULE, sr), (TWIN, st)):
        P.save(f, s)
    print(f"poly updown: {len(mk)} live, {len(cand)} with edge >= {EDGE} | " +
          " | ".join(f"{k} {P.value(s) / s['start_usd'] - 1:+.1%} open {len(s['pos'])}" for k, s in (("rule", sr), ("twin", st))))


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "run"
    if a == "status":
        for f in (RULE, TWIN):
            s = F.load(f)
            print(f"{Path(f).stem:<22} {P.value(s) / s['start_usd'] - 1:+.1%} open {len(s['pos'])}")
    else:
        cmd_run(show=(a == "show"))
