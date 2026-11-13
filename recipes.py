#!/usr/bin/env python3
"""Paper accounts that copy specific X-post recipes (13 Nov 2026), fake money only.
Each recipe reads the GMGN 5m ranking that agents.py saves every scan (data/rank5m_latest.json),
so it costs no extra API calls. Same fees and slippage as agents.py.

  python3 recipes.py RECIPE init 500
  python3 recipes.py RECIPE scan     # apply the recipe to the latest ranking, paper-buy matches
  python3 recipes.py RECIPE run      # exits
  python3 recipes.py RECIPE status

Recipes (claims are the posts', unverified):
  insider  @x_insider4 13 Nov "$85 -> $2,130": new pair, volume spike, >=5 top traders in, dev <=2.8%, top-10 <=16%.
  grad     @0xNevsky 13 Nov "$75 -> $1,944": pump.fun coins that just graduated to PumpSwap, whale in, TP +35%.
           (the on-curve half of the post needs bonding-curve progress, which the ranking does not carry)
  smart4   @crbpite8 12 Nov "$120 -> $486": a whale plus 4 smart wallets in, -8% stop, small wins.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import agents  # noqa: E402

HERE = Path(__file__).parent
RANK = HERE / "data" / "rank5m_latest.json"


def age_min(t):
    return (time.time() - (t.get("open_timestamp") or time.time())) / 60


def base_guard(t):
    return (not t.get("is_honeypot") and t.get("renounced_mint") and t.get("renounced_freeze_account")
            and float(t.get("sell_tax") or 0) == 0 and float(t.get("liquidity") or 0) >= 10_000)


def up_with_buyers(t):
    return (t.get("buys") or 0) > (t.get("sells") or 0) and 0 < float(t.get("price_change_percent5m") or 0) <= 100


RECIPES = {
    "insider": dict(label="สูตร x_insider4 (คู่ใหม่ + top trader)", exits={},
                    pick=lambda t: (age_min(t) <= 60 and (t.get("smart_degen_count") or 0) >= 5
                                    and float(t.get("top_10_holder_rate") or 1) <= 0.16
                                    and float(t.get("dev_team_hold_rate") or 0) <= 0.03 and up_with_buyers(t))),
    "grad": dict(label="สูตร 0xNevsky (เพิ่งจบ bonding curve)", exits=dict(STOP=-0.15, TP_ALL=0.35),
                 pick=lambda t: (str(t.get("launchpad_status")) == "1" and t.get("migrated_pool_exchange")
                                 and age_min(t) <= 30 and (t.get("renowned_count") or 0) >= 1 and up_with_buyers(t))),
    "smart4": dict(label="สูตร crbpite8 (วาฬ + smart 4 กระเป๋า)", exits={},
                   pick=lambda t: ((t.get("smart_degen_count") or 0) >= 4 and (t.get("renowned_count") or 0) >= 1
                                   and age_min(t) >= 15 and float(t.get("liquidity") or 0) >= 15_000 and up_with_buyers(t))),
}


def setup(name):
    r = RECIPES[name]
    agents.STATE = HERE / f"state_recipe_{name}.json"
    for k, v in r["exits"].items():
        setattr(agents, k, v)
    return r


def cmd_init(name, thb):
    r = setup(name)
    agents.cmd_init(thb)
    s = agents.load()
    s["label"] = r["label"]
    agents.save(s)


def cmd_scan(name):
    r = setup(name)
    if not RANK.exists():
        return
    d = json.loads(RANK.read_text())
    s = agents.load()
    if d["t"] <= s.get("rank_t", 0):        # this ranking was already used
        return
    s["rank_t"] = d["t"]
    for t in d["rank"]:
        if base_guard(t) and r["pick"](t):
            why = agents.paper_buy(s, t["address"], t.get("symbol"), smart=t.get("smart_degen_count"), kol=t.get("renowned_count"))
            if why is None:
                print(f"{name}: bought {t.get('symbol')}")
    agents.save(s)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in RECIPES:
        sys.exit(__doc__)
    name, cmd = a[0], a[1]
    if cmd == "init":
        cmd_init(name, a[2])
    elif cmd == "scan":
        cmd_scan(name)
    elif cmd in ("run", "status"):
        setup(name)
        {"run": agents.cmd_run, "status": agents.cmd_status}[cmd]()
    else:
        sys.exit(__doc__)
