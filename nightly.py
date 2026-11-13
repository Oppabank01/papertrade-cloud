#!/usr/bin/env python3
"""Nightly sessions (fake money): each night starts again at 500 THB, trades 21:00-09:00 Bangkok, can bank a
target or stop at a loss limit, closes everything at 09:00 and logs one result per night. The posts brag about
"went to bed with $85, woke up with $2,130"; this measures how often a night actually ends green.

Entries mirror every new buy of the cloud accounts (recipes insider/grad/smart4 and the Helius wallet copier),
so profiles differ only in sizing, exits and the nightly target/stop.

  python3 nightly.py tick      # run from cloud.sh every ~5 min
  python3 nightly.py report    # nights so far, per profile
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import agents  # noqa: E402

HERE = Path(__file__).parent
SOURCES = ("state_recipe_insider.json", "state_recipe_grad.json", "state_recipe_smart4.json", "state_wallets.json")
START_THB, OPEN_H, CLOSE_H = 500, 21, 9
PROFILES = {   # target/stop are the night's equity change that ends the session early (None = ride to 09:00)
    "safe":   dict(label="คืนละรอบ แบบระวัง", PER_TRADE=0.20, MAX_POS=4, STOP=-0.08, TRAIL_ON=0.15, TRAIL=0.15, MAX_HOLD_H=3, target=None, stop=-0.20),
    "runner": dict(label="คืนละรอบ ปล่อยกำไรวิ่ง", PER_TRADE=0.40, MAX_POS=2, STOP=-0.08, TRAIL_ON=0.20, TRAIL=0.20, MAX_HOLD_H=12, target=0.50, stop=-0.30),
    "apple":  dict(label="คืนละรอบ แบบ Apple Card", PER_TRADE=0.60, MAX_POS=2, STOP=-0.18, TRAIL_ON=0.12, TRAIL=0.12, MAX_HOLD_H=12, target=1.00, stop=-0.40),
}


def night_of(now):
    """The session date a moment belongs to, or None outside 21:00-09:00."""
    if now.hour >= OPEN_H:
        return now.date().isoformat()
    if now.hour < CLOSE_H:
        return (now.date() - timedelta(days=1)).isoformat()
    return None


def use(name):
    p = PROFILES[name]
    for k in ("PER_TRADE", "MAX_POS", "STOP", "TRAIL_ON", "TRAIL", "MAX_HOLD_H"):
        setattr(agents, k, p[k])
    agents.STATE = HERE / f"state_night_{name}.json"
    return p


def source_buys():
    for f in SOURCES:
        if (HERE / f).exists():
            for x in json.loads((HERE / f).read_text())["log"]:
                if x["kind"] == "buy" and x.get("mint"):
                    yield f"{f}:{x['t']}:{x['mint']}", x


def live_prices(mints):
    out = {}
    for p in agents.grok.get(agents.grok.DEX + ",".join(mints)) if mints else []:
        m = (p.get("baseToken") or {}).get("address")
        if p.get("chainId") == "solana" and p.get("priceUsd"):
            out[m] = float(p["priceUsd"])
    return out


def close_all(s, why):
    px = live_prices(list(s["pos"]))
    for m, q in list(s["pos"].items()):
        price = px.get(m, 0.0)                          # no pool left counts as a rug
        got = q["qty"] * price * (1 - agents.SLIP) * (1 - agents.FEE)
        s["cash"] += got
        agents.log(s, "sell", mint=m, sym=q["sym"], price=price, usd=round(got, 4), pnl=round(got - q["cost"], 4), why=why)
        del s["pos"][m]


def tick(name, now=None):
    p = use(name)
    now = now or agents.grok.now()
    night = night_of(now)
    s = agents.load() if agents.STATE.exists() else dict(label=p["label"], nights=[], log=[], pos={}, cash=0, start_usd=1)
    sess = s.get("session")
    if sess and not sess.get("closed") and night != sess["night"]:          # morning (or a missed night): settle
        if s["pos"]:
            close_all(s, "ปิดรอบเช้า")
        eq = s["cash"]
        sells = [x for x in s["log"] if x["kind"] == "sell" and x["t"] >= sess["t"]]
        s["nights"].append(dict(night=sess["night"], start_usd=round(sess["start_usd"], 4), end_usd=round(eq, 4),
                                ret=round(eq / sess["start_usd"] - 1, 4), trades=len(sells), wins=sum(x["pnl"] > 0 for x in sells),
                                ended=sess.get("halted") or "09:00"))
        sess["closed"] = True
    if night and (not sess or sess["night"] != night):                        # evening: fresh 500 THB
        usd = START_THB / agents.grok.usdthb()
        s.update(cash=usd, start_usd=usd, pos={}, mirrored=[k for k, _ in source_buys()],
                 session=dict(night=night, t=now.isoformat(timespec="seconds"), start_usd=usd))
        sess = s["session"]
    if night and sess and not sess.get("halted"):
        done = set(s.get("mirrored", []))
        for key, x in source_buys():
            if key not in done:
                done.add(key)
                agents.paper_buy(s, x["mint"], x.get("sym"), source=key.split(":")[0])
        s["mirrored"] = sorted(done)
    agents.save(s)
    if night and sess and not sess.get("closed"):
        agents.cmd_run()                                                        # per-trade exits
        s = agents.load()
        chg = agents.equity(s) / sess["start_usd"] - 1
        hit = ("ถึงเป้าคืนนี้" if p["target"] is not None and chg >= p["target"] else
               "ชนเพดานขาดทุนคืนนี้" if chg <= p["stop"] else None)
        if hit and not sess.get("halted"):
            close_all(s, hit)
            s["session"]["halted"] = f"{hit} {chg:+.0%}"
        agents.save(s)


def report():
    for name in PROFILES:
        use(name)
        if not agents.STATE.exists():
            continue
        s = agents.load()
        n = s.get("nights", [])
        green = sum(x["ret"] > 0 for x in n)
        avg = sum(x["ret"] for x in n) / len(n) if n else 0
        print(f"{s['label']}: {len(n)} คืน, บวก {green}, เฉลี่ยต่อคืน {avg:+.1%}")
        for x in n[-7:]:
            print(f"   {x['night']}: {x['ret']:+.1%}  ไม้ {x['trades']} ชนะ {x['wins']}  จบเพราะ {x['ended']}")


if __name__ == "__main__":
    cmd = sys.argv[1:2]
    if cmd == ["tick"]:
        for name in PROFILES:
            tick(name)
    elif cmd == ["report"]:
        report()
    else:
        sys.exit(__doc__)
