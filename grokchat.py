#!/usr/bin/env python3
"""Mac-only helper for the Grok chat accounts (g_boan_chat, g_gmgn_chat). Paper money only.
  python3 grokchat.py prompt OUT.txt      fresh GMGN ranking -> prompt to paste into Grok chat (x.com/i/grok)
  python3 grokchat.py orders ANSWER.json  Grok's JSON reply -> data/orders_<name>.json (cloud buys within 30 min)"""
import json
import sys
import time
from pathlib import Path

import grok
import zoo

HERE = Path(__file__).parent
SNAP = HERE / "data" / "grokchat_last_rank.json"   # mints Grok may pick from; anything else is ignored
DESKS = (("A", "g_boan_chat"), ("B", "g_gmgn_chat"))


def row(t):
    f = lambda k: zoo.f(t, k)
    return (f"{t.get('symbol')} | {t['address']} | age {zoo.age_h(t):.1f}h | liq ${f('liquidity'):,.0f} | mcap ${f('market_cap'):,.0f} | "
            f"vol5m ${f('volume'):,.0f} | 5m {f('price_change_percent5m'):+.0f}% 1h {f('price_change_percent1h'):+.0f}% | "
            f"holders {f('holder_count'):.0f} | top10 {f('top_10_holder_rate') * 100:.0f}% | smart {f('smart_degen_count'):.0f} "
            f"KOL {f('renowned_count'):.0f} | bundler {f('bundler_rate') * 100:.0f}% | rug {f('rug_ratio'):.2f} | graduated {t.get('launchpad_status')}")


def cmd_prompt(out):
    r = grok.gm("/v1/market/rank", chain="sol", interval="5m", limit=50, order_by="volume", direction="desc")
    rank = (r.get("data") or r).get("rank", [])
    SNAP.write_text(json.dumps([t["address"] for t in rank]))
    a = [t for t in rank if zoo.ok(t) and zoo.age_h(t) <= 6]
    b = [t for t in rank if zoo.ok(t) and (zoo.f(t, "smart_degen_count") >= 1 or zoo.f(t, "renowned_count") >= 1)]
    nl = "\n"
    Path(out).write_text(f"""Paper trading only (fake money, no wallet). I run two simulated Solana memecoin desks and you make the buy decisions. Snapshot from GMGN 5m volume ranking, taken just now.

DESK A (Scanner, Rug Check, Momentum, Exit): sweep new pools. Check liquidity, holders, top-10 concentration, volume and fresh buyers. Rug Check: kill anything shady. Momentum: enter only on a confirmed move. Sizing: small fast trades (0.10 of equity) on routine setups, one bigger position (0.35) only on the best setup of the day. Exits are fixed by my script: stop -15%, sell half at +30%, trail 15%, max hold 4h15m. Saying no is fine.
Candidates (age 6h or less):
{nl.join(map(row, a))}

DESK B (GMGN data + you make the final call): for each coin answer BUY or SKIP using smart-money and KOL presence, holder structure, bundler/rug signals, and anything you can see on X right now about the coin. Size 0.10 each, 0.25 only if exceptional. Same fixed exits.
Candidates:
{nl.join(map(row, b))}

Reply with ONLY this JSON, no other text:
{{"A":[{{"mint":"...","sym":"...","size":0.10,"why":"short reason"}}],"B":[{{"mint":"...","sym":"...","size":0.10,"why":"short reason"}}]}}
Empty lists are allowed.""")
    print(f"prompt: {len(a)} desk A, {len(b)} desk B -> {out}")


def cmd_orders(path, now=None):
    ans, ok_mints, t = json.loads(Path(path).read_text()), set(json.loads(SNAP.read_text())), now or time.time()
    for desk, name in DESKS:
        p = HERE / "data" / f"orders_{name}.json"
        old = json.loads(p.read_text()) if p.exists() else []
        new = [dict(id=f"{int(t)}-{o['mint'][:6]}", mint=o["mint"], sym=o.get("sym"), size=min(float(o["size"]), 0.35),
                    why="grok chat: " + str(o.get("why", "")), t=t) for o in ans.get(desk, []) if o.get("mint") in ok_mints]
        p.write_text(json.dumps(old + new, ensure_ascii=False, indent=0))
        print(f"{name}: {len(new)} orders ({len(ans.get(desk, [])) - len(new)} ignored: not in snapshot)")


if __name__ == "__main__":
    {"prompt": cmd_prompt, "orders": cmd_orders}[sys.argv[1]](sys.argv[2])
