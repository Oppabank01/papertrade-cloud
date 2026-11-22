#!/usr/bin/env python3
"""Paper accounts that copy top Polymarket wallets (opened 23 Nov 2026 after an X post about wallet "bosona"). Fake money only:
public read-only APIs, no login, no keys, no wallet, no orders anywhere.

  state_poly_copy.json  every new taker BUY (>= $20) of a listed wallet -> paper buy of the same outcome token,
                        5% of the 500 THB start, at the live CLOB ask; exit when that wallet sells the token
                        (any fill, maker or taker) at the live bid, or at resolution (pays the outcome's payout, 1 or 0)
  state_poly_twin.json  control: at the same moment, the same size on a random outcome of a random open market with the
                        same Gamma feeType (fee category, e.g. sports_fees_v3, crypto_btc_5m_15m_fees) and a similar time
                        to its end date; it sells when its copy partner sells, otherwise holds to resolution

Wallets: research_notes/polymarket-wallets-2026-11-23.md (rule in that file; `pick` reruns it).
Cost per side: the market's own taker fee from Gamma feeSchedule (fee = shares x rate x (p(1-p))^exponent, docs.polymarket.com/trading/fees)
+ walking the live order book level by level + SLIP 0.5% of notional for the delay between reading the book and filling.
Resolution pays no fee. A failed fetch means no action this run; prices only come from the live book or the resolution payouts.

  python3 polymarket.py run      # poll trades, copy, exits, mark to the bid (cloud.sh, every 5 min)
  python3 polymarket.py status
  python3 polymarket.py pick     # rerun the wallet rule and print candidates (does not change the list)
"""
import json, os, random, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
TZ = timezone(timedelta(hours=7))
DATA, GAMMA, CLOB = "https://data-api.polymarket.com", "https://gamma-api.polymarket.com", "https://clob.polymarket.com"
THB, RATE = 500.0, 33.9
SIZE = 0.05                  # of the starting balance per buy
SLIP = 0.005                 # per side, on top of the book walk and the taker fee
FALLBACK_FEE = (0.05, 1.0)   # fees on but no schedule in Gamma: the highest category rate in the fee table
MIN_LEADER_USD = 20          # leader's fill size*price; smaller fills are noise
STALE_MIN = 15               # leader fill older than this when we see it: too late to copy
MAX_CHASE = 0.05             # skip if our best ask is more than 5 cents above the leader's price
PX_MIN, PX_MAX = 0.02, 0.98  # our average fill price; outside this the fee and tick eat the payoff
MAX_DAYS = 14                # only markets ending within 14 days, so cash turns over during the test
MAX_NEW_PER_WALLET = 2       # per run, so one busy wallet cannot take all the cash at once
NOTES = HERE / "research_notes" / "polymarket-wallets-2026-11-23.md"
COPY, TWIN = str(HERE / "state_poly_copy.json"), str(HERE / "state_poly_twin.json")
LABELS = {COPY: "Polymarket ตามกระเป๋าเก่ง ไม้ละ 5% ซื้อตาม BUY ขายตามเจ้าของหรือรอผลตัดสิน",
          TWIN: "Polymarket ตัวควบคุม: สุ่มฝั่งตลาดประเภทเดียวกัน เวลาเดียวกัน ขนาดเดียวกัน"}


def wallets():
    return re.findall(r"^- (0x[0-9a-fA-F]{40}) \|", NOTES.read_text(), re.M) if NOTES.exists() else []


def get(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": "papertrade-bot/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"User-Agent": "papertrade-bot/1.0", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")


def ts_of(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


# ---- fetchers (raise on failure; callers treat a failure as "no action") ----
def markets(conds):
    """Gamma markets by condition id, open or closed: {condition_id: market}."""
    out, conds = {}, list(dict.fromkeys(conds))
    for i in range(0, len(conds), 50):
        for m in get(f"{GAMMA}/markets", dict(condition_ids=conds[i:i + 50], closed="any", limit=100)):
            out[m["conditionId"].lower()] = m
    return out


def books(tokens):
    """CLOB order books (POST /books, public): {token_id: book}. Tokens without a book (closed markets) are missing."""
    out, tokens = {}, list(dict.fromkeys(tokens))
    for i in range(0, len(tokens), 20):
        for b in post(f"{CLOB}/books", [dict(token_id=t) for t in tokens[i:i + 20]]):
            out[b["asset_id"]] = b
    return out


def resolutions(conds):
    """Data API /v2/resolutions rows by condition id."""
    out, conds = {}, list(dict.fromkeys(conds))
    for i in range(0, len(conds), 20):
        for r in get(f"{DATA}/v2/resolutions", dict(condition=",".join(conds[i:i + 20])))["data"]:
            if r.get("condition_id"):
                out[r["condition_id"].lower()] = r
    return out


# ---- pricing ----
def levels(book, side):
    """Best first: asks ascending, bids descending (the API does not promise an order)."""
    return sorted(((float(x["price"]), float(x["size"])) for x in (book or {}).get(side) or []), reverse=side == "bids")


def fee_info(m):
    if m.get("feesEnabled") is False:
        return (0.0, 1.0)
    fs = m.get("feeSchedule") or {}
    return (float(fs["rate"]), float(fs.get("exponent") or 1)) if fs.get("rate") is not None else FALLBACK_FEE


def fee_of(shares, px, fee):
    return shares * fee[0] * (px * (1 - px)) ** fee[1]


def fill_buy(asks, usd, fee):
    """Spend `usd` in total (notional + taker fee + SLIP) walking the asks. -> (shares, notional, fee_usd) or None if too thin."""
    left, sh, notional, f = usd, 0.0, 0.0, 0.0
    for px, size in asks:
        unit = px * (1 + SLIP) + fee_of(1, px, fee)
        take = min(size, left / unit)
        sh, notional, f, left = sh + take, notional + take * px, f + fee_of(take, px, fee), left - take * unit
        if left <= 1e-9:
            return sh, notional, f
    return None


def fill_sell(bids, qty, fee):
    """Sell `qty` walking the bids. -> (gross, fee_usd, net) or None if the bids are too thin."""
    left, gross, f = qty, 0.0, 0.0
    for px, size in bids:
        take = min(size, left)
        gross, f, left = gross + take * px, f + fee_of(take, px, fee), left - take
        if left <= 1e-9:
            return gross, f, gross - f - SLIP * gross
    return None


# ---- accounting ----
def new_state(label):
    return dict(label=label, start_thb=THB, start_usd=THB / RATE, cash=THB / RATE, pos={}, log=[], cursor={}, seen={})


def load(f):
    try:
        return json.load(open(f))
    except (OSError, ValueError):
        return new_state(LABELS.get(f, "polymarket"))


def save(f, s):
    json.dump(s, open(f + ".tmp", "w"), ensure_ascii=False, indent=1)
    os.replace(f + ".tmp", f)


def outcome_name(m, oi):
    try:
        return json.loads(m["outcomes"])[oi]
    except (KeyError, ValueError, IndexError, TypeError):
        return str(oi)


def buy(s, token, m, oi, book, why, **extra):
    """Paper buy of one outcome token at the live asks. Returns None when bought, else the reason it did not."""
    usd = s["start_usd"] * SIZE
    if token in s["pos"]:
        return "holding"
    if s["cash"] < usd:
        return "no cash"
    fee = fee_info(m)
    f = fill_buy(levels(book, "asks"), usd, fee)
    if not f:
        return "no asks / book too thin"
    sh, notional, fusd = f
    px = notional / sh
    if not PX_MIN <= px <= PX_MAX:
        return f"price {px:.3f} outside {PX_MIN}-{PX_MAX}"
    bids = levels(book, "bids")
    s["cash"] -= usd
    coin = f"{outcome_name(m, oi)} | {m.get('question', '')}"[:90]
    cost_side = round((usd - notional) / notional, 5)        # fee + slip as a fraction of notional on this side
    s["pos"][token] = dict(qty=sh, entry=px, last=bids[0][0] if bids else px, usd=usd, t=now_iso(), why=why, coin=coin,
                           cond=m["conditionId"].lower(), oi=oi, fee=list(fee), end=m.get("endDate"), **extra)
    s["log"].append(dict(kind="buy", t=now_iso(), coin=coin, token=token, px=round(px, 5), usd=round(usd, 5), qty=round(sh, 5),
                         fee_usd=round(fusd, 5), cost_side=cost_side, gamma_ask=m.get("bestAsk"), why=why, **extra))
    return None


def close(s, token, net, px, why, cost_side):
    q = s["pos"].pop(token)
    s["cash"] += net
    s["log"].append(dict(kind="sell", t=now_iso(), coin=q["coin"], token=token, px=round(px, 5), entry=round(q["entry"], 5),
                         usd=round(net, 5), pnl=round(net - q["usd"], 5), cost_side=cost_side, why=why,
                         **{k: q[k] for k in ("wallet", "pair") if k in q}))


def sell(s, token, book, why):
    q = s["pos"][token]
    f = fill_sell(levels(book, "bids"), q["qty"], q["fee"])
    if not f:
        return "no bids / book too thin"
    gross, fusd, net = f
    close(s, token, net, gross / q["qty"], why, round((gross - net) / gross, 5) if gross else 0)
    return None


def settle(s, token, payout, why):
    q = s["pos"][token]
    close(s, token, q["qty"] * payout, payout, why, 0.0)


def value(s):
    return s["cash"] + sum(q["qty"] * q["last"] for q in s["pos"].values())


# ---- one run ----
def leader_fills(w, since, conds=None, side="BUY"):
    """Taker BUY fills since `since` (the leader's own decisions), or every SELL fill (maker too) in `conds`."""
    p = dict(user=w, start=int(since), side=side, limit=500)
    if side == "SELL":
        p.update(taker_only="false", condition=",".join(conds))
    return get(f"{DATA}/v2/trades", p)["data"]


def twin_buy(twin, m, pair, rng, cache):
    """Random outcome of a random open market with the same feeType and a similar time to its end, same size."""
    now = time.time()
    end = ts_of(m.get("endDate")) or now
    h = max(end - now, 1800)
    lo, hi = now + h / 2, min(now + h * 2, now + MAX_DAYS * 86400)
    key = (m.get("feeType"), int(lo // 1800), int(hi // 1800))
    if key not in cache:
        rows = []
        for off in (0, 100, 200):
            rows += get(f"{GAMMA}/markets", dict(closed="false", limit=100, offset=off, order="volume24hr", ascending="false",
                                                 end_date_min=datetime.fromtimestamp(lo, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                 end_date_max=datetime.fromtimestamp(hi, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
        cache[key] = rows
    ev = {e.get("id") for e in m.get("events") or []}
    pool = [x for x in cache[key] if x.get("feeType") == m.get("feeType") and x.get("acceptingOrders") and x.get("enableOrderBook")
            and x.get("clobTokenIds") and x["conditionId"].lower() != m["conditionId"].lower()
            and not ev & {e.get("id") for e in x.get("events") or []}]
    rng.shuffle(pool)
    why = "no similar open market"
    for x in pool[:4]:
        toks = json.loads(x["clobTokenIds"])
        oi = rng.randrange(len(toks))
        b = books([toks[oi]]).get(toks[oi])
        why = buy(twin, toks[oi], x, oi, b, f"สุ่มฝั่งคู่กับ {pair} ({x.get('feeType')})", pair=pair)
        if why is None:
            return None
    twin["log"].append(dict(kind="skip", t=now_iso(), pair=pair, why=why))
    return why


def cmd_run():
    W = wallets()
    copy, twin = load(COPY), load(TWIN)
    now, rng, cache = time.time(), random.Random(), {}
    seen = {k: v for k, v in copy["seen"].items() if v > now - 86400}
    # 1) leader sells of tokens we copied from them
    for w in W:
        held = {t: q for t, q in copy["pos"].items() if q.get("wallet") == w}
        if not held:
            continue
        try:
            fills = leader_fills(w, min(q["leader_ts"] for q in held.values()), [q["cond"] for q in held.values()], "SELL")
        except Exception as e:
            print(f"poly {w[:8]} sells: {type(e).__name__}")
            continue
        out = {x["token_id"] for x in fills if x["token_id"] in held and int(x["timestamp"]) >= held[x["token_id"]]["leader_ts"]}
        if not out:
            continue
        try:
            bk = books(list(out) + [t for t, q in twin["pos"].items() if q.get("pair") in {held[o]["pair"] for o in out}])
        except Exception as e:
            print(f"poly books: {type(e).__name__}")
            continue
        for t in out:
            pair = held[t]["pair"]
            r = sell(copy, t, bk.get(t), "เจ้าของกระเป๋าขาย")
            print(f"  LEADER SELL {held[t]['coin'][:50]}: {'sold' if r is None else r}")
            if r is None:
                for tt in [k for k, q in twin["pos"].items() if q.get("pair") == pair]:
                    sell(twin, tt, bk.get(tt), "คู่ copy ขาย")
    # 2) new leader buys
    cand = []
    for w in W:
        since = copy["cursor"].get(w)
        if since is None:
            copy["cursor"][w] = int(now)            # a new wallet starts now: no back-filling
            continue
        try:
            fills = leader_fills(w, since)
        except Exception as e:
            print(f"poly {w[:8]} buys: {type(e).__name__}")
            continue
        if fills:
            copy["cursor"][w] = max(since, max(int(x["timestamp"]) for x in fills))
        for x in sorted(fills, key=lambda x: int(x["timestamp"])):
            k = f"{x.get('transaction_hash')}:{x['token_id']}:{x['size']}:{x['price']}"
            if k in seen:
                continue
            seen[k] = int(x["timestamp"])
            if float(x["size"]) * float(x["price"]) >= MIN_LEADER_USD and now - int(x["timestamp"]) <= STALE_MIN * 60:
                cand.append((w, x))
    if cand:
        try:
            mk = markets([x["condition_id"].lower() for _, x in cand])
            bk = books([x["token_id"] for _, x in cand])
        except Exception as e:
            print(f"poly market/book fetch: {type(e).__name__}")
            cand = []
    per = {}
    for w, x in cand:
        if per.get(w, 0) >= MAX_NEW_PER_WALLET:
            continue
        m, t = mk.get(x["condition_id"].lower()), x["token_id"]
        end = ts_of((m or {}).get("endDate"))
        lag = round((now - int(x["timestamp"])) / 60, 1)
        if not m or m.get("closed") or not m.get("acceptingOrders"):
            why = "market closed or unknown"
        elif not end or end < now or end - now > MAX_DAYS * 86400:
            why = "ends beyond 14 days" if end and end > now else "end date passed"
        elif t not in bk:
            why = "no book"
        elif (levels(bk[t], "asks") or [(9, 0)])[0][0] - float(x["price"]) > MAX_CHASE:
            why = f"ask moved > {MAX_CHASE} above leader {float(x['price']):.3f}"
        else:
            pair = f"{w[2:8]}-{int(x['timestamp'])}-{t[-6:]}"
            why = buy(copy, t, m, int(x["outcome_index"]), bk[t], f"ตาม {x.get('name') or w[:8]} ซื้อ {float(x['size']):.0f} หุ้นที่ {float(x['price']):.3f} ช้า {lag} นาที",
                      wallet=w, leader_px=float(x["price"]), leader_ts=int(x["timestamp"]), lag_min=lag, pair=pair)
            if why is None:
                per[w] = per.get(w, 0) + 1
                try:
                    tw = twin_buy(twin, m, pair, rng, cache)
                except Exception as e:
                    tw = f"fetch failed {type(e).__name__}"
                    twin["log"].append(dict(kind="skip", t=now_iso(), pair=pair, why=tw))
                print(f"  COPY {copy['pos'][t]['coin'][:50]} @ {copy['pos'][t]['entry']:.3f} (leader {x['price']}) twin: {'bought' if tw is None else tw}")
                continue
        if why not in ("holding", "no cash"):
            copy["log"].append(dict(kind="skip", t=now_iso(), wallet=w, token=t, coin=x.get("title", "")[:80], lag_min=lag, why=why))
    copy["seen"] = seen
    # 3) resolutions and marks for everything still open
    for s in (copy, twin):
        if not s["pos"]:
            continue
        conds = [q["cond"] for q in s["pos"].values()]
        try:
            res, mk2, bk2 = resolutions(conds), markets(conds), books(list(s["pos"]))
        except Exception as e:
            print(f"poly settle/mark fetch: {type(e).__name__}")
            continue
        for t, q in list(s["pos"].items()):
            pay, why = resolved_payout(res.get(q["cond"]), mk2.get(q["cond"]), q["oi"])
            if pay is not None:
                settle(s, t, pay, why)
                print(f"  RESOLVED {q['coin'][:50]} -> {pay}")
            elif why:
                print(f"  {q['coin'][:40]}: {why}")
            elif levels(bk2.get(t), "bids"):
                q["last"] = levels(bk2[t], "bids")[0][0]
    save(COPY, copy)
    save(TWIN, twin)
    print(f"poly copy {value(copy) / copy['start_usd'] - 1:+.1%} open {len(copy['pos'])} | twin {value(twin) / twin['start_usd'] - 1:+.1%} open {len(twin['pos'])}")


def resolved_payout(r, m, oi):
    """(payout per share, why) once the market is resolved, (None, None) while it is not, (None, reason) if sources disagree.
    Primary: /v2/resolutions payouts (micro-USDC per share). Fallback: Gamma closed + umaResolutionStatus resolved + outcomePrices."""
    pay = None
    if r and r.get("status") == "resolved" and r.get("payouts"):
        pay = r["payouts"][oi] / 1e6
    g = None
    if m and m.get("closed") and m.get("umaResolutionStatus") == "resolved":
        try:
            g = float(json.loads(m["outcomePrices"])[oi])
        except (KeyError, ValueError, IndexError, TypeError):
            g = None
        if g not in (0.0, 0.5, 1.0):
            g = None
    if pay is not None and g is not None and abs(pay - g) > 1e-6:
        return None, f"resolution mismatch payouts {pay} vs gamma {g}"
    pay = pay if pay is not None else g
    return (pay, f"ตัดสินผลแล้ว จ่าย {pay:g} ต่อหุ้น") if pay is not None else (None, None)


def cmd_status():
    for f in (COPY, TWIN):
        s = load(f)
        sells = [x for x in s["log"] if x["kind"] == "sell"]
        skips = sum(x["kind"] == "skip" for x in s["log"])
        avg = sum(x["pnl"] / (x["usd"] - x["pnl"]) for x in sells) / len(sells) if sells else 0
        print(f"{Path(f).name[6:-5]:<10} {value(s) / s['start_usd'] - 1:+.1%}  เปิด {len(s['pos'])}  ปิด {len(sells)} (ชนะ {sum(x['pnl'] > 0 for x in sells)})"
              f"  เฉลี่ยต่อไม้ {avg:+.1%}  ข้าม {skips}")


def cmd_pick():
    """The wallet rule in the notes file: top 1000 all-time PnL -> >= 1000 distinct markets, joined >= 365 days ago,
    positive PnL this month, a taker trade in the last 7 days; keep the 8 highest all-time PnL."""
    now = time.time()
    lb = get(f"{DATA}/v2/leaderboard", dict(time_period="all", sort_by="PNL", limit=1000))["data"]

    def stats(r):
        try:
            return r, get(f"{DATA}/v2/user-stats", dict(user=r["user_id"]))["data"]
        except Exception:
            return r, None
    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(stats, lb))
    ok = [(r, st) for r, st in rows if st and (st.get("trades") or 0) >= 1000 and (st.get("join_date") or now) <= now - 365 * 86400]
    print(f"top {len(lb)} -> {len(ok)} with >= 1000 markets and >= 365 days", file=sys.stderr)
    out = []
    for r, st in ok:
        try:
            mo = get(f"{DATA}/v2/leaderboard", dict(user=r["user_id"], time_period="month"))["data"] or {}
            last = get(f"{DATA}/v2/trades", dict(user=r["user_id"], limit=1))["data"]
        except Exception:
            continue
        lt = int(last[0]["timestamp"]) if last else 0
        if (mo.get("pnl") or 0) > 0 and now - lt <= 7 * 86400:
            out.append((r, st, mo.get("pnl"), lt))
        if len(out) >= 8:
            break
    for r, st, mp, lt in out:
        print(f"- {r['user_id']} | {r.get('user_name')} | rank {r['rank']} all-time PnL ${r['pnl']:,.0f}, volume ${r['volume']:,.0f}, "
              f"{st['trades']:,} markets, joined {datetime.fromtimestamp(st['join_date'], TZ):%Y-%m-%d}, month PnL ${mp:,.0f}, "
              f"last trade {datetime.fromtimestamp(lt, TZ):%Y-%m-%d %H:%M}")


if __name__ == "__main__":
    cmds = {"run": cmd_run, "status": cmd_status, "pick": cmd_pick}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]]()
