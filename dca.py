#!/usr/bin/env python3
"""Paper "smart DCA" on BTCTHB: buy a fixed amount every week, more when BTC is
cheap and less when it is overheated. A second paper account next to paper.py,
with its own state file. Rules are explained in RULES_DCA.md.

  python3 dca.py backtest            # plain vs smart DCA from 12 different start dates
  python3 dca.py init 10000 250      # paper budget 10,000 THB, base buy 250 THB a week
  python3 dca.py run                 # any day after 07:00: buys once per week (Monday bar)
  python3 dca.py status
Standard library only. Reuses data and fee helpers from paper.py.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from paper import FEE, MIN_ORDER, SLIP, TH, bars, day, ma, price

SYM = "BTCTHB"
RSI_N, RSI_LOW, RSI_HIGH = 14, 30, 70
CHEAP_MA, HOT_PCT = 200, 0.30      # below MA200 is cheap, 30% above it is overheated
STATE = Path(__file__).with_name("state_dca.json")


def rsi(b, i, n=RSI_N):
    gain = loss = 0.0
    for j in range(i - n + 1, i + 1):
        d = b[j]["c"] - b[j - 1]["c"]
        gain, loss = gain + max(d, 0), loss + max(-d, 0)
    return 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)


def mult(b, i):
    """2x when cheap (RSI < 30 or below MA200), 0.5x when hot (RSI > 70 or 30% above MA200)."""
    c, m, r = b[i]["c"], ma(b, i, CHEAP_MA), rsi(b, i)
    if r < RSI_LOW or c < m:
        return 2.0
    if r > RSI_HIGH or c > m * (1 + HOT_PCT):
        return 0.5
    return 1.0


def monday(t):
    return datetime.fromtimestamp(t / 1000, TH).weekday() == 0


def backtest():
    b = bars(SYM)

    def dca(rule, start):
        spent = coins = 0.0
        for i in range(start, len(b)):
            if monday(b[i]["t"]):
                amt = 250 * rule(i)
                coins += amt / (b[i]["c"] * (1 + SLIP)) * (1 - FEE)
                spent += amt
        return spent, coins * b[-1]["c"] * (1 - FEE)

    print(f"Weekly DCA on {SYM}, valued at {b[-1]['c']:,.0f} on {day(b[-1]['t'])}")
    print("start        plain DCA          smart DCA          smart spent")
    for s in range(CHEAP_MA, len(b) - 120, 60):
        sp, v = dca(lambda i: 1.0, s)
        sp2, v2 = dca(lambda i: mult(b, i), s)
        print(f"{day(b[s]['t'])}   {v / sp - 1:+6.1%} cost {sp * b[-1]['c'] / v:>10,.0f}"
              f"   {v2 / sp2 - 1:+6.1%} cost {sp2 * b[-1]['c'] / v2:>10,.0f}   x{sp2 / sp:.2f}")


def load():
    if not STATE.exists():
        sys.exit("No DCA account yet. Run: python3 dca.py init 10000 250")
    return json.loads(STATE.read_text())


def save(st):
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2))


def init(budget, base):
    if STATE.exists():
        sys.exit("state_dca.json already exists. Delete it yourself to start over.")
    st = dict(cash=budget, start=budget, base=base, start_day=datetime.now(TH).strftime("%Y-%m-%d"),
              start_btc=price(SYM), coins=0.0, spent=0.0, done_t=0, buys=[], log=[])
    st["log"].append(f"{datetime.now(TH):%Y-%m-%d %H:%M} init {budget:,.0f} THB, base {base:,.0f}/week")
    save(st)
    print(f"DCA paper account: {budget:,.0f} THB, base {base:,.0f} THB a week")


def run():
    st = load()
    b = bars(SYM)
    i = max(j for j in range(len(b)) if monday(b[j]["t"]))  # latest closed Monday bar
    if b[i]["t"] <= st["done_t"]:
        print(f"Already bought for the week of {day(b[i]['t'])}. Next buy after next Tuesday 07:00.")
        return status(st)
    m = mult(b, i)
    amt = min(st["base"] * m, st["cash"])
    st["done_t"] = b[i]["t"]
    stamp = f"{datetime.now(TH):%Y-%m-%d %H:%M}"
    if amt < MIN_ORDER:
        st["log"].append(f"{stamp} week {day(b[i]['t'])}: budget used up, no buy")
        save(st)
        print("Budget used up.")
        return status(st)
    px = price(SYM) * (1 + SLIP)
    qty = amt / px * (1 - FEE)
    st["cash"] -= amt
    st["coins"] += qty
    st["spent"] += amt
    why = f"RSI {rsi(b, i):.1f}, close vs MA{CHEAP_MA} {b[i]['c'] / ma(b, i, CHEAP_MA) - 1:+.1%}"
    st["buys"].append(dict(week=day(b[i]["t"]), px=round(px, 2), thb=amt, qty=qty, mult=m, why=why))
    st["log"].append(f"{stamp} BUY {amt:,.0f} THB ({m:g}x) at {px:,.2f}. {why}")
    save(st)
    print(f"Week of {day(b[i]['t'])}: bought {amt:,.0f} THB ({m:g}x) at {px:,.2f}. {why}")
    status(st)


def status(st=None):
    st = st or load()
    px = price(SYM)
    value = st["coins"] * px * (1 - FEE)
    avg = st["spent"] / st["coins"] if st["coins"] else 0
    pnl = value / st["spent"] - 1 if st["spent"] else 0
    print(f"Spent {st['spent']:,.0f} of {st['start']:,.0f} THB, holding {st['coins']:.8f} BTC "
          f"worth {value:,.0f} ({pnl:+.2%}), avg cost {avg:,.0f}, BTC now {px:,.0f}")
    print(f"  {len(st['buys'])} weekly buys since {st['start_day']}, cash left {st['cash']:,.0f}")


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if cmd == "init" and len(args) == 2:
        init(float(args[0]), float(args[1]))
    elif cmd in ("backtest", "run", "status"):
        {"backtest": backtest, "run": run, "status": status}[cmd]()
    else:
        sys.exit(__doc__)
