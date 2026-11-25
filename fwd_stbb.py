#!/usr/bin/env python3
"""Forward paper test of the "Supertrend + Bollinger Band MID gate" scalper (dy6z/supertrend-binance-bot,
supertrend_bb_crypto_scanner.py and binance_sl_watchdog.py, Binance futures 15m, README claims 30 days 428 trades
+99% win 60.5% PF 1.27 at $20 margin x10), opened 26 Nov 2026 by the scout; backtest in LABEL, opened at any p because
the user asked to try weak ideas too. Fake money only.

On closed 15m bars: Supertrend (ATR 10 Wilder, x3, hl2) flips on the bar, the close is at least 2% from the new
Supertrend line, RSI14 (simple averages, as the scanner) is 55-65 for a long or 35-45 for a short, and the close
crossed the SMA20 (BB mid) the same way on this bar or up to 3 bars before -> enter at the next open. Exit inside each
bar: target +1.8% from the entry, stop at the Supertrend line of the last closed bar or 3% from the entry, whichever
is nearer; a close through the line closes at the next open; gap through the stop fills at the open; both touched =
stop. One position per coin, 1/22 of the start per coin, 0.35% per side.
  state_fwd_stbb.json       22 coins of the scanner that Binance spot lists
  state_fwd_stbb_twin.json  control: random entry times (1 in 250 free bars) in the Supertrend direction, same exits
  python3 fwd_stbb.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                 # per side, as every account here
M15 = 15 * 60 * 1000
ST_N, ST_M, BB_N, RSI_N = 10, 3.0, 20, 14            # from the scanner PARAMS
DIST, RLO, RSH, GAP = 0.02, (55, 65), (35, 45), 3      # from the scanner (min_st_distance_pct, RSI gates, grade B window)
TP, HARD = 0.018, 0.03                                 # from the scanner (max_tp_percent, hard_stop_pct)
TWIN_P = 1 / 250              # my choice: about as often as the rule fires per coin
# my choices: Binance spot instead of USDT-M futures, 1000PEPE read as PEPE, SNDK INIT SNXX SOXS dropped (no spot pair),
# taker entry at the next 15m open instead of a market order a minute after the close, the watchdog's every-minute stop
# check modelled as a touch inside the bar, the -3% hard stop applied as the nearer of the two stops, no leverage
SYMS = ["ZECUSDT", "SOLUSDT", "PEOPLEUSDT", "TIAUSDT", "TAOUSDT", "JUPUSDT", "GRTUSDT", "FETUSDT", "OPUSDT", "ARBUSDT",
        "INJUSDT", "XRPUSDT", "PEPEUSDT", "ENAUSDT", "UNIUSDT", "ADAUSDT", "LINKUSDT", "SUIUSDT", "WLDUSDT", "DOGEUSDT",
        "NEARUSDT", "ETHUSDT"]
LABEL = ("Supertrend + BB mid 15 นาที (dy6z บอท scalping) 22 เหรียญ: Supertrend กลับทิศ ห่างเส้น 2%+ RSI 55-65 (short 35-45) "
         "ตัด SMA20 ทางเดียวกันภายใน 3 แท่ง เป้า +1.8% stop เส้น Supertrend หรือ 3% (backtest Binance 15 นาที 180 วัน "
         "หลังหัก 0.35%/ข้าง 1,374 ไม้ -0.67% ต่อไม้ ก่อนหัก +0.03% ชนะ 52% ตัวแฝดเข้าสุ่ม -0.71% 30 วันล่าสุด 266 ไม้ "
         "-0.38% ชนะ 60% permutation 200 รอบ 6 เหรียญ กริด 9 แบบ p 0.57 ไม่ผ่าน)")
ACCOUNTS = {"state_fwd_stbb.json": ("rule", LABEL),
            "state_fwd_stbb_twin.json": ("random", "Supertrend + BB mid ตัวควบคุม: เข้าสุ่มเวลาตามทิศ Supertrend ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="15m"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ind(b):   # same as the scout's /tmp/scout_0216/bt_st.py ind(): the scanner's Supertrend, SMA20 and simple RSI14
    n, c = len(b), [x["c"] for x in b]
    trend, lo, up, atr = [1] * n, [0.0] * n, [0.0] * n, 0.0
    for i in range(n):
        tr = b[i]["h"] - b[i]["l"] if i == 0 else max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - c[i - 1]), abs(b[i]["l"] - c[i - 1]))
        atr = tr if i == 0 else atr + (tr - atr) / ST_N
        hl2 = (b[i]["h"] + b[i]["l"]) / 2
        ub, lb = hl2 + ST_M * atr, hl2 - ST_M * atr
        if i == 0:
            up[i], lo[i] = ub, lb
            continue
        up[i] = min(ub, up[i - 1]) if c[i - 1] < up[i - 1] else ub
        lo[i] = max(lb, lo[i - 1]) if c[i - 1] > lo[i - 1] else lb
        trend[i] = (-1 if c[i] < lo[i] else 1) if trend[i - 1] == 1 else (1 if c[i] > up[i] else -1)
    mid, s = [None] * n, 0.0
    for i in range(n):
        s += c[i]
        if i >= BB_N:
            s -= c[i - BB_N]
        if i >= BB_N - 1:
            mid[i] = s / BB_N
    rsi, g, l, sg, sl = [None] * n, [0.0] * n, [0.0] * n, 0.0, 0.0
    for i in range(1, n):
        d = c[i] - c[i - 1]
        g[i], l[i] = max(d, 0), max(-d, 0)
        sg += g[i]; sl += l[i]
        if i > RSI_N:
            sg -= g[i - RSI_N]; sl -= l[i - RSI_N]
        if i >= RSI_N and sl > 0:
            rsi[i] = 100 - 100 / (1 + sg / sl)
    return trend, lo, up, mid, rsi


def signal(b, i, I):
    trend, lo, up, mid, rsi = I
    if i < 60 or trend[i] == trend[i - 1] or rsi[i] is None:
        return 0
    d, c = trend[i], b[i]["c"]
    line = lo[i] if d == 1 else up[i]
    if (c - line) / c * d < DIST:
        return 0
    lo_r, hi_r = RLO if d == 1 else RSH
    if not lo_r <= rsi[i] <= hi_r:
        return 0
    for ix in range(i, i - GAP - 1, -1):
        if mid[ix] is None or mid[ix - 1] is None:
            return 0
        cc, pc = b[ix]["c"], b[ix - 1]["c"]
        if (d == 1 and cc > mid[ix] and pc <= mid[ix - 1]) or (d == -1 and cc < mid[ix] and pc >= mid[ix - 1]):
            return d
    return 0


def exit_px(b, j, I, d, e):
    """price and reason if the position (direction d, entry e) closes during bar j, else (None, None)."""
    trend, lo, up = I[0], I[1], I[2]
    x = b[j]
    if trend[j - 1] != d:
        return x["o"], "Supertrend กลับทิศ"
    stop = max(lo[j - 1], e * (1 - HARD)) if d == 1 else min(up[j - 1], e * (1 + HARD))
    tgt = e * (1 + d * TP)
    if d == 1:
        if x["o"] <= stop: return x["o"], "stop"
        if x["l"] <= stop: return stop, "stop"
        if x["h"] >= tgt: return max(tgt, x["o"]), "ถึงเป้า 1.8%"
    else:
        if x["o"] >= stop: return x["o"], "stop"
        if x["h"] >= stop: return stop, "stop"
        if x["l"] <= tgt: return min(tgt, x["o"]), "ถึงเป้า 1.8%"
    return None, None


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    I = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < 1:
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            px, why = exit_px(bars, i, I, p["d"], p["entry"])
            if px is not None:
                close(s, sym, px, x["t"] + M15, why)   # the scanner may open again on the same bar (a fresh flip)
        if sym in s["pos"]:
            continue
        if mode == "rule":
            d = signal(bars, i, I)
        else:
            d = I[0][i] if i >= 60 and rng.random() < TWIN_P else 0
        usd = s["start_usd"] / len(SYMS)
        if not d or (d > 0 and s["cash"] < usd * (1 + COST)):
            continue
        e = bars[i + 1]["o"]
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "Supertrend กลับทิศ + ตัด SMA20" if mode == "rule" else "สุ่มเวลา ตามทิศ Supertrend"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "15m")
        except Exception as e:
            print("fwd_stbb fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
