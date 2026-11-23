#!/usr/bin/env python3
"""Kalshi favourite-longshot check (opened 23 Nov 2026), the same idea as poly_fav.py on a second venue, so a Polymarket-only
fluke shows up. Fake money only: Kalshi's public read-only market API, no login, no keys, no orders.

  state_kalshi_fav.json   buys the side (yes or no) whose ask is 0.85-0.97 in markets closing within 48 h
  state_kalshi_long.json  control: the side whose ask is 0.03-0.10 in the same scan (expected to lose)
  state_kalshi_twin.json  a random side of each market the two above buy, same moment and size
5% of the 500 THB start per buy at the ask plus Kalshi's taker fee 0.07 x P x (1-P) per contract (real fees round up to the
cent per order; ignored) plus 0.5% slip. Held to settlement (result yes/no pays 1 or 0), marked to the side's bid meanwhile.
Skipped: no bid, spread above 3 cents, ask size worth less than 5x our order, multivariate combos. One buy per event per
account, at most 2 per account per run, soonest close first. Kalshi gives no game start time, so sports markets may be bought
in play (unlike poly_fav). Numbers chosen by me, copied from poly_fav where they exist.
shortcut: "scalar" results are not settled (the position stays marked to its last bid); handle them if one is ever bought.
  python3 kalshi_fav.py run | status"""
import json, random, sys, time, urllib.parse, urllib.request
from pathlib import Path
from byttrade import iso, load, save

HERE = Path(__file__).parent
API = "https://api.elections.kalshi.com/trade-api/v2"
FAV, LONG, TWIN = (str(HERE / f"state_kalshi_{n}.json") for n in ("fav", "long", "twin"))
LABELS = {FAV: "Kalshi ซื้อตัวเต็ง 0.85-0.97 ตลาดปิดใน 48 ชม. ไม้ละ 5% ถือจนตัดสิน (เทียบกับ Polymarket)",
          LONG: "Kalshi ตัวควบคุม: ซื้อตัวรอง 0.03-0.10 ตลาดแบบเดียวกัน",
          TWIN: "Kalshi ตัวควบคุม: สุ่มฝั่งในตลาดเดียวกับตัวเต็ง/ตัวรอง"}
BANDS = {"fav": (0.85, 0.97), "long": (0.03, 0.10)}
SIZE, SLIP, FEE, MAX_H, MAX_SPREAD, DEPTH_X, MAX_NEW, PAGES = 0.05, 0.005, 0.07, 48, 0.03, 5, 2, 6


def get(path, **q):
    u = f"{API}{path}?{urllib.parse.urlencode(q)}" if q else f"{API}{path}"
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())


def scan(now):
    out, cur = [], None
    for _ in range(PAGES):
        q = dict(status="open", limit=1000, max_close_ts=int(now + MAX_H * 3600), min_close_ts=int(now + 300), mve_filter="exclude")
        if cur:
            q["cursor"] = cur
        d = get("/markets", **q)
        out += [m for m in d["markets"] if not m.get("mve_collection_ticker")]
        cur = d.get("cursor")
        if not cur:
            break
    return out


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def quote(m, side, usd, lo, hi):
    a, b, sz = num(m.get(f"{side}_ask_dollars")), num(m.get(f"{side}_bid_dollars")), num(m.get(f"{side}_ask_size_fp"))
    if not lo <= a <= hi:
        return None
    if b <= 0 or a - b > MAX_SPREAD + 1e-9 or sz * a < DEPTH_X * usd:
        return "thin"
    return a + FEE * a * (1 - a) + a * SLIP     # dollars per contract


def buy(s, m, side, cost, why):
    usd = s["start_usd"] * SIZE
    k = f"{m['ticker']}:{side}"
    if k in s["pos"] or s["cash"] < usd:
        return False
    qty = usd / cost
    s["cash"] -= usd
    bid = num(m.get(f"{side}_bid_dollars"))
    s["pos"][k] = dict(qty=qty, entry=cost, last=bid, usd=usd, t=iso(time.time() * 1000), coin=f"{side.upper()} | {m.get('title', '')}"[:90],
                       ticker=m["ticker"], side=side, close=m.get("close_time"), why=why)
    s["log"].append(dict(kind="buy", t=iso(time.time() * 1000), coin=s["pos"][k]["coin"], px=round(cost, 5), usd=usd, why=why,
                         ask=num(m.get(f"{side}_ask_dollars"))))
    return True


def settle_and_mark(s):
    for k, p in list(s["pos"].items()):
        try:
            m = get(f"/markets/{p['ticker']}")["market"]
        except Exception as e:
            print(f"kalshi mark {p['ticker']}: {type(e).__name__}")
            continue
        if m.get("result") in ("yes", "no") and m.get("status") in ("settled", "finalized", "determined"):
            pay = 1.0 if m["result"] == p["side"] else 0.0
            net = p["qty"] * pay
            s["pos"].pop(k)
            s["cash"] += net
            s["log"].append(dict(kind="sell", t=iso(time.time() * 1000), coin=p["coin"], px=pay, entry=round(p["entry"], 5), usd=round(net, 5),
                                 pnl=round(net - p["usd"], 5), ret=round(pay / p["entry"] - 1, 5), cost_side=0, why=f"ตัดสิน {m['result']}"))
            print(f"  SETTLED {p['coin'][:60]} -> {pay:g}")
        else:
            b = num(m.get(f"{p['side']}_bid_dollars"))
            if b > 0:
                p["last"] = b


def ld(f):
    s = load(f, LABELS[f])
    s.setdefault("done", {})
    return s


def run():
    now, rng = time.time(), random.Random()
    accts = {"fav": ld(FAV), "long": ld(LONG)}
    tw = ld(TWIN)
    usd = accts["fav"]["start_usd"] * SIZE
    try:
        ms = sorted(scan(now), key=lambda m: m.get("close_time") or "")
    except Exception as e:
        print(f"kalshi scan: {type(e).__name__}: no buys this run")
        ms = []
    bought = {}
    for name, s in accts.items():
        n = 0
        for m in ms:
            ev = m.get("event_ticker") or m["ticker"]
            if n >= MAX_NEW or ev in s["done"]:
                continue
            for side in ("yes", "no"):
                c = quote(m, side, usd, *BANDS[name])
                if isinstance(c, float) and buy(s, m, side, c, f"{name} ask {num(m.get(side + '_ask_dollars')):.2f} ทุน {c:.3f} ปิด {m.get('close_time')}"):
                    s["done"][ev] = int(now); n += 1; bought[m["ticker"]] = m
                    print(f"  {name.upper()} {side} {m.get('title', '')[:60]} @ {c:.3f}")
                    break
    for t, m in bought.items():
        ev = m.get("event_ticker") or t
        if ev in tw["done"]:
            continue
        side = rng.choice(("yes", "no"))
        a = num(m.get(f"{side}_ask_dollars"))
        if 0.01 < a < 0.99 and buy(tw, m, side, a + FEE * a * (1 - a) + a * SLIP, "สุ่มฝั่ง"):
            tw["done"][ev] = int(now)
    for f, s in ((FAV, accts["fav"]), (LONG, accts["long"]), (TWIN, tw)):
        s["done"] = {k: v for k, v in s["done"].items() if v > now - 10 * 86400}
        settle_and_mark(s)
        save(f, s)
    v = lambda s: (s["cash"] + sum(p["qty"] * p["last"] for p in s["pos"].values())) / s["start_usd"] - 1
    print(f"kalshi fav: {len(ms)} markets | " + " | ".join(f"{k} {v(s):+.1%} open {len(s['pos'])}" for k, s in (("fav", accts["fav"]), ("long", accts["long"]), ("twin", tw))))


if __name__ == "__main__":
    if (sys.argv[1] if len(sys.argv) > 1 else "run") == "status":
        for f in (FAV, LONG, TWIN):
            s = ld(f)
            print(Path(f).stem, f"{(s['cash'] + sum(p['qty'] * p['last'] for p in s['pos'].values())) / s['start_usd'] - 1:+.1%}", len(s["pos"]))
    else:
        run()
