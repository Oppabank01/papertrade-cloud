#!/usr/bin/env python3
"""Paper experiment "fast multi-agent" (13 Nov 2026): a copy of the X-post recipe
(@crbpite8 / @x_insider4: SCOUT -> SMART$ -> GUARD -> DEBATE -> EXEC, stop -8%) with fake money only.
Separate from grok.py v2 so neither result contaminates the other. Rules: RULES_AGENTS.md.

  python3 agents.py init 300      # paper THB
  python3 agents.py scan          # one GMGN 5m ranking call -> seats -> paper buys
  python3 agents.py run           # exits from DexScreener prices (cheap, run every 2 min)
  python3 agents.py status
No wallet, no keys beyond GMGN's read-only demo key, no orders anywhere.
"""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import grok  # noqa: E402  reuse get/gm/usdthb/now and the laya loader

STATE = Path(__file__).with_name("state_agents.json")
FEE, SLIP = 0.01, 0.02                  # per side; small pools slip more than v2's 1%
PER_TRADE, MAX_POS = 0.20, 4
STOP, TRAIL_ON, TRAIL, MAX_HOLD_H = -0.08, 0.15, 0.15, 3
TP_ALL = None                           # recipes.py 'grad' sells everything at a fixed target
MIN_LIQ, MIN_AGE_MIN = 15_000, 15
DEBATE_BUY = 0.60
COOLDOWN_H = 24                         # added 13 Nov 01:40 with the 500 THB restart, before any trade
DEBATE_Q = {
    "bull": {"type": "noul", "instructions": "The bullish case (smart wallets accumulating, buyers outnumber sellers, price rising) is stronger than the bearish case."},
    "bear": {"type": "noul", "instructions": "This looks like a pump, bundle or exit-liquidity setup where early holders are about to sell."},
    "action": {"type": "choice", "instructions": "Decide on a fast paper trade held up to 3 hours with a -8% stop.",
               "criteria": {"buy": "momentum with real buyers, enter now", "pass": "no"}},
}


def load():
    if not STATE.exists():
        sys.exit("ยังไม่มีบัญชี: python3 agents.py init 300")
    return json.loads(STATE.read_text())


def save(s):
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1))


def log(s, kind, **kw):
    s["log"].append(dict(t=grok.now().isoformat(timespec="seconds"), kind=kind, **kw))


def equity(s):
    return s["cash"] + sum(q["qty"] * q["last"] for q in s["pos"].values())


def seats(t):
    """Deterministic seats. Returns list of failures (empty = pass)."""
    f = []
    age_min = (time.time() - (t.get("open_timestamp") or time.time())) / 60
    liq = float(t.get("liquidity") or 0)
    # SCOUT
    if liq < MIN_LIQ:
        f.append(f"scout: liq ${liq:,.0f}")
    if age_min < MIN_AGE_MIN:
        f.append(f"scout: age {age_min:.0f}m")
    # SMART$: at least two smart wallets and one known wallet in, more buys than sells, price going up
    if (t.get("smart_degen_count") or 0) < 2 or (t.get("renowned_count") or 0) < 1:
        f.append(f"smart: smart {t.get('smart_degen_count')} kol {t.get('renowned_count')}")
    if (t.get("buys") or 0) <= (t.get("sells") or 0):
        f.append("smart: sells >= buys")
    ch5 = float(t.get("price_change_percent5m") or 0)
    if not 0 < ch5 <= 100:
        f.append(f"smart: 5m {ch5:+.0f}%")
    # GUARD: the post's 'checks risk', kept loose on purpose (this is the post's recipe, not v2)
    if t.get("is_honeypot") or not t.get("renounced_mint") or not t.get("renounced_freeze_account"):
        f.append("guard: honeypot/mint/freeze")
    if float(t.get("rug_ratio") or 0) >= 0.5 or float(t.get("top_10_holder_rate") or 0) >= 0.5 or float(t.get("sell_tax") or 0) > 0:
        f.append("guard: rug/top10/tax")
    return f


def debate(t):
    """DEBATE seat: local laya model answers closed questions on the ranking facts (stand-in for Grok)."""
    try:
        if grok._laya is None:
            import laya
            grok._laya = laya.load()
        facts = {k: t.get(k, "missing") for k in ("symbol", "liquidity", "market_cap", "smart_degen_count", "renowned_count",
                                                   "buys", "sells", "volume", "price_change_percent5m", "price_change_percent1h",
                                                   "holder_count", "top_10_holder_rate", "bundler_rate", "sniper_count")}
        facts["age_minutes"] = round((time.time() - (t.get("open_timestamp") or time.time())) / 60)
        a = grok._laya.predict(facts, DEBATE_Q)["answers"]
        v = dict(buy=a["action"]["probabilities"]["buy"], bull=a["bull"]["noul"], bear=a["bear"]["noul"])
        return v["buy"] >= DEBATE_BUY and v["bull"] > v["bear"], v
    except Exception as e:
        return False, {"error": str(e)[:80]}


def cmd_init(thb):
    if STATE.exists():
        sys.exit("มีบัญชีอยู่แล้ว")
    usd = float(thb) / grok.usdthb()
    s = dict(start_thb=float(thb), start_usd=usd, cash=usd, pos={}, log=[])
    log(s, "init", thb=float(thb))
    save(s)
    print(f"บัญชีเร็วแบบหลายเอเจนต์ {thb} บาท = ${usd:.2f}")


def cmd_scan():
    s = load()
    try:
        r = grok.gm("/v1/market/rank", chain="sol", interval="5m", limit=50, order_by="volume", direction="desc")
    except Exception as e:
        print(f"scan skipped: {str(e)[:50]}")
        return
    rank = (r.get("data") or r).get("rank", [])
    (Path(__file__).with_name("data") / "rank5m_latest.json").write_text(json.dumps(dict(t=time.time(), rank=rank)))
    passed = [t for t in rank if not seats(t) and t["address"] not in s["pos"]]
    cut = (grok.now() - timedelta(hours=COOLDOWN_H)).isoformat(timespec="seconds")
    recent = {x.get("mint") for x in s["log"] if x["kind"] == "sell" and x["t"] >= cut}
    passed = [t for t in passed if t["address"] not in recent]   # skip before spending a laya call
    print(f"5m rank {len(rank)}, passed seats {len(passed)}")
    for t in passed:
        if len(s["pos"]) >= MAX_POS:
            break
        ok, v = debate(t)
        log(s, "debate", mint=t["address"], sym=t.get("symbol"), ok=ok, bundler=t.get("bundler_rate"), **v)
        print(f"  {t.get('symbol')}: debate {'buy' if ok else 'pass'} {v}")
        if not ok:
            continue
        if paper_buy(s, t["address"], t.get("symbol"), smart=t.get("smart_degen_count"), kol=t.get("renowned_count"),
                     bundler=t.get("bundler_rate")) == "no cash":
            break
    save(s)


def paper_buy(s, mint, sym, **meta):
    """EXEC seat: fake buy at the live DexScreener price (not a stale snapshot). Returns why it did not buy, or None."""
    if mint in s["pos"] or len(s["pos"]) >= MAX_POS:
        return "held or full"
    cut = (grok.now() - timedelta(hours=COOLDOWN_H)).isoformat(timespec="seconds")
    if any(x["kind"] == "sell" and x.get("mint") == mint and x["t"] >= cut for x in s["log"]):
        return f"sold within {COOLDOWN_H}h"     # the post's own rule: never repeat a token within 24h
    p = grok.pair(mint)
    if not p or not p.get("priceUsd"):
        return "no pool"
    price = float(p["priceUsd"])
    spend = min(equity(s) * PER_TRADE, s["cash"])
    if spend < 0.05:
        return "no cash"
    s["cash"] -= spend
    s["pos"][mint] = dict(sym=sym, qty=spend * (1 - FEE) * (1 - SLIP) / price, entry=price, last=price, peak=price, cost=spend,
                          opened=grok.now().isoformat(timespec="seconds"), **meta)
    log(s, "buy", mint=mint, sym=sym, price=price, usd=round(spend, 4))
    print(f"  BUY {sym} ${spend:.2f} at {price:.8g}")
    return None


def cmd_run():
    s = load()
    if s["pos"]:
        pools = {}
        try:
            for p in grok.get(grok.DEX + ",".join(s["pos"])):
                m = (p.get("baseToken") or {}).get("address")
                if p.get("chainId") == "solana" and p.get("priceUsd") and (p.get("liquidity") or {}).get("usd", 0) >= \
                        (pools.get(m, {}).get("liquidity") or {}).get("usd", -1):
                    pools[m] = p
        except Exception as e:
            print(f"price fetch failed: {str(e)[:50]}")
            return
        for m, q in list(s["pos"].items()):
            if m not in pools:
                q["miss"] = q.get("miss", 0) + 1
                if q["miss"] < 2:
                    continue
                price, why = 0.0, "pool หาย ถือว่า rug"
            else:
                price = float(pools[m]["priceUsd"])
                q.update(last=price, peak=max(q["peak"], price), miss=0)
                chg, held = price / q["entry"] - 1, (grok.now() - datetime.fromisoformat(q["opened"])).total_seconds() / 3600
                why = (f"stop {chg:+.1%}" if chg <= STOP else
                       f"ถึงเป้า {chg:+.1%}" if TP_ALL is not None and chg >= TP_ALL else
                       f"trailing จากยอด {q['peak'] / q['entry'] - 1:+.0%} ({chg:+.1%})" if q["peak"] / q["entry"] - 1 >= TRAIL_ON and price <= q["peak"] * (1 - TRAIL) else
                       f"ครบ {MAX_HOLD_H} ชม. ({chg:+.1%})" if held >= MAX_HOLD_H else None)
            if why:
                got = q["qty"] * price * (1 - SLIP) * (1 - FEE)
                s["cash"] += got
                log(s, "sell", mint=m, sym=q["sym"], price=price, usd=round(got, 4), pnl=round(got - q["cost"], 4), why=why,
                    smart=q.get("smart"), bundler=q.get("bundler"))
                del s["pos"][m]
                print(f"  SELL {q['sym']} {why} pnl ${got - q['cost']:+.3f}")
    save(s)


def cmd_status():
    s = load()
    eq, rate = equity(s), grok.usdthb()
    sells = [x for x in s["log"] if x["kind"] == "sell"]
    print(f"{s.get('label', 'พอร์ตเร็วหลายเอเจนต์')} ${eq:.2f} = {eq * rate:,.0f} บาท ({eq / s['start_usd'] - 1:+.1%}) ถืออยู่ {len(s['pos'])} ตัว")
    for q in s["pos"].values():
        print(f"  {q['sym']}: {q['last'] / q['entry'] - 1:+.1%} เปิด {q['opened'][11:16]}")
    if sells:
        pnl = [x["pnl"] for x in sells]
        print(f"ปิดแล้ว {len(pnl)} ไม้ ชนะ {sum(p > 0 for p in pnl)} ({sum(p > 0 for p in pnl) / len(pnl):.0%}) "
              f"รวม ${sum(pnl):+.3f} ไม้ดีสุด ${max(pnl):+.3f} แย่สุด ${min(pnl):+.3f}")
    print("เทียบโพสต์: $88 เป็น $2,673 ใน 10 ชม. 121 ไม้ ชนะ 80%")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmds = {"init": lambda: cmd_init(a[1]), "scan": cmd_scan, "run": cmd_run, "status": cmd_status}
    if not a or a[0] not in cmds:
        sys.exit(__doc__)
    cmds[a[0]]()
