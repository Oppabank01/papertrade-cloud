#!/usr/bin/env python3
"""Forward paper test: buy high-dividend Thai stocks 6 trading days before XD, sell the day before XD (opened 27 Nov 2026).
Fake money only.

Rule (the passer of the 27 Nov round-2 hunt): a SET/mai stock with an announced XD date and an upcoming dividend of at
least 4% of the entry close, average turnover at least 5M THB a day. Buy at the close 6 trading days before XD, sell at
the close of the last cum-dividend day (5 days held, no dividend received, so no withholding tax). Stop 8% checked first
on daily lows (fill min(open, stop)). 10% of the start per trade, 0.17% per side.
Honesty: the XD date must have been seen in the calendar before the entry day's close (seen time is recorded), and the
yield uses the entry close. The trade is booked once the XD bar exists, from Yahoo daily bars, so missed runs book the same.
Calendar: TradingView scanner (keyless POST, upcoming XD date and amount). Prices: Yahoo chart JSON (SYMBOL.BK).
Who loses: late dividend chasers. Buying the last cum-dividend close and holding through XD loses about 1.8% after tax.
Backtest 2010 - 2026, 421 SET/mai stocks (252 of them never used to find the rule): yield 4%+, 8% stop, n 1,174, mean
+1.00%, median +0.66%, 61% winners, without best 5 +0.90%, halves +1.13 / +0.88; random days -0.2%. Weaker in liquid
names (+0.85% at 5M THB/day, +0.58% at 20M in 2023-26) and an extra 0.25%/side of spread halves it, so it sits on the bar.
About 11 trades a month on average, 80% in Feb-Apr and Aug. A Thai user trades it with at-the-close orders in any broker app.
  state_fwd_prexd.json        the rule
  state_fwd_prexd_twin.json   control: same entry and exit days, a random liquid stock with no XD in the calendar
  python3 fwd_prexd.py"""
import json, random, time, urllib.request
from datetime import datetime, timezone, timedelta
from byttrade import iso, load, save

COST, SIZE, YIELD, MINTURN, STOP, BEFORE = 0.0017, 0.10, 0.04, 5e6, 0.08, 6
TV = "https://scanner.tradingview.com/thailand/scan"
YH = "https://query1.finance.yahoo.com/v8/finance/chart/{}.BK?range=3mo&interval=1d"
BKK = timezone(timedelta(hours=7))
ACCOUNTS = {"state_fwd_prexd.json": ("rule", "หุ้นไทยปันผล 4% ขึ้นไป ซื้อก่อน XD 6 วันทำการ ขายวันก่อน XD stop 8% (backtest 1,174 ไม้ เฉลี่ย +1.0%)"),
            "state_fwd_prexd_twin.json": ("random", "หุ้นไทยก่อน XD ตัวควบคุม: วันซื้อขายเดียวกัน หุ้นสุ่มที่ไม่มี XD ใกล้ๆ")}


def get(u, body=None):
    h = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
    rq = urllib.request.Request(u, json.dumps(body).encode() if body else None, h)
    return json.loads(urllib.request.urlopen(rq, timeout=20).read())


def scan(get=get):
    """(calendar [(sym, xd 'YYYY-MM-DD', amount, turnover THB/day)], liquid universe [sym])."""
    cols = ["name", "close", "average_volume_30d_calc", "ex_dividend_date_upcoming", "dividend_amount_upcoming"]
    j = get(TV, {"filter": [{"left": "type", "operation": "equal", "right": "stock"}], "columns": cols,
                 "sort": {"sortBy": "average_volume_30d_calc", "sortOrder": "desc"}, "range": [0, 1500], "markets": ["thailand"]})
    cal, univ = [], []
    for r in j["data"]:
        n, c, v, xd, amt = r["d"]
        if not n or "." in n or not c or not v:
            continue
        turn = c * v
        if turn >= MINTURN:
            univ.append(n)
        if xd and amt:
            cal.append((n, datetime.fromtimestamp(xd, timezone.utc).strftime("%Y-%m-%d"), float(amt), turn))
    return cal, univ


def daily(sym, get=get):
    """[(bangkok date, close-time ms, o, l, c)] from Yahoo."""
    r = get(YH.format(sym))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    out = []
    for t, o, l, c in zip(r["timestamp"], q["open"], q["low"], q["close"]):
        if None in (o, l, c):
            continue
        d = datetime.fromtimestamp(t, BKK)
        out.append((d.strftime("%Y-%m-%d"), int(d.replace(hour=16, minute=40).timestamp() * 1000), o, l, c))
    return out


def window(b, xd):
    """(entry bar, later bars up to the last cum day) or None."""
    i = next((k for k, x in enumerate(b) if x[0] == xd), None)
    if i is None or i - BEFORE < 0:
        return None
    return b[i - BEFORE], b[i - BEFORE + 1:i]


def book(s, sym, e, rest, why):
    px, out = rest[-1][4], "ขายวันก่อน XD"
    lvl = e[4] * (1 - STOP)
    for d, t, o, l, c in rest:
        if l <= lvl:
            px, out = min(o, lvl), "stop -8%"
            break
    usd = min(s["start_usd"] * SIZE, s["cash"])
    if usd <= 0:
        return
    ret = px / e[4] - 1
    pnl = usd * (1 + ret) * (1 - COST) - usd * (1 + COST)
    s["cash"] += pnl
    s["log"].append(dict(kind="buy", t=iso(e[1]), coin=sym, px=e[4], usd=usd, why=why))
    s["log"].append(dict(kind="sell", t=iso(rest[-1][1]), coin=sym, px=px, usd=usd, ret=round(ret, 6), pnl=pnl, cost_side=COST, why=out))


def step(rule, twin, cal, univ, now, rng, daily=daily):
    """Record new calendar rows, then book every XD whose bar exists (today in Bangkok is on or after XD)."""
    for st in (rule, twin):
        st.setdefault("cal", {})
        if univ:
            st["univ"] = univ
    for sym, xd, amt, turn in cal:
        rule["cal"].setdefault(f"{sym}|{xd}", dict(sym=sym, xd=xd, amt=amt, turn=turn, seen=now))
    today = datetime.fromtimestamp(now / 1000, BKK).strftime("%Y-%m-%d")
    near = {x["sym"] for x in rule["cal"].values()}
    for k, x in list(rule["cal"].items()):
        if x.get("done") or x["xd"] > today:
            continue
        try:
            w = window(daily(x["sym"]), x["xd"])
        except Exception as e:
            print("fwd_prexd yahoo", x["sym"], type(e).__name__)
            if x["xd"] < (datetime.fromtimestamp(now / 1000, BKK) - timedelta(days=10)).strftime("%Y-%m-%d"):
                x["done"] = "no data"
            continue
        if w is None:
            if x["xd"] < today:                              # XD passed and still no bar (holiday or bad date)
                x["done"] = "no bar"
            continue
        x["done"] = "checked"
        e, rest = w
        y = x["amt"] / e[4]
        if x["seen"] > e[1] or y < YIELD or x["turn"] < MINTURN or not rest:
            continue
        x["done"] = "traded"
        book(rule, x["sym"], e, rest, f"ปันผล {y:.1%} XD {x['xd']}")
        pool = [u for u in twin.get("univ", []) if u not in near]
        for _ in range(5):                                   # a random stock may lack Yahoo bars on those days
            if not pool:
                break
            u = rng.choice(pool)
            try:
                b = {d[0]: d for d in daily(u)}
            except Exception:
                continue
            seq = [b.get(d[0]) for d in [e] + rest]
            if all(seq):
                book(twin, u, seq[0], seq[1:], f"สุ่มคู่กับ {x['sym']}")
                break
    cut = (datetime.fromtimestamp(now / 1000, BKK) - timedelta(days=60)).strftime("%Y-%m-%d")
    rule["cal"] = {k: v for k, v in rule["cal"].items() if v["xd"] >= cut}
    twin.pop("cal", None)


def main():
    now, rng = time.time() * 1000, random.Random()
    (fr, (_, lr)), (ft, (_, lt)) = ACCOUNTS.items()
    rule, twin = load(fr, lr), load(ft, lt)
    cal, univ = [], []
    if now - rule.get("last_scan", 0) > 6 * 3600 * 1000:
        try:
            cal, univ = scan()
            rule["last_scan"] = now
        except Exception as e:
            print("fwd_prexd scan failed", type(e).__name__)
    step(rule, twin, cal, univ, now, rng)
    save(fr, rule); save(ft, twin)


if __name__ == "__main__":
    main()
