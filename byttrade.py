#!/usr/bin/env python3
"""Forward paper test of byttrade/free-crypto-trading-bot "st4h_ema50_1d" on SOL (opened 23 Nov 2026 at the user's
request after the scout's backtest: SOL 2020-2026 +2.33%/trade, permutation p 0.005 long+short, 0.010 long only).
Fake money only.

Rule, on closed 4h SOLUSDT bars: Supertrend(10, 3) flips direction and the last closed daily close is on the same side
of its EMA50 -> enter that way at the next 4h open. Stop 2 ATR14(4h), take 10 ATR, trailing stop 5 ATR from the best
price, all checked on closed 4h bars (as in the backtest). One position at a time, whole account, 0.35% per side.
  state_byt_sol.json       long and short
  state_byt_sol_long.json  long only (what Binance TH spot allows)
  state_byt_sol_twin.json  control: random entry times (1 in 50 free bars) on the daily-regime side, same exits
Runs every cloud.sh tick; acts only when a new 4h bar has closed. Prices: Binance public data API; a failed fetch
means no action.  python3 byttrade.py run | report"""
import json, os, random, sys, time, urllib.request
from datetime import datetime, timezone

H4, DAY = 4 * 3600 * 1000, 86400 * 1000
THB, RATE, COST, TWIN_P = 500.0, 33.9, 0.0035, 1 / 50
SL, TP, TR = 2, 10, 5
URL = "https://data-api.binance.vision/api/v3/klines?symbol={}&interval=4h&limit=1000"
ACCOUNTS = {   # file: (sides, mode, label, symbol); BTC and ETH added 23 Nov 00:59 (backtest p 0.109 / 0.010, opened anyway)
    "state_byt_sol.json": ((1, -1), "flip", "byttrade SOL 4 ชม. long+short: Supertrend กลับทิศตามฝั่ง EMA50 รายวัน stop 2 ATR เป้า 10 ATR trail 5 ATR", "SOLUSDT"),
    "state_byt_sol_long.json": ((1,), "flip", "byttrade SOL 4 ชม. long อย่างเดียว กฎเดียวกัน", "SOLUSDT"),
    "state_byt_sol_twin.json": ((1, -1), "random", "byttrade SOL ตัวควบคุม: เข้าสุ่มเวลา ฝั่งตาม EMA50 รายวัน ออกแบบเดียวกัน", "SOLUSDT"),
    "state_byt_eth.json": ((1, -1), "flip", "byttrade ETH 4 ชม. long+short กฎเดียวกับ SOL", "ETHUSDT"),
    "state_byt_eth_twin.json": ((1, -1), "random", "byttrade ETH ตัวควบคุม: เข้าสุ่มเวลา ฝั่งตาม EMA50 รายวัน", "ETHUSDT"),
    "state_byt_btc.json": ((1, -1), "flip", "byttrade BTC 4 ชม. long+short กฎเดียวกับ SOL", "BTCUSDT"),
    "state_byt_btc_twin.json": ((1, -1), "random", "byttrade BTC ตัวควบคุม: เข้าสุ่มเวลา ฝั่งตาม EMA50 รายวัน", "BTCUSDT"),
}


def wilder_atr(b, n):
    tr = [b[0]["h"] - b[0]["l"]] + [max(x["h"] - x["l"], abs(x["h"] - p["c"]), abs(x["l"] - p["c"])) for p, x in zip(b, b[1:])]
    a = [None] * len(b)
    if len(b) <= n:
        return a
    a[n - 1] = sum(tr[:n]) / n
    for i in range(n, len(b)):
        a[i] = (a[i - 1] * (n - 1) + tr[i]) / n
    return a


def supertrend_dir(b, n=10, m=3.0):
    atr, d, fu, fl = wilder_atr(b, n), [0] * len(b), None, None
    for i in range(len(b)):
        if atr[i] is None:
            continue
        mid = (b[i]["h"] + b[i]["l"]) / 2
        bu, bl = mid + m * atr[i], mid - m * atr[i]
        if fu is None:
            fu, fl, d[i] = bu, bl, 1
            continue
        pc = b[i - 1]["c"]
        fu = bu if (bu < fu or pc > fu) else fu
        fl = bl if (bl > fl or pc < fl) else fl
        prev = d[i - 1] or 1
        d[i] = -1 if prev == 1 and b[i]["c"] < fl else 1 if prev == -1 and b[i]["c"] > fu else prev
    return d


def daily_regime(b):
    """+1/-1 per 4h bar from the last daily bar fully closed when that 4h bar closes (close vs EMA50 seeded with SMA)."""
    days, cur = [], None
    for x in b:
        k = x["t"] // DAY
        if k != cur:
            days.append([k, x["c"]]); cur = k
        else:
            days[-1][1] = x["c"]
    ema, reg = [None] * len(days), {}
    for i in range(len(days)):
        if i == 49:
            ema[i] = sum(d[1] for d in days[:50]) / 50
        elif i > 49:
            ema[i] = ema[i - 1] + 2 / 51 * (days[i][1] - ema[i - 1])
        if ema[i] is not None:
            reg[days[i][0]] = 1 if days[i][1] > ema[i] else -1
    return [reg.get((x["t"] + H4) // DAY - 1, 0) for x in b]


def iso(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).astimezone().isoformat(timespec="seconds")


def new_state(label):
    return dict(label=label, start_thb=THB, start_usd=THB / RATE, cash=THB / RATE, pos={}, log=[], seen=None)


def open_pos(s, side, px, t, atr, why, sym="SOLUSDT"):
    usd = s["cash"] / (1 + COST)
    s["cash"] += (-usd if side > 0 else usd) - usd * COST       # a short books the proceeds: value = cash + qty*last
    s["pos"][sym] = dict(side="long" if side > 0 else "short", d=side, qty=side * usd / px, entry=px, last=px, usd=usd,
                               atr=atr, stop=px - side * SL * atr, take=px + side * TP * atr, best=px, entry_t=t, t=iso(t), why=why)
    s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side=s["pos"][sym]["side"], px=px, usd=usd, why=why))


def close_pos(s, px, t, why, sym="SOLUSDT"):
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def exit_check(s, x, sym="SOLUSDT"):
    """One closed bar against the open position, exactly as the backtest: gap fills at the open after the entry bar."""
    p = s["pos"][sym]
    first, o, h, l = x["t"] == p["entry_t"], x["o"], x["h"], x["l"]
    if p["d"] > 0:
        if l <= p["stop"]:
            return close_pos(s, p["stop"] if first else min(o, p["stop"]), x["t"] + H4, "stop/trail", sym) or True
        if h >= p["take"]:
            return close_pos(s, p["take"] if first else max(o, p["take"]), x["t"] + H4, "ถึงเป้า 10 ATR", sym) or True
        p["best"] = max(p["best"], h); p["stop"] = max(p["stop"], p["best"] - TR * p["atr"])
    else:
        if h >= p["stop"]:
            return close_pos(s, p["stop"] if first else max(o, p["stop"]), x["t"] + H4, "stop/trail", sym) or True
        if l <= p["take"]:
            return close_pos(s, p["take"] if first else min(o, p["take"]), x["t"] + H4, "ถึงเป้า 10 ATR", sym) or True
        p["best"] = min(p["best"], l); p["stop"] = min(p["stop"], p["best"] + TR * p["atr"])
    return False


def process(s, bars, sides, mode, rng, sym="SOLUSDT"):
    """bars: oldest first, the last one may still be forming (closed=False). Walks every closed bar after s['seen']."""
    closed = [x for x in bars if x["closed"]]
    if s["seen"] is None:                       # a new account starts from the latest closed bar, no stale signal
        s["seen"] = closed[-1]["t"]
        return
    atr, d, reg = wilder_atr(bars, 14), supertrend_dir(bars), daily_regime(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= s["seen"] or i + 1 >= len(bars):
            continue
        s["seen"] = x["t"]
        exited = False
        if sym in s["pos"] and x["t"] >= s["pos"][sym]["entry_t"]:
            exited = exit_check(s, x, sym)
        if sym in s["pos"] or exited or not atr[i]:
            continue
        if mode == "flip":
            side = d[i] if d[i] and d[i - 1] and d[i] != d[i - 1] and reg[i] == d[i] else 0
        else:
            side = reg[i] if rng.random() < TWIN_P else 0
        if side in sides:
            open_pos(s, side, bars[i + 1]["o"], bars[i + 1]["t"], atr[i], f"{'Supertrend กลับทิศ' if mode == 'flip' else 'สุ่มเวลา'} "
                     f"{'ขึ้น' if side > 0 else 'ลง'} EMA50 รายวัน {'บน' if reg[i] > 0 else 'ล่าง'}", sym)
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def fetch(sym):
    now = time.time() * 1000
    raw = json.loads(urllib.request.urlopen(urllib.request.Request(URL.format(sym), headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())
    return [dict(t=k[0], o=float(k[1]), h=float(k[2]), l=float(k[3]), c=float(k[4]), closed=k[6] < now) for k in raw]


def load(f, label):
    try:
        return json.load(open(f))
    except (OSError, ValueError):
        return new_state(label)


def save(f, s):
    json.dump(s, open(f + ".tmp", "w"), ensure_ascii=False, indent=1)
    os.replace(f + ".tmp", f)


def main(cmd):
    if cmd == "report":
        for f in ACCOUNTS:
            s = load(f, "")
            v = s["cash"] + sum(p["qty"] * p["last"] for p in s["pos"].values())
            sells = [x for x in s["log"] if x["kind"] == "sell"]
            print(f"{f[6:-5]:<14} {v / s['start_usd'] - 1:+.1%}  ไม้ปิด {len(sells)}  เปิดอยู่ {list(s['pos'].values())[0]['side'] if s['pos'] else '-'}")
        return
    rng, cache = random.Random(), {}
    for f, (sides, mode, label, sym) in ACCOUNTS.items():
        if sym not in cache:
            try:
                cache[sym] = fetch(sym)
            except Exception as e:
                print("byttrade fetch failed", sym, type(e).__name__)
                cache[sym] = None
        if cache[sym]:
            s = load(f, label)
            process(s, cache[sym], sides, mode, rng, sym)
            save(f, s)

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "run")
