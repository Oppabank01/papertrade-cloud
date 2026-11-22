#!/usr/bin/env python3
"""Polymarket YES+NO pair "arbitrage" (idea from X user jbfly46; the scout rejected it, opened 23 Nov 2026 to try first).
Fake money only: public read-only APIs, no login, no keys, no wallet, no orders anywhere.

  state_poly_arb.json  each run scans a slice of binary markets ending within 14 days. For PAIRS shares of YES and PAIRS
                       shares of NO it walks both live ask books level by level, adds the taker fee of each side and SLIP
                       0.5% of notional per side. If that total per pair is below 1, it buys the pair on paper. A pair pays
                       exactly 1 at resolution (YES + NO payouts; a 50-50 resolution pays 0.5 + 0.5), so it is held to the end.
                       Marked to the two best bids meanwhile (shows the spread as a loss until it resolves).
  data/poly_arb_log.jsonl  every binary market seen with both books deep enough: best asks, raw gap 1 - (ask_yes + ask_no)
                       and the gap after fees and slip, bought or not; the last LOG_KEEP lines only. state["stats"] keeps
                       counts of the gap for every market ever seen, so the frequency of a real gap survives the trim.

Why it should fail (written before any result): the CLOB matches a YES bid against a NO bid (a NO bid at q is a YES ask at
1 - q), so in one binary market ask_yes + ask_no should never be below 1; the raw gap is minus the spread. The log measures it.
Dead (written before any result): no market with a gap above 0 after costs in 7 days of runs (stats.best_net <= 0), or 20 closed
pairs with a negative total. Pass: 50 closed pairs, positive after costs (a true pair cannot lose unless a payout breaks).

Endpoints (each checked 23 Nov 2026, all public):
  Gamma GET /markets?closed=false&end_date_min&end_date_max&order=volume24hr  docs.polymarket.com/api-spec/gamma-openapi.yaml
  CLOB POST /books (security: [] in the spec; 500 tokens per call answered in 1 s)  docs.polymarket.com/api-spec/clob-openapi.yaml
  Fees fee = C x rate x p(1-p), rate per market from Gamma feeSchedule              docs.polymarket.com/trading/fees.md
  Data API GET /v2/resolutions?condition=  (payouts in micro-USDC per share)         docs.polymarket.com/migrate/data-api-v1-to-v2.md
  Resolution: winning token redeems 1, losing 0, 50-50 pays 0.5                     docs.polymarket.com/concepts/resolution.md

  python3 poly_arb.py run      # cloud.sh, every 5 min
  python3 poly_arb.py status
"""
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

import polymarket as P

HERE = Path(__file__).parent
STATE = str(HERE / "state_poly_arb.json")
LOG = HERE / "data" / "poly_arb_log.jsonl"
LABEL = "Polymarket ซื้อ YES+NO คู่กันเมื่อรวมต่ำกว่า 1 หลังค่าธรรมเนียม ถือจนตัดสินผล (ไอเดีย jbfly46)"
PAIRS = 5.0          # shares per side: the CLOB min_order_size (5) so a real order could exist; about $5 of the $14.75 start
MAX_DAYS = 14
UNIVERSE = 600       # top markets by 24h volume ending within 14 days
PER_RUN = 300        # markets per run (3 Gamma pages + 6 book calls, a few seconds); the slice rotates through UNIVERSE
LOG_KEEP = 2000
BUCKETS = [-1.0, -0.05, -0.02, -0.01, -0.005, 0.0, 0.005, 0.01]   # gap histogram lower edges (gap = 1 - cost per pair)


def new_state():
    s = P.new_state(LABEL)
    s.update(scan_off=0, stats=dict(seen=0, raw={}, net={}, best_raw=None, best_net=None))
    return s


def load(f=None):
    try:
        return json.load(open(f or STATE))
    except (OSError, ValueError):
        return new_state()


def walk(asks, n, fee):
    """Buy exactly n shares walking the asks. -> (notional, fee_usd) or None if the book is too thin."""
    left, notional, f = n, 0.0, 0.0
    for px, size in asks:
        take = min(size, left)
        notional, f, left = notional + take * px, f + P.fee_of(take, px, fee), left - take
        if left <= 1e-9:
            return notional, f
    return None


def pair_cost(m, book_yes, book_no, n=PAIRS):
    """Cost of n YES + n NO at the live asks incl. both taker fees and SLIP per side, or None if a side is too thin."""
    fee = P.fee_info(m)
    ay, an = P.levels(book_yes, "asks"), P.levels(book_no, "asks")
    wy, wn = walk(ay, n, fee), walk(an, n, fee)
    if not (wy and wn):
        return None
    notional, fees = wy[0] + wn[0], wy[1] + wn[1]
    total = notional + fees + P.SLIP * notional
    return dict(ask_yes=ay[0][0], ask_no=an[0][0], raw=round(1 - ay[0][0] - an[0][0], 5), notional=notional, fee_usd=fees,
                total=total, per_pair=total / n, gap=round(1 - total / n, 5), fee=list(fee))


def bucket(g):
    return str(max(b for b in BUCKETS if g >= b)) if g >= BUCKETS[0] else "lt-1"


def books(tokens, n=100):
    out, tokens = {}, list(dict.fromkeys(tokens))
    for i in range(0, len(tokens), n):
        for b in P.post(f"{P.CLOB}/books", [dict(token_id=t) for t in tokens[i:i + n]]):
            out[b["asset_id"]] = b
    return out


def scan_markets(off, now):
    """One slice of binary, order-book, accepting markets ending within MAX_DAYS, by 24h volume."""
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for o in range(off, off + PER_RUN, 100):
        rows += P.get(f"{P.GAMMA}/markets", dict(closed="false", limit=100, offset=o, order="volume24hr", ascending="false",
                                                  end_date_min=iso(now), end_date_max=iso(now + MAX_DAYS * 86400)))
    out = []
    for m in rows:
        try:
            toks, outs = json.loads(m.get("clobTokenIds") or "[]"), json.loads(m.get("outcomes") or "[]")
        except ValueError:
            continue
        if len(toks) == 2 and len(outs) == 2 and m.get("enableOrderBook") and m.get("acceptingOrders") and not m.get("closed"):
            out.append((m, toks))
    return out, len(rows)


def buy_pair(s, m, toks, pc, why):
    c = m["conditionId"].lower()
    if c in s["pos"]:
        return "holding"
    if s["cash"] < pc["total"]:
        return "no cash"
    coin = f"YES+NO | {m.get('question', '')}"[:90]
    s["cash"] -= pc["total"]
    s["pos"][c] = dict(qty=PAIRS, entry=pc["per_pair"], last=pc["per_pair"], usd=pc["total"], t=P.now_iso(), why=why, coin=coin,
                       cond=c, tokens=toks, fee=pc["fee"], end=m.get("endDate"))
    s["log"].append(dict(kind="buy", t=P.now_iso(), coin=coin, token=c, px=round(pc["per_pair"], 5), usd=round(pc["total"], 5),
                         qty=PAIRS, fee_usd=round(pc["fee_usd"], 5), cost_side=round((pc["total"] - pc["notional"]) / pc["notional"], 5),
                         ask_yes=pc["ask_yes"], ask_no=pc["ask_no"], gap=pc["gap"], why=why))
    return None


def pair_payout(r, m):
    """(payout per pair, why) once resolved; the pair must pay exactly 1 or nothing is settled."""
    p0, w0 = P.resolved_payout(r, m, 0)
    p1, w1 = P.resolved_payout(r, m, 1)
    if p0 is None or p1 is None:
        return None, w0 or w1
    if abs(p0 + p1 - 1) > 1e-6:
        return None, f"payouts {p0} + {p1} != 1"
    return p0 + p1, f"ตัดสินผลแล้ว YES {p0:g} + NO {p1:g}"


def settle_and_mark(s, bk=None):
    if not s["pos"]:
        return
    conds = list(s["pos"])
    try:
        res, mk = P.resolutions(conds), P.markets(conds)
        bk = bk if bk is not None else books([t for q in s["pos"].values() for t in q["tokens"]])
    except Exception as e:
        print(f"arb settle/mark fetch: {type(e).__name__}")
        return
    for c, q in list(s["pos"].items()):
        pay, why = pair_payout(res.get(c), mk.get(c))
        if pay is not None:
            P.close(s, c, q["qty"] * pay, pay, why, 0.0)
            print(f"  RESOLVED {q['coin'][:50]} -> {pay}")
            continue
        if why:
            print(f"  {q['coin'][:40]}: {why}")
        by, bn = (P.levels(bk.get(t), "bids") for t in q["tokens"])
        if by and bn:
            q["last"] = by[0][0] + bn[0][0]


def trim_log(path, keep):
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return
    if len(lines) > keep:
        path.write_text("\n".join(lines[-keep:]) + "\n")


def cmd_run(state=None, log=None):
    state, log = state or STATE, Path(log or LOG)
    s = load(state)
    now, t0 = time.time(), time.time()
    off = s.get("scan_off", 0) % UNIVERSE
    try:
        cand, n_rows = scan_markets(off, now)
        bk = books([t for _, toks in cand for t in toks])
    except Exception as e:
        print(f"arb scan fetch: {type(e).__name__}")
        cand, n_rows, bk = [], None, None
    if n_rows is not None:                                   # a failed fetch keeps the slice for next run
        s["scan_off"] = 0 if n_rows < PER_RUN else (off + PER_RUN) % UNIVERSE
    st, rows, thin = s["stats"], [], 0
    for m, toks in cand:
        pc = pair_cost(m, bk.get(toks[0]), bk.get(toks[1]))
        if not pc:
            thin += 1
            continue
        why = None
        if pc["gap"] > 0:
            why = buy_pair(s, m, toks, pc, f"YES {pc['ask_yes']} + NO {pc['ask_no']} รวมค่าธรรมเนียม {pc['per_pair']:.4f} ต่อคู่ ช่อง {pc['gap']:+.4f}")
            print(f"  ARB {m.get('question', '')[:50]} gap {pc['gap']:+.4f}: {'bought' if why is None else why}")
        st["seen"] += 1
        for k, g in (("raw", pc["raw"]), ("net", pc["gap"])):
            st[k][bucket(g)] = st[k].get(bucket(g), 0) + 1
            if st["best_" + k] is None or g > st["best_" + k]:
                st["best_" + k] = g
        rows.append(dict(t=int(now), c=m["conditionId"][:12], q=m.get("question", "")[:48], ft=m.get("feeType"), ay=pc["ask_yes"],
                         an=pc["ask_no"], raw=pc["raw"], gap=pc["gap"], b=int(pc["gap"] > 0 and why is None)))
    if rows or cand:
        log.parent.mkdir(exist_ok=True)
        with open(log, "a") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        trim_log(log, LOG_KEEP)
    settle_and_mark(s, bk if bk is not None and all(t in bk for q in s["pos"].values() for t in q["tokens"]) else None)
    P.save(state, s)
    best = max((r["gap"] for r in rows), default=None)
    print(f"poly arb: {len(cand)} binary markets (offset {off}), {len(rows)} with depth for {PAIRS:g} shares, {thin} thin, "
          f"best gap after costs {best if best is None else f'{best:+.4f}'}, open {len(s['pos'])}, value {P.value(s) / s['start_usd'] - 1:+.2%}, "
          f"{time.time() - t0:.1f}s")


def cmd_status():
    s = load()
    st = s["stats"]
    sells = [x for x in s["log"] if x["kind"] == "sell"]
    print(f"arb {P.value(s) / s['start_usd'] - 1:+.2%}  เปิด {len(s['pos'])}  ปิด {len(sells)}  เห็นตลาด {st['seen']} ครั้ง")
    for k in ("raw", "net"):
        print(f"  {k} gap: " + "  ".join(f"{b}:{st[k][b]}" for b in sorted(st[k], key=lambda x: float(x) if x != 'lt-1' else -9))
              + f"  best {st['best_' + k]}")


if __name__ == "__main__":
    cmds = {"run": cmd_run, "status": cmd_status}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]]()
