#!/usr/bin/env python3
"""Polymarket favourite-longshot bias (opened 23 Nov 2026). Fake money only: public read-only APIs, no login, no keys,
no wallet, no orders anywhere.

Idea: heavy favourites (priced about 0.85-0.97 shortly before the end) win more often than their price says, longshots
(under 0.10) less often. `calib` measures it on resolved markets first; the three accounts test it forward.

  state_poly_fav.json       buys the outcome whose best ask is FAV_LO-FAV_HI (and whose average fill walking the real asks
                            stays in that range) in markets whose endDate is within MAX_H hours, 5% of the 500 THB start per
                            buy (polymarket.SIZE), held to resolution, marked to the best bid meanwhile.
  state_poly_long.json      the opposite: outcomes with best ask LONG_LO-LONG_HI in the same scan (expected to lose: the control
                            for the bias).
  state_poly_fav_twin.json  for every market fav or long buys, at the same moment, the same size on a random outcome of it.
  data/poly_fav_log.jsonl   every outcome seen in either price range (bought or why not), last LOG_KEEP lines.
  data/poly_fav_calib.json  rows of the last `calib` run (price 1/6/24 h before the end vs the payout).

Skipped: endDate or gameStartTime passed or less than MIN_LEAD_S away (no in-play buys), not accepting
orders, Gamma umaResolutionStatus set (an answer proposed), a /v2/resolutions row that is not "posed" or was disputed, thin
books (no bid, spread above MAX_SPREAD, or asks within DEPTH_BAND of the best ask worth less than DEPTH_X times our size).
One buy per market and per event per account (a negRisk event's NO legs move together), at most MAX_NEW buys per account
per run, soonest end first. A failed fetch means no buys that run. Cost = walking the asks + the market's taker fee
(shares x rate x p(1-p), Gamma feeSchedule) + SLIP 0.5%; resolution pays 1 or 0 with no fee.
Note: $0.74 per buy is below the CLOB's 5-share minimum for a favourite (5 x 0.9 = $4.5); kept small so 20 buys fit in
the start, the fill math is the same per dollar.

History check (`calib 30`, run 23 Nov 2026 02:37 Bangkok, seed 23; 5,948 resolved markets, 91% sports, price = CLOB
prices-history 6 h before endDate or game start, both outcomes of each market):
  0.85-0.97  n 1,670 outcomes, 460 events, price 0.920, won 0.947 (+2.8 points, z 4.2, event-clustered z 4.7),
             return per $ after taker fee and slip at that price +2.2% (the spread to the ask is not in it)
  0.03-0.10  n 1,179 outcomes, 381 events, price 0.061, won 0.042 (-2.0 points, clustered z -3.4), -36% per $
  1 h and 24 h before give the same signs (fav +3.0 / +3.0 points, long -2.1 / -2.2).
  Not trusted as an edge: the middle buckets are off by more (0.35-0.50 priced 0.446 won 0.332), too big for liquid books,
  and the first run (top 300 by total volume per day, data/poly_fav_calib_byvolume.json, endDate as the reference) gave
  the opposite sign (0.85-0.97 at 6 h: n 551, price 0.913, won 0.826) because total volume includes in-play trading,
  which is larger after an upset. The forward accounts decide.

Dead / pass (AGENT_RULES, written before any result): fav dead at 20 resolved buys if its average return per buy is not
above the twin's; pass at 50 resolved buys, positive after costs, above the twin and still positive with its best buy
removed. long is a control: it should lose more per buy than the twin; if it does not, the bias is not there.

Endpoints (public, checked 23 Nov 2026; see polymarket.py / poly_arb.py docstrings for the docs links):
  Gamma GET /markets?closed=false&end_date_min&end_date_max&order=volume24hr&limit=100&offset   (scan)
  Gamma GET /markets?closed=true&...&order=volumeNum                                            (calib)
  CLOB  POST /books (500 tokens per call), GET /prices-history?market=&startTs&endTs&fidelity=10 (calib only)
  Data  GET /v2/resolutions?condition=a,b  (status posed / proposed / resolved, was_disputed, payouts)

  python3 poly_fav.py run          # cloud.sh, every 5 min (~5-10 s)
  python3 poly_fav.py status
  python3 poly_fav.py calib [days] # history check on resolved markets (a few minutes, one-off)
"""
import json, random, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import polymarket as P
from poly_arb import books, trim_log

HERE = Path(__file__).parent
FAV, LONG, TWIN = (str(HERE / f"state_poly_{n}.json") for n in ("fav", "long", "fav_twin"))
LABELS = {FAV: "Polymarket ซื้อตัวเต็ง 0.85-0.97 ในตลาดที่จบภายใน 48 ชม. ไม้ละ 5% ถือจนตัดสินผล (favourite-longshot bias)",
          LONG: "Polymarket ตัวควบคุมฝั่งตรงข้าม: ซื้อตัวรอง 0.03-0.10 ในตลาดแบบเดียวกัน ไม้ละ 5% ถือจนตัดสินผล",
          TWIN: "Polymarket ตัวควบคุม: สุ่มฝั่งในตลาดเดียวกับ fav/long เวลาเดียวกัน ขนาดเดียวกัน"}
LOG, CALIB = HERE / "data" / "poly_fav_log.jsonl", HERE / "data" / "poly_fav_calib.json"
FAV_LO, FAV_HI = 0.85, 0.97      # the user's ranges
LONG_LO, LONG_HI = 0.03, 0.10
MAX_H = 48                       # hours to endDate
MIN_LEAD_S = 300                 # chosen: an endDate less than 5 min away is treated as passed
UNIVERSE, PER_RUN = 900, 300     # chosen: top 900 by 24h volume ending within 48 h, 300 per run (3 Gamma pages), rotating
MAX_SPREAD = 0.03                # chosen: best ask - best bid
DEPTH_BAND, DEPTH_X = 0.02, 5    # chosen: asks within 2 cents of the best ask must hold 5x our order
MAX_NEW = 2                      # chosen: buys per account per run, so 20 slots fill over many runs, not one
LOG_KEEP = 3000
ACT_H, ACT_MIN = 12, 6           # calib: "active" = the history price changed at least 6 times in the 12 h before the lead point
EDGES = [0.0, 0.03, 0.10, 0.20, 0.35, 0.50, 0.65, 0.80, 0.85, 0.90, 0.93, 0.97, 1.0001]


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(f):
    try:
        return json.load(open(f))
    except (OSError, ValueError):
        s = P.new_state(LABELS.get(f, "poly fav"))
        s.update(done={}, ev_done={}, scan_off=0)
        return s


# ---- live scan ----
def scan_markets(off, now):
    rows = []
    for o in range(off, off + PER_RUN, 100):
        rows += P.get(f"{P.GAMMA}/markets", dict(closed="false", limit=100, offset=o, order="volume24hr", ascending="false",
                                                  end_date_min=iso(now + MIN_LEAD_S), end_date_max=iso(now + MAX_H * 3600)))
    return rows


def tokens(m):
    try:
        t, o = json.loads(m.get("clobTokenIds") or "[]"), json.loads(m.get("outcomes") or "[]")
    except ValueError:
        return None
    return t if len(t) == 2 and len(o) == 2 else None


def tradable(m, now):
    end = P.ts_of(m.get("endDate"))
    if not (m.get("enableOrderBook") and m.get("acceptingOrders")) or m.get("closed"):
        return "not accepting orders"
    if not end or end < now + MIN_LEAD_S:
        return "end passed"
    g = utc_ts(m.get("gameStartTime"))
    if g and g < now + MIN_LEAD_S:
        return "game started"                        # sports endDate can be days after the game: never buy in play
    if end > now + MAX_H * 3600:
        return "ends beyond 48 h"
    if m.get("umaResolutionStatus"):
        return f"uma {m['umaResolutionStatus']}"
    return None if tokens(m) else "not a 2-outcome book"


def quote(book, m, usd, lo, hi):
    """dict(ask, px, cost) if the best ask is in [lo, hi], the book is not thin and the average fill stays in [lo, hi];
    None if the best ask is outside the range; a reason string if it is in range but not buyable."""
    asks, bids = P.levels(book, "asks"), P.levels(book, "bids")
    if not asks or not lo <= asks[0][0] <= hi:
        return None
    a = asks[0][0]
    if not bids:
        return "thin: no bid"
    if a - bids[0][0] > MAX_SPREAD + 1e-9:
        return f"thin: spread {a - bids[0][0]:.3f}"
    if sum(px * sz for px, sz in asks if px <= a + DEPTH_BAND + 1e-9) < DEPTH_X * usd:
        return "thin: depth"
    f = P.fill_buy(asks, usd, P.fee_info(m))
    if not f:
        return "thin: fill"
    px = f[1] / f[0]
    if not lo <= px <= hi:
        return f"avg fill {px:.3f} outside range"
    return dict(ask=a, px=px, cost=usd / f[0], bid=bids[0][0])


def res_ok(r):
    """A /v2/resolutions row for an open market: buy only if none yet or the question is just posed and never disputed."""
    if not r:
        return None
    if r.get("was_disputed"):
        return "disputed"
    return None if r.get("status") == "posed" else f"resolution {r.get('status')}"


def event_of(m):
    ev = m.get("events") or []
    return str(ev[0].get("id")) if ev and ev[0].get("id") is not None else m["conditionId"].lower()


def settle_and_mark(s, bk=None):
    if not s["pos"]:
        return
    conds = [q["cond"] for q in s["pos"].values()]
    try:
        res, mk = P.resolutions(conds), P.markets(conds)
        bk = bk if bk is not None and all(t in bk for t in s["pos"]) else books(list(s["pos"]), 500)
    except Exception as e:
        print(f"fav settle/mark fetch: {type(e).__name__}")
        return
    for t, q in list(s["pos"].items()):
        pay, why = P.resolved_payout(res.get(q["cond"]), mk.get(q["cond"]), q["oi"])
        if pay is not None:
            P.settle(s, t, pay, why)
            print(f"  RESOLVED {q['coin'][:60]} -> {pay:g}")
        elif why:
            print(f"  {q['coin'][:40]}: {why}")
        elif P.levels(bk.get(t), "bids"):
            q["last"] = P.levels(bk[t], "bids")[0][0]


def cmd_run(fav=None, long=None, twin=None, log=None, rng=None):
    paths = (fav or FAV, long or LONG, twin or TWIN)
    log, rng = Path(log or LOG), rng or random.Random()
    sf, sl, st = (load(f) for f in paths)
    now = t0 = time.time()
    usd = sf["start_usd"] * P.SIZE
    off = sf.get("scan_off", 0) % UNIVERSE
    try:
        rows = scan_markets(off, now)
        live = [(m, tokens(m)) for m in rows if not tradable(m, now)]
        bk = books([t for _, tk in live for t in tk], 500) if live else {}
        sf["scan_off"] = 0 if len(rows) < PER_RUN else (off + PER_RUN) % UNIVERSE
    except Exception as e:
        print(f"fav scan fetch: {type(e).__name__}")
        rows, live, bk = [], [], None
        sf["scan_off"] = 0                                 # a failing page (Gamma refuses offsets past about 2,000) must not stick
    logrows, cand = [], {"fav": [], "long": []}
    for m, tk in live:
        c, ev, end = m["conditionId"].lower(), event_of(m), P.ts_of(m["endDate"])
        for side, s, lo, hi in (("fav", sf, FAV_LO, FAV_HI), ("long", sl, LONG_LO, LONG_HI)):
            for oi, tok in enumerate(tk):
                q = quote(bk.get(tok), m, usd, lo, hi)
                if q is None:
                    continue
                row = dict(t=int(now), side=side, c=c[:14], q=(m.get("question") or "")[:60], ft=m.get("feeType"), oi=oi,
                           end_h=round((end - now) / 3600, 1), ask=P.levels(bk.get(tok), "asks")[0][0])
                if isinstance(q, str):
                    row["why"] = q
                elif c in s["done"] or ev in s["ev_done"]:
                    row["why"] = "already bought this market/event"
                else:
                    row.update(px=round(q["px"], 4), cost=round(q["cost"], 4))
                    cand[side].append((end, m, oi, tok, q, row, ev))
                logrows.append(row)
                break
    # disputes / proposals: one /v2/resolutions call for the shortlist only
    short = {k: sorted(v, key=lambda x: x[0])[:MAX_NEW * 4] for k, v in cand.items()}
    conds = list({x[1]["conditionId"].lower() for v in short.values() for x in v})
    try:
        res = P.resolutions(conds) if conds else {}
    except Exception as e:
        print(f"fav resolutions fetch: {type(e).__name__}: no buys this run")
        res, short = {}, {"fav": [], "long": []}
    paired = []
    for side, s in (("fav", sf), ("long", sl)):
        n = 0
        for end, m, oi, tok, q, row, ev in short[side]:
            c = m["conditionId"].lower()
            why = res_ok(res.get(c))
            if why is None and (c in s["done"] or ev in s["ev_done"]):
                why = "already bought this market/event"
            if why is None and n >= MAX_NEW:
                why = "max buys this run"
            if why is None:
                pair = f"{c[2:10]}-{int(now)}"
                why = P.buy(s, tok, m, oi, bk.get(tok),
                            f"{side} ask {q['ask']:.3f} เฉลี่ย {q['px']:.3f} ทุนต่อหุ้น {q['cost']:.4f} จบใน {row['end_h']} ชม. ({m.get('feeType')})",
                            pair=pair, event=ev, end_h=row["end_h"], gamma_bid=m.get("bestBid"),
                            vol24=round(float(m.get("volume24hr") or 0)))  # logged only, to split results by volume at entry later
                if why is None:
                    n += 1
                    s["done"][c], s["ev_done"][ev] = int(now), int(now)
                    paired.append((m, pair, ev))
                    print(f"  {side.upper()} {s['pos'][tok]['coin'][:60]} @ {q['px']:.3f} ends in {row['end_h']} h")
            row["bought" if why is None else "why"] = True if why is None else why
        for x in cand[side]:
            if x not in short[side]:
                x[5]["why"] = "not in this run's shortlist (soonest end first)"
    for m, pair, ev in paired:                          # twin: random outcome of each market fav or long just bought
        c = m["conditionId"].lower()
        if c in st["done"]:
            continue
        tk = tokens(m)
        oi = rng.randrange(len(tk))
        why = P.buy(st, tk[oi], m, oi, bk.get(tk[oi]), f"สุ่มฝั่ง {oi} คู่กับ {pair}", pair=pair, event=ev)
        if why is None:
            st["done"][c] = int(now)
        else:
            st["log"].append(dict(kind="skip", t=P.now_iso(), pair=pair, why=why))
    if logrows:
        log.parent.mkdir(exist_ok=True)
        with open(log, "a") as f:
            for r in logrows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        trim_log(log, LOG_KEEP)
    for s in (sf, sl, st):
        s["done"] = {k: v for k, v in s["done"].items() if v > now - 10 * 86400}
        s["ev_done"] = {k: v for k, v in s.get("ev_done", {}).items() if v > now - 10 * 86400}
        settle_and_mark(s, bk)
    for f, s in zip(paths, (sf, sl, st)):
        P.save(f, s)
    nf, nl = sum(r["side"] == "fav" for r in logrows), sum(r["side"] == "long" for r in logrows)
    print(f"poly fav: {len(rows)} markets (offset {off}), {len(live)} tradable, in range fav {nf} long {nl} | "
          + " | ".join(f"{k} {P.value(s) / s['start_usd'] - 1:+.1%} open {len(s['pos'])}" for k, s in zip(("fav", "long", "twin"), (sf, sl, st)))
          + f" ({time.time() - t0:.1f}s)")


def cmd_status():
    for f in (FAV, LONG, TWIN):
        s = load(f)
        sells = [x for x in s["log"] if x["kind"] == "sell"]
        avg = sum(x["pnl"] / (x["usd"] - x["pnl"]) for x in sells) / len(sells) if sells else 0
        ent = sum(x["entry"] for x in sells) / len(sells) if sells else 0
        print(f"{Path(f).name[6:-5]:<14} {P.value(s) / s['start_usd'] - 1:+.1%}  เปิด {len(s['pos'])}  ปิด {len(sells)} "
              f"(ชนะ {sum(x['pnl'] > 0 for x in sells)}, ราคาเข้าเฉลี่ย {ent:.3f})  เฉลี่ยต่อไม้ {avg:+.1%}")


# ---- history check ----
def utc_ts(x):
    """Gamma closedTime '2026-11-16 01:01:54.232351+00' (always UTC) -> epoch seconds, or None."""
    try:
        return datetime.strptime(x[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def price_at(hist, t, tol=3600):
    """Last history price at or before t, if it is at most tol seconds old; else None."""
    pts = [x for x in hist if t - tol <= x["t"] <= t]
    return float(max(pts, key=lambda x: x["t"])["p"]) if pts else None


def table(rows, lead, edges=EDGES, keep=lambda r: True):
    """Calibration buckets for one lead (hours), both outcomes of every market (token 1 price = 1 - token 0 price).
    -> [(lo, hi, n, events, mean price, win rate, z of win - price, mean return per $ after fee and slip at that price,
         z clustered by event)]. Markets of one event (spreads, totals, exact scores of one game) move together, so the plain
    z overstates the evidence; the clustered z uses the sum of residuals per event."""
    pts = []
    for r in rows:
        p = r["p"].get(str(lead))
        if p is None or not keep(r):
            continue
        for px, y in ((p, r["y"]), (1 - p, 1 - r["y"])):
            pts.append((px, y, r["ev"], r.get("rate", 0.0)))
    out = []
    for lo, hi in zip(edges, edges[1:]):
        b = [x for x in pts if lo <= x[0] < hi]
        if not b:
            out.append((lo, min(hi, 1.0), 0, 0, None, None, None, None, None))
            continue
        n = len(b)
        mp, wr = sum(x[0] for x in b) / n, sum(x[1] for x in b) / n
        var = sum(x[0] * (1 - x[0]) for x in b)
        z = (wr - mp) * n / var ** 0.5 if var > 0 else None
        ret = sum(x[1] / (x[0] * (1 + P.SLIP) + x[3] * x[0] * (1 - x[0])) - 1 for x in b if x[0] > 0) / n
        d = wr - mp
        per = {}
        for x in b:
            per[x[2]] = per.get(x[2], 0.0) + (x[1] - x[0] - d)
        cv = sum(v * v for v in per.values()) / n ** 2
        out.append((lo, min(hi, 1.0), n, len(per), mp, wr, z, ret, d / cv ** 0.5 if cv > 0 else None))
    return out


def fetch_resolved(days, hours_per_day, now, rng):
    """First Gamma page (100, ordered by id = creation order) of closed markets for `hours_per_day` random hours of endDate
    on each of the last `days` days. Not ordered by volume: total volume includes in-play trading, which is larger when a
    favourite loses, so a top-by-volume sample over-counts upsets (the first calib run did that; data/poly_fav_calib_byvolume.json)."""
    slots = [(d, h) for d in range(days) for h in rng.sample(range(24), hours_per_day)]

    def page(a):
        d, h = a
        lo = now - (d + 1) * 86400 + h * 3600
        if lo + 3600 > now - 3600:
            return []
        return P.get(f"{P.GAMMA}/markets", dict(closed="true", limit=100, offset=0, order="id", ascending="true",
                                                 end_date_min=iso(lo), end_date_max=iso(lo + 3599)))
    with ThreadPoolExecutor(6) as ex:
        pages = list(ex.map(page, slots))
    seen, out = set(), []
    for pg in pages:
        for m in pg:
            if m["conditionId"] not in seen:
                seen.add(m["conditionId"])
                out.append(m)
    return out


def cmd_calib(days=30, hours_per_day=8, max_hist=6000, leads=(1, 6, 24), seed=23):
    now, t0 = time.time(), time.time()
    rng = random.Random(seed)
    ms = fetch_resolved(days, hours_per_day, now, rng)
    drop = {}
    keep = []
    for m in ms:
        tk, end, ct = tokens(m), P.ts_of(m.get("endDate")), utc_ts(m.get("closedTime"))
        g = utc_ts(m.get("gameStartTime"))
        if end and g:
            end = min(end, g)                            # reference = game start: prices after it are in play
        why = None
        if not tk or not m.get("enableOrderBook"):
            why = "no 2-outcome book"
        elif not end or not ct:
            why = "no end/closed time"
        elif ct < end - 3600:
            why = "closed more than 1 h before endDate/game start (outcome may be known early)"
        elif (utc_ts(m.get("acceptingOrdersTimestamp") or m.get("startDate")) or 9e9) > end - max(leads) * 3600:
            why = f"opened less than {max(leads)} h before endDate"
        if why:
            drop[why] = drop.get(why, 0) + 1
        else:
            keep.append((m, tk, end))
    if len(keep) > max_hist:
        drop["random sample cut (history call budget)"] = len(keep) - max_hist
        keep = rng.sample(keep, max_hist)
    conds = [m["conditionId"].lower() for m, _, _ in keep]

    def res_chunk(i):
        return P.resolutions(conds[i:i + 20])
    res = {}
    with ThreadPoolExecutor(8) as ex:
        for d in ex.map(res_chunk, range(0, len(conds), 20)):
            res.update(d)

    def hist(x):
        m, tk, end = x
        try:
            return P.get(f"{P.CLOB}/prices-history", dict(market=tk[0], startTs=int(end - (max(leads) + ACT_H) * 3600), endTs=int(end), fidelity=10))["history"]
        except Exception:
            return None
    with ThreadPoolExecutor(8) as ex:
        hs = list(ex.map(hist, keep))
    rows = []
    for (m, tk, end), h in zip(keep, hs):
        c = m["conditionId"].lower()
        r = res.get(c)
        pay, why = P.resolved_payout(r, m, 0)
        if r and r.get("was_disputed"):
            why = "disputed"
        elif pay is None or pay not in (0.0, 1.0):
            why = why or ("50-50 or unresolved" if pay is None or pay == 0.5 else f"payout {pay}")
        elif h is None:
            why = "history fetch failed"
        else:
            why = None
        if why:
            drop[why] = drop.get(why, 0) + 1
            continue
        p = {str(L): price_at(h, end - L * 3600) for L in leads}
        chg = {}                                         # price changes in the 12 h before each lead point (activity, no look-ahead)
        for L in leads:
            w = [x["p"] for x in sorted(h, key=lambda x: x["t"]) if end - L * 3600 - ACT_H * 3600 <= x["t"] <= end - L * 3600]
            chg[str(L)] = sum(a != b for a, b in zip(w, w[1:]))
        rows.append(dict(c=c[:14], q=(m.get("question") or "")[:50], ft=m.get("feeType"), ev=event_of(m), end=int(end),
                         vol=round(float(m.get("volumeNum") or 0)), rate=P.fee_info(m)[0], y=pay, p=p, chg=chg))
    CALIB.parent.mkdir(exist_ok=True)
    CALIB.write_text(json.dumps(dict(fetched=iso(now), days=days, markets=len(ms), dropped=drop, rows=rows), ensure_ascii=False))
    print(f"calib: {len(ms)} closed markets (first 100 by id in {hours_per_day} random endDate hours per day, last {days} days, seed {seed}), kept {len(rows)}, dropped {drop}, "
          f"{time.time() - t0:.0f}s -> {CALIB.name}")
    report(rows, leads)


def report(rows, leads=(1, 6, 24)):
    for L in leads:
        k = str(L)
        act = lambda r: r.get("chg", {}).get(k, 0) >= ACT_MIN
        groups = (("all", lambda r: True), (f"active", act),
                  ("sports", lambda r: (r["ft"] or "").startswith("sports")),
                  ("sports+act", lambda r: (r["ft"] or "").startswith("sports") and act(r)),
                  ("other", lambda r: not (r["ft"] or "").startswith("sports")),
                  ("other+act", lambda r: not (r["ft"] or "").startswith("sports") and act(r)))
        print(f"\nlead {L} h before endDate (both outcomes of each market; price = CLOB prices-history, not the ask; "
              f"active = price changed >= {ACT_MIN} times in the {ACT_H} h before)")
        print(f"  {'bucket':<11} {'n':>5} {'events':>6} {'price':>6} {'won':>6} {'won-px':>7} {'z':>6} {'z_ev':>6} {'ret/$':>7}")
        rz = lambda z: "" if z is None else round(z, 2)
        for lo, hi, n, ne, mp, wr, z, ret, ze in table(rows, L):
            if n:
                print(f"  {lo:.2f}-{hi:.2f}  {n:>5} {ne:>6} {mp:>6.3f} {wr:>6.3f} {wr - mp:>+7.3f} {rz(z):>6} {rz(ze):>6} {ret:>+7.3f}")
        for name, f in groups:
            fa = table(rows, L, [FAV_LO, FAV_HI + 1e-9], f)[0]
            lg = table(rows, L, [LONG_LO, LONG_HI + 1e-9], f)[0]
            s = lambda b: (f"n {b[2]} ev {b[3]} px {b[4]:.3f} won {b[5]:.3f} ({b[5] - b[4]:+.3f}, z {rz(b[6])}, z_ev {rz(b[8])}) "
                           f"ret/$ {b[7]:+.3f}") if b[2] else "n 0"
            print(f"  {name:<10} fav {FAV_LO}-{FAV_HI}: {s(fa)}\n  {'':<10} long {LONG_LO}-{LONG_HI}: {s(lg)}")


if __name__ == "__main__":
    cmds = {"run": cmd_run, "status": cmd_status,
            "calib": lambda: cmd_calib(int(sys.argv[2]) if len(sys.argv) > 2 else 30),
            "report": lambda: report(json.loads(Path(sys.argv[2] if len(sys.argv) > 2 else CALIB).read_text())["rows"])}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]]()
