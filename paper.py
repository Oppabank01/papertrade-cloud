#!/usr/bin/env python3
"""Paper trading on Binance TH spot (THB pairs) with fixed trend-following rules.
The rules are explained in RULES.md. This script enforces the mechanical parts
(signals, position size, stops, fees) so the AI can only take or veto a signal.

  python3 paper.py backtest              # same rules over the past ~2.5 years
  python3 paper.py init 100000           # start a paper account with 100,000 THB
  python3 paper.py run                   # daily after 07:00: apply stops, list signals
  python3 paper.py buy SOLTHB "reason"   # take a signal (size and stop computed here)
  python3 paper.py skip SOLTHB "reason"  # veto a signal (logged)
  python3 paper.py sell SOLTHB "reason"  # emergency exit only (hack, delisting)
  python3 paper.py status
  python3 paper.py serve                 # live dashboard on http://127.0.0.1:8765/dashboard.html
  python3 paper.py selftest
Standard library only. Public endpoints, no API key.
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://api.binance.th/api/v1"
UNIVERSE = ["BTCTHB", "ETHTHB", "BNBTHB", "SOLTHB", "XRPTHB"]
FEE, SLIP = 0.0025, 0.001          # Binance TH THB pairs fee per side, assumed slippage
RISK, MAX_POS_PCT, MAX_POS, MIN_ORDER = 0.01, 0.25, 4, 100
BREAKOUT, TREND_MA, REGIME_MA, ATR_N = 20, 50, 200, 14
STOP_ATR, TRAIL_ATR = 2, 3
STATE = Path(__file__).with_name("state.json")
TH = timezone(timedelta(hours=7))


def get(path):
    with urllib.request.urlopen(API + path, timeout=20) as r:
        return json.load(r)


def bars(sym):
    """Closed daily bars only (Binance daily candles close at 07:00 Thai time)."""
    k = get(f"/klines?symbol={sym}&interval=1d&limit=1000")
    now = time.time() * 1000
    return [dict(t=x[0], o=float(x[1]), h=float(x[2]), l=float(x[3]), c=float(x[4]))
            for x in k if x[6] < now]


def price(sym):
    return float(get(f"/ticker/price?symbol={sym}")["price"])


def day(t):
    return datetime.fromtimestamp(t / 1000, TH).strftime("%Y-%m-%d")


def ma(b, i, n):
    return sum(x["c"] for x in b[i - n + 1:i + 1]) / n


def atr(b, i, n=ATR_N):
    return sum(max(b[j]["h"] - b[j]["l"], abs(b[j]["h"] - b[j - 1]["c"]), abs(b[j]["l"] - b[j - 1]["c"]))
               for j in range(i - n + 1, i + 1)) / n


def regime_on(btc, i):
    return i >= REGIME_MA and btc[i]["c"] > ma(btc, i, REGIME_MA)


def signal(b, i):
    """Close breaks the previous 20-day high and sits above MA50."""
    if i < max(BREAKOUT, TREND_MA, ATR_N + 1):
        return False
    return b[i]["c"] > max(x["h"] for x in b[i - BREAKOUT:i]) and b[i]["c"] > ma(b, i, TREND_MA)


def size(equity, cash, px, stop):
    qty = min(equity * RISK / (px - stop), equity * MAX_POS_PCT / px, cash / (px * (1 + FEE)))
    return qty if qty * px >= MIN_ORDER else 0


def trail(p, b, i):
    """Process one closed bar: return the fill price if the stop was hit, else ratchet the stop up."""
    p["last"] = b[i]["c"]
    if b[i]["l"] <= p["stop"]:
        return min(b[i]["o"], p["stop"]) * (1 - SLIP)  # gap below the stop fills at the open
    p["stop"] = max(p["stop"], b[i]["c"] - TRAIL_ATR * atr(b, i))


def open_pos(cash, sym, px, stop, qty, t):
    p = dict(qty=qty, entry=px, stop=stop, init_stop=stop, last=px, t=t, last_t=t)
    return cash - qty * px * (1 + FEE), p


def close_pos(cash, sym, p, px, t, why):
    r = (px - p["entry"]) / (p["entry"] - p["init_stop"])
    trade = dict(sym=sym, entry=p["entry"], exit=px, opened=day(p["t"]), closed=day(t),
                 pnl=round(p["qty"] * (px * (1 - FEE) - p["entry"] * (1 + FEE)), 2), R=round(r, 2), why=why)
    return cash + p["qty"] * px * (1 - FEE), trade


def equity(cash, pos):
    return cash + sum(p["qty"] * p["last"] for p in pos.values())


def stats(trades):
    if not trades:
        return "no closed trades"
    wins = [t for t in trades if t["pnl"] > 0]
    return (f"{len(trades)} trades, win rate {len(wins) / len(trades):.0%}, "
            f"avg R {sum(t['R'] for t in trades) / len(trades):+.2f}, "
            f"P&L {sum(t['pnl'] for t in trades):+,.0f} THB")


def backtest():
    data = {s: bars(s) for s in UNIVERSE}
    idx = {s: {x["t"]: i for i, x in enumerate(b)} for s, b in data.items()}
    btc = data["BTCTHB"]
    cash, pos, trades, pending, peak, dd = 100000.0, {}, [], [], 100000.0, 0.0
    for k in range(REGIME_MA, len(btc)):
        t = btc[k]["t"]
        for s in pending:  # yesterday's signals fill at today's open
            b, i = data[s], idx[s].get(t)
            if i is None:
                continue
            px = b[i]["o"] * (1 + SLIP)
            stop = px - STOP_ATR * atr(b, i - 1)
            qty = size(equity(cash, pos), cash, px, stop)
            if qty:
                cash, pos[s] = open_pos(cash, s, px, stop, qty, t)
        pending = []
        for s, p in list(pos.items()):
            i = idx[s].get(t)
            if i is not None and (fill := trail(p, data[s], i)):
                cash, tr = close_pos(cash, s, pos.pop(s), fill, t, "stop")
                trades.append(tr)
        if regime_on(btc, k):
            for s in UNIVERSE:
                i = idx[s].get(t)
                if i is not None and s not in pos and len(pos) + len(pending) < MAX_POS and signal(data[s], i):
                    pending.append(s)
        eq = equity(cash, pos)
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    eq = equity(cash, pos)
    print(f"Backtest {day(btc[REGIME_MA]['t'])} to {day(btc[-1]['t'])}, start 100,000 THB")
    print(f"  Strategy: {eq / 100000 - 1:+.1%}, max drawdown {dd:.1%}, still open {list(pos)}")
    print(f"  BTC buy and hold: {btc[-1]['c'] / btc[REGIME_MA]['c'] - 1:+.1%}")
    print(f"  {stats(trades)}")


def load():
    if not STATE.exists():
        sys.exit("No account yet. Run: python3 paper.py init 100000")
    return json.loads(STATE.read_text())


def save(st):
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2))


def log(st, msg):
    st["log"].append(f"{datetime.now(TH):%Y-%m-%d %H:%M} {msg}")


def init(amount):
    if STATE.exists():
        sys.exit("state.json already exists. Delete it yourself to start over.")
    st = dict(cash=amount, start=amount, start_day=datetime.now(TH).strftime("%Y-%m-%d"),
              start_btc=price("BTCTHB"), positions={}, signals={}, trades=[], log=[])
    log(st, f"init {amount:,.0f} THB")
    save(st)
    print(f"Paper account started with {amount:,.0f} THB")


def run():
    st = load()
    data = {s: bars(s) for s in UNIVERSE}
    for s, p in list(st["positions"].items()):
        b = data[s]
        for i, x in enumerate(b):
            if x["t"] <= p["last_t"]:
                continue
            p["last_t"] = x["t"]
            if fill := trail(p, b, i):
                st["cash"], tr = close_pos(st["cash"], s, st["positions"].pop(s), fill, x["t"], "stop")
                st["trades"].append(tr)
                log(st, f"STOP {s} at {fill:,.2f} ({tr['R']:+.2f}R, {tr['pnl']:+,.0f} THB)")
                print(f"Stopped out {s} at {fill:,.2f}: {tr['R']:+.2f}R, {tr['pnl']:+,.0f} THB")
                break
    btc = data["BTCTHB"]
    on = regime_on(btc, len(btc) - 1)
    st["signals"] = {}
    if on and len(st["positions"]) < MAX_POS:
        for s in UNIVERSE:
            b = data[s]
            if s not in st["positions"] and signal(b, len(b) - 1):
                st["signals"][s] = dict(t=b[-1]["t"], atr=atr(b, len(b) - 1))
    save(st)
    print(f"Last closed bar {day(btc[-1]['t'])}. Regime (BTC > MA{REGIME_MA}): {'ON' if on else 'OFF, no new buys'}")
    print("Signals:", ", ".join(st["signals"]) or "none")
    status(st)


def buy(sym, note):
    st = load()
    sig = st["signals"].get(sym)
    if not sig:
        sys.exit(f"{sym} has no live signal. Only signals from today's run can be taken.")
    b = bars(sym)
    if b[-1]["t"] != sig["t"]:
        sys.exit("Signal expired (a new daily bar closed). Run again first.")
    if len(st["positions"]) >= MAX_POS:
        sys.exit(f"Already holding {MAX_POS} positions.")
    px = price(sym) * (1 + SLIP)
    stop = px - STOP_ATR * sig["atr"]
    eq = equity(st["cash"], st["positions"])
    qty = size(eq, st["cash"], px, stop)
    if not qty:
        sys.exit("Size below the 100 THB minimum or no cash.")
    # shortcut: the entry bar's low (before our fill) also counts for the stop, slightly pessimistic
    st["cash"], st["positions"][sym] = open_pos(st["cash"], sym, px, stop, qty, sig["t"])
    del st["signals"][sym]
    log(st, f"BUY {sym} {qty:.6g} at {px:,.2f}, stop {stop:,.2f}. {note}")
    save(st)
    print(f"Bought {qty:.6g} {sym} at {px:,.2f} ({qty * px:,.0f} THB), stop {stop:,.2f}")


def skip(sym, note):
    st = load()
    if st["signals"].pop(sym, None) is None:
        sys.exit(f"{sym} has no live signal.")
    log(st, f"SKIP {sym}. {note}")
    save(st)
    print(f"Skipped {sym}")


def sell(sym, note):
    st = load()
    if sym not in st["positions"]:
        sys.exit(f"Not holding {sym}.")
    px = price(sym) * (1 - SLIP)
    st["cash"], tr = close_pos(st["cash"], sym, st["positions"].pop(sym), px, time.time() * 1000, "manual")
    st["trades"].append(tr)
    log(st, f"MANUAL SELL {sym} at {px:,.2f} ({tr['R']:+.2f}R). {note}")
    save(st)
    print(f"Sold {sym} at {px:,.2f}: {tr['R']:+.2f}R, {tr['pnl']:+,.0f} THB")


def status(st=None):
    st = st or load()
    for s, p in st["positions"].items():
        p["last"] = price(s)
    eq = equity(st["cash"], st["positions"])
    btc_ret = price("BTCTHB") / st["start_btc"] - 1
    print(f"Equity {eq:,.0f} THB ({eq / st['start'] - 1:+.2%}) since {st['start_day']}, "
          f"BTC buy and hold {btc_ret:+.2%}, cash {st['cash']:,.0f}")
    for s, p in st["positions"].items():
        print(f"  {s}: {p['qty']:.6g} @ {p['entry']:,.2f}, now {p['last']:,.2f} "
              f"({p['last'] / p['entry'] - 1:+.1%}), stop {p['stop']:,.2f}")
    print(f"  Closed: {stats(st['trades'])}")


def selftest():
    p = dict(stop=90.0)
    flat = [dict(t=j, o=100, h=101, l=99, c=100) for j in range(20)]
    assert trail(p, flat + [dict(t=20, o=95, h=96, l=85, c=88)], 20) == 90 * (1 - SLIP)
    assert trail(p, flat + [dict(t=20, o=89, h=89, l=85, c=86)], 20) == 89 * (1 - SLIP)
    assert trail(p, flat, 19) is None and p["stop"] == 94  # 100 - 3 * ATR(2)
    assert size(100000, 100000, 100, 98) == 250  # 1% risk wants 500, 25% cap allows 250
    assert size(100000, 50, 100, 98) == 0        # under the 100 THB minimum
    cash, p = open_pos(1000, "X", 100, 90, 5, 0)
    cash, tr = close_pos(cash, "X", p, 120, 0, "t")
    assert tr["R"] == 2 and abs(cash - (1000 - 500 * 1.0025 + 600 * 0.9975)) < 1e-9
    print("selftest ok")


def serve():
    import functools
    import http.server
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(STATE.parent))
    print("Dashboard: http://127.0.0.1:8765/dashboard.html  (Ctrl+C to stop)")
    http.server.ThreadingHTTPServer(("127.0.0.1", 8765), h).serve_forever()


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if cmd == "init" and args:
        init(float(args[0]))
    elif cmd in ("buy", "skip", "sell") and len(args) >= 2:
        {"buy": buy, "skip": skip, "sell": sell}[cmd](args[0].upper(), " ".join(args[1:]))
    elif cmd in ("backtest", "run", "status", "selftest", "serve"):
        {"backtest": backtest, "run": run, "status": status, "selftest": selftest, "serve": serve}[cmd]()
    else:
        sys.exit(__doc__)
