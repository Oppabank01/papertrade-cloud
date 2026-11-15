#!/usr/bin/env python3
"""One-day paper accounts on big coins (15 Nov 2026), fake money only. Prices are Hyperliquid 1-minute candles, walked
in order since the last run, so fills inside the ~5 min between cloud runs are still seen. Cost 0.1% per side
(Binance TH spot), plus 0.05% slippage on market orders. Each account books one day 09:00 to 09:00 Bangkok:
grid and dip close everything at 09:00, the carry account is delta-neutral and is only measured.

  d_grid_btc_500  buy limits every 0.5% below the 09:00 price (8 levels), sell each fill 0.5% higher
  d_grid_sol_500  same on SOL
  d_liqdip_500    BTC/ETH/SOL fell hard in 60 min (-2% BTC, -3% ETH/SOL): buy, TP +1.5%, stop -2.5%, max 6 h
  d_fundspike_500 hourly funding >= 0.01% (~88%/yr) on a top-15 perp: hold spot + short perp, out below 0.002%

  python3 daytrade.py init 500 | run | report
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HL = "https://api.hyperliquid.xyz/info"
TH = timezone(timedelta(hours=7))
HERE = Path(__file__).parent
FEE, SLIP = 0.001, 0.0005
MIN = 60_000
GRID_STEP, GRID_N = 0.005, 8
DIP = {"BTC": -0.02, "ETH": -0.03, "SOL": -0.03}
DIP_TP, DIP_STOP, DIP_HOLD = 0.015, -0.025, 6 * 60 * MIN
SPIKE_IN, SPIKE_OUT, SPIKE_COST, SPIKE_MAX = 0.0001, 0.00002, 0.006, 3   # 0.3% to go in, 0.3% out (both legs), as funding.py
ACCOUNTS = {"d_grid_btc_500": ("กริด BTC ทุก 0.5% 8 ขั้น ปิดทุก 09:00", "grid", "BTC"),
            "d_grid_sol_500": ("กริด SOL ทุก 0.5% 8 ขั้น ปิดทุก 09:00", "grid", "SOL"),
            "d_liqdip_500": ("ช้อนเหรียญใหญ่ร่วงแรงใน 1 ชม. TP +1.5% stop -2.5%", "dip", None),
            "d_fundspike_500": ("funding พุ่งเกิน 0.01%/ชม. ถือ spot + short perp", "spike", None)}


def post(body):
    req = urllib.request.Request(HL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def candles(coin, start_ms):
    """Closed 1-minute candles from start_ms, oldest first: [(t, o, h, l, c)]."""
    now = int(time.time() * 1000)
    rows = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1m", "startTime": start_ms, "endTime": now}})
    return [(x["t"], float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"])) for x in rows if x["T"] < now]


def path(name):
    return HERE / f"state_day_{name}.json"


def book_day(t_ms):
    """The 09:00-to-09:00 Bangkok day a moment belongs to, named by its start date."""
    return (datetime.fromtimestamp(t_ms / 1000, TH) - timedelta(hours=9)).date().isoformat()


def log(s, t_ms, **kw):
    s["log"].append(dict(t=datetime.fromtimestamp(t_ms / 1000, TH).isoformat(timespec="seconds"), **kw))


def roll(s, t_ms, eq, close_all):
    """Book the finished day at equity eq (after close_all has turned positions into cash) and start the next."""
    day = book_day(t_ms)
    if s.get("day") and s["day"] != day:
        close_all()
        s["days"].append(dict(day=s["day"], ret=round(eq() / s["day_start"] - 1, 5)))
        s["day"] = None
    if s.get("day") != day:
        s.update(day=day, day_start=eq())
        return True
    return False


# ---------- grid ----------
def grid_eq(s, px):
    return s["cash"] + sum(l["qty"] for l in s["grid"]) * px


def grid_reset(s, px):
    cap = s["cash"] / GRID_N
    s.update(center=px, grid=[dict(buy=px * (1 - GRID_STEP * (i + 1)), cap=cap, qty=0.0, bt=0) for i in range(GRID_N)])


def grid_step(s, cs):
    for t, o, h, lo, c in cs:
        def close_all():
            for lv in s["grid"]:
                if lv["qty"]:
                    s["cash"] += lv["qty"] * o * (1 - SLIP) * (1 - FEE)
                    lv["qty"] = 0.0
        if roll(s, t, lambda: grid_eq(s, o), close_all) or not s.get("grid"):
            grid_reset(s, o)
        if not any(lv["qty"] for lv in s["grid"]) and o > s["center"] * (1 + 2 * GRID_STEP):
            grid_reset(s, o)            # flat and the price walked away upward: re-centre so the grid can trade
        for lv in s["grid"]:
            if not lv["qty"] and lo <= lv["buy"] and s["cash"] >= lv["cap"] - 1e-9:
                s["cash"] -= lv["cap"]
                lv.update(qty=lv["cap"] * (1 - FEE) / lv["buy"], bt=t)
            elif lv["qty"] and lv["bt"] < t and h >= lv["buy"] * (1 + GRID_STEP):
                s["cash"] += lv["qty"] * lv["buy"] * (1 + GRID_STEP) * (1 - FEE)
                s["trips"] = s.get("trips", 0) + 1
                lv["qty"] = 0.0
        s["last_t"], s["px"] = t, c


# ---------- dip ----------
def dip_eq(s, px):
    return s["cash"] + sum(p["qty"] * px.get(k, p["entry"]) for k, p in s["pos"].items())


def dip_sell(s, k, t, price, why):
    p = s["pos"].pop(k)
    usd = p["qty"] * price * (1 - FEE)
    s["cash"] += usd
    log(s, t, kind="sell", coin=k, price=price, pnl=round(usd - p["cost"], 4), why=why)


def dip_step(s, data):
    times = sorted({t for cs in data.values() for t, *_ in cs if t > s["last_t"]})
    by = {k: {t: (o, h, lo, c) for t, o, h, lo, c in cs} for k, cs in data.items()}
    for t in times:
        last = {k: by[k][t][0] for k in by if t in by[k]}
        roll(s, t, lambda: dip_eq(s, {**s["px"], **last}),
             lambda: [dip_sell(s, k, t, last.get(k, s["px"].get(k)) * (1 - SLIP), "ปิดรอบ 09:00") for k in list(s["pos"])])
        for k in by:
            if t not in by[k]:
                continue
            o, h, lo, c = by[k][t]
            p = s["pos"].get(k)
            if p:
                if lo <= p["entry"] * (1 + DIP_STOP):
                    dip_sell(s, k, t, p["entry"] * (1 + DIP_STOP) * (1 - SLIP), "stop")
                elif h >= p["entry"] * (1 + DIP_TP):
                    dip_sell(s, k, t, p["entry"] * (1 + DIP_TP), "tp")
                elif t - p["t"] >= DIP_HOLD:
                    dip_sell(s, k, t, c * (1 - SLIP), "ครบ 6 ชม.")
            ago = by[k].get(t - 60 * MIN)
            if k not in s["pos"] and ago and c / ago[3] - 1 <= DIP[k] and t - s["cool"].get(k, 0) >= 120 * MIN:
                spend = min(s["cash"], dip_eq(s, {**s["px"], **last}) / len(DIP))
                if spend > 0.05:
                    price = c * (1 + SLIP)
                    s["cash"] -= spend
                    s["pos"][k] = dict(qty=spend * (1 - FEE) / price, entry=price, cost=spend, t=t)
                    s["cool"][k] = t
                    log(s, t, kind="buy", coin=k, price=price, usd=round(spend, 4), why=f"60 นาที {c / ago[3] - 1:+.1%}")
            s["px"][k] = c
        s["last_t"] = t


# ---------- funding spike ----------
def spike_eq(s):
    return s["cash"] + sum(s["sleeve"].values())


def spike_step(s, ctx, hist, now_ms):
    """ctx: {coin: current hourly funding} for the top-15 perps; hist: {held coin: [(t, rate)]} since last_t."""
    for k in s["sleeve"]:
        for t, r in hist.get(k, []):
            if s["last_t"] < t <= now_ms:
                s["sleeve"][k] *= 1 + r
    roll(s, now_ms, lambda: spike_eq(s), lambda: None)
    for k in [k for k in s["sleeve"] if ctx.get(k, 0) < SPIKE_OUT]:
        usd = s["sleeve"].pop(k) * (1 - SPIKE_COST / 2)
        s["cash"] += usd
        log(s, now_ms, kind="sell", coin=k, usd=round(usd, 4), why=f"funding {ctx.get(k, 0):.4%}/ชม.")
    for k, r in sorted(ctx.items(), key=lambda x: -x[1]):
        if r >= SPIKE_IN and k not in s["sleeve"] and len(s["sleeve"]) < SPIKE_MAX:
            spend = min(s["cash"], spike_eq(s) / SPIKE_MAX)
            s["cash"] -= spend
            s["sleeve"][k] = spend * (1 - SPIKE_COST / 2)
            log(s, now_ms, kind="buy", coin=k, usd=round(spend, 4), why=f"funding {r:.4%}/ชม.")
    s["last_t"] = now_ms


def top_funding():
    meta, ctxs = post({"type": "metaAndAssetCtxs"})
    rows = sorted(((float(x["openInterest"]) * float(x["markPx"]), u["name"], float(x["funding"]))
                   for u, x in zip(meta["universe"], ctxs)), reverse=True)[:15]
    return {k: r for _, k, r in rows}


def funding_since(coin, start_ms):
    return [(x["time"], float(x["fundingRate"])) for x in post({"type": "fundingHistory", "coin": coin, "startTime": start_ms})]


# ---------- commands ----------
def cmd_init(thb):
    with urllib.request.urlopen("https://api.binance.th/api/v1/ticker/price?symbol=USDTTHB", timeout=20) as r:
        usd = float(thb) / float(json.load(r)["price"])
    now = int(time.time() * 1000) // MIN * MIN
    for name, (label, kind, coin) in ACCOUNTS.items():
        if not path(name).exists():
            s = dict(label=label, start_usd=usd, start_thb=float(thb), cash=usd, last_t=now - MIN, log=[], days=[], px=0 if kind == "grid" else {})
            s.update(dict(grid=[], center=0) if kind == "grid" else dict(pos={}, cool={}) if kind == "dip" else dict(sleeve={}))
            path(name).write_text(json.dumps(s, ensure_ascii=False, indent=1))
            print(f"init {name}")


def cmd_run():
    states = {n: json.loads(path(n).read_text()) for n in ACCOUNTS if path(n).exists()}
    for name, s in states.items():
        label, kind, coin = ACCOUNTS[name]
        try:
            start = max(s["last_t"] + MIN, int(time.time() * 1000) - 3 * 3600 * 1000)   # a long outage resumes from 3 h back
            if kind == "grid":
                grid_step(s, [x for x in candles(coin, start) if x[0] > s["last_t"]])
            elif kind == "dip":
                dip_step(s, {k: candles(k, start - 61 * MIN) for k in DIP})
            else:
                now = int(time.time() * 1000)
                spike_step(s, top_funding(), {k: funding_since(k, s["last_t"] + 1) for k in s["sleeve"]}, now)
        except Exception as e:                  # an API error is a missed round, never a guessed price
            print(f"daytrade {name} error: {e!r}"[:200])
            continue
        path(name).write_text(json.dumps(s, ensure_ascii=False, indent=1))


def equity(name, s):
    kind = ACCOUNTS[name][1]
    return grid_eq(s, s.get("px") or 0) if kind == "grid" else dip_eq(s, s["px"]) if kind == "dip" else spike_eq(s)


def cmd_report():
    for name in ACCOUNTS:
        if path(name).exists():
            s = json.loads(path(name).read_text())
            d = s["days"]
            print(f"{equity(name, s) / s['start_usd'] - 1:+7.2%}  {name:16s} วัน {len(d):3d} บวก {sum(x['ret'] > 0 for x in d):3d}  {s['label']}")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmds = {"init": lambda: cmd_init(a[1]), "run": cmd_run, "report": cmd_report}
    if not a or a[0] not in cmds:
        sys.exit(__doc__)
    cmds[a[0]]()
