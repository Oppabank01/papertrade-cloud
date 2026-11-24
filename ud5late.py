#!/usr/bin/env python3
"""Polymarket BTC 5-minute Up/Down: buy the favourite in the last minute (opened 24 Nov 2026). Fake money only, public read-only APIs.

Runs on the Mac (python3 ud5late.py loop), not in the 5-minute cloud job, which can only act about 2 min into each window.
Rule: 240-285 s into each 5-minute window, buy the outcome whose best ask is 0.50-0.90 (the higher one if both are), 5% of
the start per trade, taker fee 0.05*p*(1-p) per share (the market's feeSchedule), hold to the result.
Why: the user sent an X post (@Mikocrypto11, 23 Nov 2026) about a bot buying the 20-35c side of these markets for +$103K.
I pulled every taker trade of 600 markets (about 2 days, 1.3M trades) to check it: one buy per market at 0.20-0.35 loses
6% to 23% after the fee in every part of the window (later is worse). The other side looked better only in the last minute:
first taker buy at 0.50-0.65 at 240-290 s: n 97, +15% (t 2.0); 0.80-0.90: n 188, +4.4% (t 1.6). That is the best of about
30 band/time combinations I tried, so it is probably partly luck; this forward test is the check.
  state_ud5late.json        the rule
  state_ud5late_twin.json   control: a random outcome of the same market at the same moment, same size and fee
  python3 ud5late.py loop | once | status"""
import json, os, random, sys, time
from pathlib import Path

import polymarket as P
import poly_fav as F

DIR = Path(os.environ.get("UD5_DIR", Path(__file__).parent.parent / "PaperTrade"))
RULE, TWIN = str(DIR / "state_ud5late.json"), str(DIR / "state_ud5late_twin.json")
LABELS = {RULE: "Polymarket BTC 5 นาที: นาทีสุดท้าย (240-285 วิ) ซื้อฝั่งที่ ask 0.50-0.90 ถือจนรู้ผล (ไอเดียจากโพสต์ X บอทซื้อ 20-35 เซนต์ ซึ่งทดสอบแล้วขาดทุน)",
          TWIN: "Polymarket BTC 5 นาที ตัวควบคุม: สุ่มฝั่งในตลาดเดียวกัน เวลาเดียวกัน"}
LO, HI, T0, T1, RATE, SIZE = 0.50, 0.90, 240, 285, 0.05, 0.05
START = 500 / 33.9                                   # same 500 THB start as the other paper accounts


def load(f):
    try:
        return json.load(open(f))
    except (OSError, ValueError):
        return dict(label=LABELS[f], start_thb=500, start_usd=START, cash=START, pos={}, log=[], done=[])


def save(f, s):
    json.dump(s, open(f + ".tmp", "w"), ensure_ascii=False, indent=1)
    os.replace(f + ".tmp", f)


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S+07:00", time.localtime(t))


def buy(s, ts, oi, name, px, why):
    usd = min(s["start_usd"] * SIZE, s["cash"])
    if usd <= 0.01:
        return
    fee = RATE * px * (1 - px)                       # per share
    qty = usd / (px + fee)
    s["cash"] -= usd
    s["pos"][str(ts)] = dict(side="long", d=1, oi=oi, coin=name, qty=qty, entry=px, last=px, usd=usd, t=iso(time.time()), why=why)
    s["log"].append(dict(kind="buy", t=iso(time.time()), coin=name, side="long", px=px, usd=usd, fee_usd=round(qty * fee, 5), why=why))
    s["done"] = (s.get("done", []) + [ts])[-50:]


def settle(s, now):
    for k, p in list(s["pos"].items()):
        ts = int(k)
        if now < ts + 360:
            continue
        try:
            m = P.get(f"{P.GAMMA}/markets", dict(slug=f"btc-updown-5m-{ts}", closed="true"))
        except Exception:
            continue
        pr = json.loads(m[0].get("outcomePrices") or "[]") if m else []
        if pr not in (["1", "0"], ["0", "1"]):
            continue
        pay = float(pr[p["oi"]])
        s["pos"].pop(k)
        s["cash"] += p["qty"] * pay
        s["log"].append(dict(kind="sell", t=iso(now), coin=p["coin"], side="long", px=pay, usd=p["usd"], ret=round(p["qty"] * pay / p["usd"] - 1, 6),
                             pnl=p["qty"] * pay - p["usd"], cost_side=0, why="ตัดสินผลแล้ว"))


def step(sr, st, now, rng):
    ts = int(now - now % 300)
    if not T0 <= now - ts <= T1 or ts in sr.get("done", []):
        return
    m = P.get(f"{P.GAMMA}/markets", dict(slug=f"btc-updown-5m-{ts}"))
    if not m or not (m[0].get("acceptingOrders") and m[0].get("enableOrderBook")):
        return
    m = m[0]
    tk = F.tokens(m)
    bk = P.books(tk)
    asks = [P.levels(bk.get(t), "asks") for t in tk]
    a = [x[0][0] if x else None for x in asks]
    ok = [i for i in (0, 1) if a[i] is not None and LO <= a[i] <= HI]
    names = ["Up", "Down"]
    sr.setdefault("done", []).append(ts)
    if not ok:
        sr["done"] = sr["done"][-50:]
        return
    oi = max(ok, key=lambda i: a[i])
    sec = int(now - ts)
    buy(sr, ts, oi, f"{names[oi]} | {m['question']}", a[oi], f"วินาทีที่ {sec} ask {a[oi]:.3f}")
    j = rng.randrange(2)
    if a[j] is not None and 0.02 <= a[j] <= 0.98:
        buy(st, ts, j, f"{names[j]} | {m['question']}", a[j], f"สุ่มฝั่ง วินาทีที่ {sec} ask {a[j]:.3f}")


def once(rng):
    now = time.time()
    sr, st = load(RULE), load(TWIN)
    try:
        step(sr, st, now, rng)
    except Exception as e:
        print(iso(now), "step", type(e).__name__, flush=True)
    for s in (sr, st):
        settle(s, now)
    save(RULE, sr)
    save(TWIN, st)


def main(cmd):
    rng = random.Random()
    if cmd == "status":
        for f in (RULE, TWIN):
            s = load(f)
            sells = [x for x in s["log"] if x["kind"] == "sell"]
            v = s["cash"] + sum(p["usd"] for p in s["pos"].values())
            print(f"{Path(f).stem:<18} {v / s['start_usd'] - 1:+.1%} sold {len(sells)} won {sum(x['px'] > 0.5 for x in sells)} open {len(s['pos'])}")
    elif cmd == "once":
        once(rng)
    else:
        while True:
            once(rng)
            time.sleep(10)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "loop")
