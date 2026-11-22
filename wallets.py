#!/usr/bin/env python3
"""Paper account "copy 10 smart wallets via Helius" (13 Nov 2026), fake money only.
Same 10 wallets and filters as the Grok Bot routine (research_notes/grokbot-wallets-2026-11-13.md), but polled
every 2 minutes straight from Solana RPC, so we copy within minutes instead of up to 30 and use no Grok quota.
Cost: getSignaturesForAddress and getTransaction are 1 Helius credit each (~230k of the free 1M a month).

  python3 wallets.py init 500   # also sets each wallet's cursor to now (no back-filling)
  python3 wallets.py poll       # new buys -> paper buys (agents.py sizing and exits)
  python3 wallets.py run        # exits
  python3 wallets.py status
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import agents  # noqa: E402

HERE = Path(__file__).parent
# WALLET_LIST=fomo runs a second, separate account on the Fomo 30-day leaderboard wallets (22 Nov); default is the Grok list.
LIST = {"grok": ("state_wallets.json", "grokbot-wallets-2026-11-13.md", "ตามกระเป๋า 10 ใบ ผ่าน Helius"),
        "fomo": ("state_wallets_fomo.json", "fomo-wallets-2026-11-22.md", "ตามกระเป๋าอันดับต้น Fomo 30 วัน 10 ใบ ผ่าน Helius"),
        # savipww's copy rules (X, 16 Nov): leaders green on 24h and 7d, sell when the leader sells, own stop -25%, half size
        "fomo_mirror": ("state_wallets_fomo_mirror.json", "fomo-mirror-wallets-2026-11-22.md",
                        "ตามกระเป๋า Fomo กำไรทั้ง 24 ชม. และ 7 วัน ขายตามเจ้าของ stop -25% ไม้ครึ่ง")}[os.environ.get("WALLET_LIST", "grok")]
MIRROR = LIST[0] == "state_wallets_fomo_mirror.json"
if MIRROR:                      # exits: the leader's sell, else our own -25% stop; no trailing, 72 h safety cap
    agents.STOP, agents.TRAIL_ON, agents.MAX_HOLD_H, agents.PER_TRADE = -0.25, 9.0, 72, 0.10
agents.STATE = HERE / LIST[0]
WALLETS = re.findall(r"^- ([1-9A-HJ-NP-Za-km-z]{32,44}) \|", (HERE / "research_notes" / LIST[1]).read_text(), re.M)
QUOTE = {"So11111111111111111111111111111111111111112",   # wSOL
         "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",   # USDC
         "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCZ8BenwNYB"}   # USDT
MIN_USD, MIN_LIQ, STALE_MIN, NO_REPEAT_H = 200, 15_000, 15, 24


def rpc(method, params):
    key = os.environ.get("HELIUS_API_KEY")
    if not key:
        sys.exit("HELIUS_API_KEY missing (PaperTrade/.env)")
    req = urllib.request.Request(f"https://mainnet.helius-rpc.com/?api-key={key}",
                                 data=json.dumps(dict(jsonrpc="2.0", id=1, method=method, params=params)).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    if "error" in d:
        raise RuntimeError(str(d["error"])[:120])
    return d["result"]


def sol_usd():
    """SOL in USD via Binance TH (api.binance.com answers 451 to US cloud hosts such as GitHub Actions)."""
    th = lambda sym: float(json.load(urllib.request.urlopen(f"https://api.binance.th/api/v1/ticker/price?symbol={sym}", timeout=10))["price"])
    return th("SOLTHB") / th("USDTTHB")


def buys_in(tx, wallet, sol_price):
    """Token buys by `wallet` in one parsed transaction: [(mint, usd_spent)]. A buy = a non-quote token balance rises
    while SOL, wSOL, USDC or USDT falls."""
    meta = tx.get("meta") or {}
    if meta.get("err"):
        return []
    delta = {}
    for side, sign in (("preTokenBalances", -1), ("postTokenBalances", 1)):
        for b in meta.get(side) or []:
            if b.get("owner") == wallet:
                amt = float((b.get("uiTokenAmount") or {}).get("uiAmount") or 0)
                delta[b["mint"]] = delta.get(b["mint"], 0) + sign * amt
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
    sol = 0.0
    if wallet in keys:
        i = keys.index(wallet)
        sol = (meta["postBalances"][i] - meta["preBalances"][i]) / 1e9
    spent = (-sol - delta.get("So11111111111111111111111111111111111111112", 0)) * sol_price \
        - delta.get("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 0) - delta.get("Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCZ8BenwNYB", 0)
    got = [m for m, d in delta.items() if d > 0 and m not in QUOTE]
    return [(m, spent) for m in got] if spent > 0 else []


def sold_in(tx, wallet):
    """Mints whose balance the wallet cut in this transaction (a sell or a transfer out): the mirror account's exit signal."""
    meta = tx.get("meta") or {}
    if meta.get("err"):
        return []
    delta = {}
    for side, sign in (("preTokenBalances", -1), ("postTokenBalances", 1)):
        for b in meta.get(side) or []:
            if b.get("owner") == wallet:
                delta[b["mint"]] = delta.get(b["mint"], 0) + sign * float((b.get("uiTokenAmount") or {}).get("uiAmount") or 0)
    return [m for m, d in delta.items() if d < 0 and m not in QUOTE]


def mirror_sell(s, mint, w):
    q = s["pos"].get(mint)
    if not q or q.get("wallet") != w[:6]:
        return
    p = agents.grok.pair(mint)
    if not p or not p.get("priceUsd"):
        return                                  # no price now: the stop and the 72 h cap still close it
    price = min(float(p["priceUsd"]), q["last"] * 1.5)   # one bad pool print must not book a moonshot
    got = q["qty"] * price * (1 - agents.SLIP) * (1 - agents.FEE)
    s["cash"] += got
    agents.log(s, "sell", mint=mint, sym=q["sym"], price=price, entry=q["entry"], usd=round(got, 4), pnl=round(got - q["cost"], 4),
               why=f"ขายตามเจ้าของกระเป๋า {price / q['entry'] - 1:+.1%}", stop_set=agents.STOP, cost_side=agents.FEE + agents.SLIP)
    del s["pos"][mint]
    print(f"  MIRROR SELL {q['sym']} pnl ${got - q['cost']:+.3f}")


def cmd_init(thb):
    agents.cmd_init(thb)
    s = agents.load()
    s["label"] = LIST[2]
    s["cursor"] = {w: (rpc("getSignaturesForAddress", [w, {"limit": 1}]) or [{}])[0].get("signature") for w in WALLETS}
    agents.save(s)
    print(f"cursor set for {len(WALLETS)} wallets")


def cmd_poll():
    s = agents.load()
    cur, price = s.setdefault("cursor", {}), sol_usd()
    cut = time.time() - NO_REPEAT_H * 3600
    for w in WALLETS:
        try:
            opts = {"limit": 25, **({"until": cur[w]} if cur.get(w) else {})}
            sigs = [x for x in rpc("getSignaturesForAddress", [w, opts]) if not x.get("err")]
        except Exception as e:
            print(f"{w[:6]}: {e}")
            continue
        if sigs:
            cur[w] = sigs[0]["signature"]
        for x in reversed(sigs):                      # oldest first
            if (time.time() - (x.get("blockTime") or 0)) / 60 > STALE_MIN:
                continue
            try:
                tx = rpc("getTransaction", [x["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
            except Exception as e:
                print(f"{w[:6]} tx: {e}")
                continue
            if MIRROR:
                for mint in sold_in(tx or {}, w):
                    mirror_sell(s, mint, w)
            for mint, usd in buys_in(tx or {}, w, price):
                if usd < MIN_USD:
                    continue
                recent = any(y["kind"] == "buy" and y.get("mint") == mint and
                             datetime.fromisoformat(y["t"]).timestamp() > cut for y in s["log"])   # tz-aware: runs on UTC hosts too
                p = agents.grok.pair(mint)
                liq = ((p or {}).get("liquidity") or {}).get("usd", 0)
                sym = ((p or {}).get("baseToken") or {}).get("symbol", mint[:6])
                lag = (time.time() - x["blockTime"]) / 60
                if recent or liq < MIN_LIQ:
                    agents.log(s, "skip", mint=mint, sym=sym, wallet=w[:6], usd=round(usd), why="repeat" if recent else f"liq ${liq:,.0f}")
                    continue
                why = agents.paper_buy(s, mint, sym, wallet=w[:6], wallet_usd=round(usd), lag_min=round(lag, 1))
                print(f"{sym} by {w[:6]} ${usd:,.0f} lag {lag:.1f}m: {'bought' if why is None else why}")
    agents.save(s)


if __name__ == "__main__":
    a = sys.argv[1:]
    cmds = {"init": lambda: cmd_init(a[1]), "poll": cmd_poll, "run": agents.cmd_run, "status": agents.cmd_status}
    if not a or a[0] not in cmds:
        sys.exit(__doc__)
    cmds[a[0]]()
