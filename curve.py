#!/usr/bin/env python3
"""Paper account "copy the 10 wallets on pump.fun bonding curves" (14 Nov 2026), fake money only.
Child of wallets.py with ONE change. wallets.py skips tokens still on the pump.fun bonding curve because DexScreener
shows no liquidity for them (59 of its first 95 skips). This account takes exactly those skipped buys, reads the curve
account on chain (Helius getMultipleAccounts, 1 credit a call) and buys only when the curve really holds MIN_SOL or more.
Detection costs nothing extra: it reads the skips wallets.py logged in state_wallets.json during this same run.
Sizing, cooldown and exits are agents.py's, the same as wallets.py. Costs per side: pump.fun fee 1.25%, slippage 2%,
0.0005 SOL network/priority fee, and amounts come from the curve's own constant-product math so our size moves the price.
Rules and pass/die criteria: RULES_AGENTS.md.

  python3 curve.py init 500
  python3 curve.py run       # exits for held tokens, then buys from this run's fresh wallets.py skips
  python3 curve.py status
"""
import base64
import hashlib
import json
import struct
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import wallets  # noqa: E402  (imports agents and grok; rpc, sol_usd)

agents, grok = wallets.agents, wallets.agents.grok
HERE = Path(__file__).parent
agents.STATE = HERE / "state_curve.json"      # wallets.py pointed it at state_wallets.json on import
SRC = HERE / "state_wallets.json"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WSOL = "So11111111111111111111111111111111111111112"
DISC = hashlib.sha256(b"account:BondingCurve").digest()[:8]
FEE, SLIP, TX_SOL = 0.0125, 0.02, 0.0005
MIN_SOL, FRESH_MIN = 5, 10                    # real SOL in the curve at our buy; ignore skips older than 10 min
DIE_N, PASS_N = 20, 50


def parse(v):
    """getMultipleAccounts value -> {vt, vs, rt, rs, done} in raw units, or None if it is not a pump.fun curve.
    Curves start from different virtual reserves (30 SOL and ~202 SOL both seen live), so the quote is only trusted
    once Jupiter agrees within 1% at the buy."""
    if not v or v.get("owner") != PUMP:
        return None
    raw = base64.b64decode(v["data"][0])
    if len(raw) < 49 or raw[:8] != DISC:
        return None
    vt, vs, rt, rs, _ = struct.unpack_from("<5Q", raw, 8)
    if not (rs <= vs and rt <= vt and vt):
        return None
    return dict(vt=vt, vs=vs, rt=rt, rs=rs, done=bool(raw[48]))


def spot(c, sol):
    """USD per token (6 decimals) from virtual reserves."""
    return c["vs"] / c["vt"] / 1000 * sol


def buy_qty(c, usd, sol):
    """Tokens received for `usd`, after fee, network fee and slippage. None if the curve cannot fill it."""
    lam = (usd * (1 - FEE) / sol - TX_SOL) * 1e9
    if lam <= 0:
        return None
    out = c["vt"] - c["vs"] * c["vt"] / (c["vs"] + lam)
    return None if out > c["rt"] else out / 1e6 * (1 - SLIP)


def sell_usd(c, qty, sol):
    """USD received for selling `qty` tokens back into the curve; never more SOL than the curve really holds."""
    lam = min(c["vs"] - c["vs"] * c["vt"] / (c["vt"] + qty * 1e6), c["rs"])
    return max(0.0, (lam / 1e9 * (1 - SLIP) * (1 - FEE) - TX_SOL) * sol)


def pool_sell_usd(price, qty, sol):
    return max(0.0, qty * price * (1 - SLIP) * (1 - FEE) - TX_SOL * sol)


def ts(t):
    return datetime.fromisoformat(t).timestamp()


def cmd_init(thb):
    agents.cmd_init(thb)
    s = agents.load()
    s.update(label="ตามกระเป๋า 10 ใบ บน bonding curve", seen_t=grok.now().isoformat(timespec="seconds"))
    agents.save(s)


def exit_why(q, price):
    chg = price / q["entry"] - 1
    held = (grok.now() - datetime.fromisoformat(q["opened"])).total_seconds() / 3600
    return (f"stop {chg:+.1%}" if chg <= agents.STOP else
            f"trailing จากยอด {q['peak'] / q['entry'] - 1:+.0%} ({chg:+.1%})"
            if q["peak"] / q["entry"] - 1 >= agents.TRAIL_ON and price <= q["peak"] * (1 - agents.TRAIL) else
            f"ครบ {agents.MAX_HOLD_H} ชม. ({chg:+.1%})" if held >= agents.MAX_HOLD_H else None)


def cmd_run():
    s = agents.load()
    src = [x for x in json.loads(SRC.read_text())["log"] if x["kind"] == "skip"]
    seen = ts(s["seen_t"])
    cands = {}
    for x in src:                                     # wallets.py skips for low liquidity, newer than the last run
        if x["why"].startswith("liq") and ts(x["t"]) > seen and time.time() - ts(x["t"]) <= FRESH_MIN * 60:
            cands.setdefault(x["mint"], x)
    if src:
        s["seen_t"] = max([s["seen_t"]] + [x["t"] for x in src], key=ts)
    if not s["pos"] and not cands:
        agents.save(s)
        return
    try:                                              # data that fails is a fail: no guessed prices this run
        sol = wallets.sol_usd()
        pairs, dexp = {}, {}
        for i in range(0, len(cands), 30):
            for p in grok.get(grok.DEX + ",".join(list(cands)[i:i + 30])):
                m = (p.get("baseToken") or {}).get("address")
                if p.get("dexId") == "pumpfun" and (p.get("quoteToken") or {}).get("address") == WSOL:   # some curves trade against BTC or other tokens
                    pairs[m] = p["pairAddress"]
                    dexp[m] = float(p["priceUsd"]) if p.get("priceUsd") else None
        addrs = [q["curve"] for q in s["pos"].values()] + [pairs[m] for m in cands if m in pairs]
        vals = wallets.rpc("getMultipleAccounts", [addrs, {"encoding": "base64"}])["value"] if addrs else []
        curves = dict(zip(addrs, map(parse, vals)))
    except Exception as e:
        print(f"curve: data fetch failed, nothing done: {str(e)[:80]}")
        agents.save(s)
        return
    jp = agents.jup_prices(list(s["pos"]) + list(cands))

    for m, q in list(s["pos"].items()):
        c = curves.get(q["curve"])
        if c and c["done"]:                           # graduated to a real pool: price it there like wallets.py would
            p = grok.pair(m)
            price = float(p["priceUsd"]) if p and p.get("priceUsd") else None
            value = None if price is None else lambda pr: pool_sell_usd(pr, q["qty"], sol)
        elif c:
            price, value = spot(c, sol), (lambda pr, c=c: sell_usd(c, q["qty"], sol) * pr / spot(c, sol))
        else:
            price = None
        if price is None:
            q["miss"] = q.get("miss", 0) + 1
            if q["miss"] < agents.MISS_N:
                continue
            got, why, price = 0.0, "curve/pool หาย ถือว่า rug", 0.0
        else:
            q["miss"] = 0
            j = jp.get(m)
            if j and abs(price / j - 1) > agents.PRICE_GAP:     # sources disagree: this round counts at the lower one
                q["gap"] = q.get("gap", 0) + 1
                price = min(price, j)
                if q["gap"] >= agents.GAP_HALT_N and not s.get("halted"):
                    s["halted"] = f"ราคา {q['sym']} curve กับ Jupiter ต่างกันเกิน {agents.PRICE_GAP:.0%} ติดกัน {q['gap']} รอบ"
                    print(f"  HALT {s['halted']}")
            else:
                q["gap"] = 0
            q.update(last=price, peak=max(q["peak"], price))
            why = exit_why(q, price)
            got = value(price) if why else 0.0
        if why:
            s["cash"] += got
            agents.log(s, "sell", mint=m, sym=q["sym"], price=price, entry=q["entry"], usd=round(got, 4), pnl=round(got - q["cost"], 4),
                       why=why, stop_set=agents.STOP, cost_side=FEE + SLIP, graduated=bool(c and c["done"]))
            del s["pos"][m]
            print(f"  SELL {q['sym']} {why} pnl ${got - q['cost']:+.3f}")

    cut = grok.now() - timedelta(hours=agents.COOLDOWN_H)
    for m, x in cands.items():
        c = curves.get(pairs.get(m))
        j = jp.get(m) or dexp.get(m)                  # second source: Jupiter, else DexScreener (Jupiter lacks some fresh curves)
        why = ("account halted" if s.get("halted") else
               "held or full" if m in s["pos"] or len(s["pos"]) >= agents.MAX_POS else
               f"sold within {agents.COOLDOWN_H}h" if any(y["kind"] == "sell" and y.get("mint") == m and ts(y["t"]) >= cut.timestamp() for y in s["log"]) else
               "not on a SOL pump.fun curve" if m not in pairs else
               "unknown curve account" if not c else
               "graduated" if c["done"] else
               f"curve {c['rs'] / 1e9:.2f} SOL" if c["rs"] / 1e9 < MIN_SOL else
               "price unverified" if not j else
               f"price mismatch {spot(c, sol) / j - 1:+.1%}" if abs(spot(c, sol) / j - 1) > agents.PRICE_GAP else None)
        spend = min(agents.equity(s) * agents.PER_TRADE, s["cash"])
        qty = None if why else buy_qty(c, spend, sol)
        if not why and not qty:
            why = "too small or curve cannot fill"
        if why:
            agents.log(s, "skip", mint=m, sym=x.get("sym"), wallet=x.get("wallet"), why=why)
            continue
        price = spot(c, sol)
        s["cash"] -= spend
        lag = (time.time() - ts(x["t"])) / 60
        s["pos"][m] = dict(sym=x.get("sym", m[:6]), qty=qty, entry=price, last=price, peak=price, cost=spend, curve=pairs[m],
                           opened=grok.now().isoformat(timespec="seconds"), wallet=x.get("wallet"))
        agents.log(s, "buy", mint=m, sym=x.get("sym"), price=price, jup=j, usd=round(spend, 4), curve_sol=round(c["rs"] / 1e9, 2),
                   wallet=x.get("wallet"), wallet_usd=x.get("usd"), lag_min_after_skip=round(lag, 1), stop_set=agents.STOP, cost_side=FEE + SLIP)
        print(f"  BUY {x.get('sym')} ${spend:.2f} at {price:.8g} curve {c['rs'] / 1e9:.1f} SOL")
    agents.save(s)


def cmd_status():
    s = agents.load()
    eq, rate = agents.equity(s), grok.usdthb()
    sells = [x["pnl"] for x in s["log"] if x["kind"] == "sell"]
    skips = [x["why"].split(" ")[0] for x in s["log"] if x["kind"] == "skip"]
    print(f"{s['label']} ${eq:.2f} = {eq * rate:,.0f} บาท ({eq / s['start_usd'] - 1:+.1%}) ถืออยู่ {len(s['pos'])} ตัว"
          + (f" [halted: {s['halted']}]" if s.get("halted") else ""))
    if sells:
        verdict = ("ตาย" if len(sells) >= DIE_N and sum(sells) < 0 else
                   "ผ่าน (ต้องชนะ rand ด้วย)" if len(sells) >= PASS_N and sum(sells) > 0 else "ยังไม่ครบ")
        print(f"ปิดแล้ว {len(sells)} ไม้ ชนะ {sum(p > 0 for p in sells)} รวม ${sum(sells):+.3f} ไม้ดีสุด ${max(sells):+.3f} แย่สุด ${min(sells):+.3f} สถานะ {verdict}")
    if skips:
        print("ข้าม: " + ", ".join(f"{k} {skips.count(k)}" for k in sorted(set(skips), key=skips.count, reverse=True)))


if __name__ == "__main__":
    a = sys.argv[1:]
    cmds = {"init": lambda: cmd_init(a[1]), "run": cmd_run, "status": cmd_status}
    if not a or a[0] not in cmds:
        sys.exit(__doc__)
    cmds[a[0]]()
