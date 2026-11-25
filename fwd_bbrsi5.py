#!/usr/bin/env python3
"""Forward paper test of indrairawan4503-cmd/btc-race-24h-20261123-0511-entry (GitHub, Nov 2026, a make.fun "Race a BTC
trading bot live for 24 hours" entry): Bollinger + RSI mean reversion on 5m bars, long only. Opened 25 Nov 2026 by the
scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 5m Binance bars (the repo's main.ts): close at or below the lower Bollinger band (20 bars, 1.5 sigma) and
RSI14 <= 30 and the close above the previous close -> long at the next open, except while the close is more than 1.5%
below its 30-bar SMA unless RSI14 <= 22. Target max(upper band of the signal bar, entry +0.8%), hard stop 2 ATR14 under
the entry, once a bar's high has reached +0.5% the stop moves up to +0.2% from the next bar on, out at the close of the
48th bar (4 h). Each bar: a gap through the stop fills at the open, then the stop, then the target (both touched = stop).
One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_bbrsi5.json       BTC, ETH, SOL
  state_fwd_bbrsi5_twin.json  control: random entry bars (1 in 300 free bars), the same exits
  python3 fwd_bbrsi5.py"""
import math, random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
M5 = 5 * 60 * 1000
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the repo trades only cbBTC; ETH and SOL as every scout account
BB_N, BB_K, RSI_MAX, RSI_EXTREME = 20, 1.5, 30, 22      # from the repo
TREND_N, TREND_GAP = 30, 0.015                          # from the repo
TP_MIN, LOCK_AT, LOCK, ATR_K, MAXB = 0.008, 0.005, 0.002, 2.0, 48   # from the repo (4 h = 48 bars of 5m)
TWIN_P = 1 / 300                       # my choice: a few times the rule's entry rate so the control fills sooner
# also mine: the repo checks the hard stop on every 1m bar and sizes 30% of equity capped at 1.5% risk; here everything is
# checked on 5m bars and each coin gets a fixed third of the start
LABEL = ("BB+RSI 5 นาที (indrairawan4503 บอทแข่ง make.fun) BTC ETH SOL: ปิดแตะขอบล่าง BB 20/1.5 RSI ไม่เกิน 30 แท่งปิดสูงกว่าแท่งก่อน "
         "เป้าขอบบนหรือ +0.8% stop 2 ATR ล็อก +0.2% เมื่อขึ้น 0.5% ถือไม่เกิน 4 ชม. "
         "(backtest Binance 5 นาที 365 วันถึง 25 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 410 ไม้ -0.71% ETH 383 ไม้ -0.77% "
         "SOL 355 ไม้ -0.72% ต่อไม้ ก่อนหัก -0.01/-0.07/-0.02% ชนะ 10-12% ตัวแฝดเข้าสุ่ม -0.70/-0.68/-0.68% "
         "permutation 200 รอบ p 0.79/1.00/0.73 ไม่ผ่าน ติดลบทุกเดือน ช่วงนั้นถือเฉยๆ -33 ถึง -50%)")
ACCOUNTS = {"state_fwd_bbrsi5.json": ("rule", LABEL),
            "state_fwd_bbrsi5_twin.json": ("random", "BB+RSI 5 นาที ตัวควบคุม: เข้าแท่งสุ่ม ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="5m"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def wilder(vals, n):
    out, a = [None] * len(vals), None
    for i, v in enumerate(vals):
        if v is None:
            continue
        a = v if a is None else (a * (n - 1) + v) / n
        out[i] = a
    return out


def ind(b):   # same as the scout's /tmp/scout_1351/bt.py ind_a (exact windows here, rolling sums there)
    c, n = [x["c"] for x in b], len(b)
    mid, sd, sma = [None] * n, [None] * n, [None] * n
    for i in range(TREND_N - 1, n):
        w = c[i - BB_N + 1:i + 1]
        m = sum(w) / BB_N
        mid[i], sd[i], sma[i] = m, math.sqrt(sum((v - m) ** 2 for v in w) / BB_N), sum(c[i - TREND_N + 1:i + 1]) / TREND_N
    ag = wilder([None] + [max(c[i] - c[i - 1], 0) for i in range(1, n)], 14)
    al = wilder([None] + [max(c[i - 1] - c[i], 0) for i in range(1, n)], 14)
    rsi = [None] * 15 + [100 if al[i] == 0 else 100 - 100 / (1 + ag[i] / al[i]) for i in range(15, n)]
    atr = wilder([None] + [max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - c[i - 1]), abs(b[i]["l"] - c[i - 1])) for i in range(1, n)], 14)
    return mid, sd, sma, rsi, atr


def signal(b, i, I):
    mid, sd, sma, rsi, atr = I
    if i < TREND_N or mid[i] is None or rsi[i] is None or atr[i] is None:
        return False
    c = b[i]["c"]
    if not (c <= mid[i] - BB_K * sd[i] and rsi[i] <= RSI_MAX and c > b[i - 1]["c"]):
        return False
    return not (c < sma[i] * (1 - TREND_GAP) and rsi[i] > RSI_EXTREME)


def new_pos(e, i, I):
    mid, sd, _, _, atr = I
    return dict(stop=e - ATR_K * atr[i], tgt=max(mid[i] + BB_K * sd[i], e * (1 + TP_MIN)), armed=False, n=0)


def exit_px(p, x, e):
    """Exit price on bar x or None; arms the lock for the next bar. Same order as the backtest's leg_a()."""
    p["n"] += 1
    if x["o"] <= p["stop"]:
        return x["o"], "stop"
    if x["l"] <= p["stop"]:
        return p["stop"], "stop" if p["stop"] < e else "ล็อกกำไร +0.2%"
    if x["h"] >= p["tgt"]:
        return max(p["tgt"], x["o"]), "ถึงเป้า"
    if not p["armed"] and x["h"] >= e * (1 + LOCK_AT):
        p["armed"], p["stop"] = True, max(p["stop"], e * (1 + LOCK))
    if p["n"] >= MAXB:
        return x["c"], "ครบ 4 ชม."
    return None


def trades(b):
    """The backtest (same trades as the scout's /tmp/scout_1351/bt.py run_a): list of (entry bar, entry, exit bar, exit)."""
    I, out, i = ind(b), [], TREND_N
    while i < len(b) - 1:
        if not signal(b, i, I):
            i += 1; continue
        e = b[i + 1]["o"]
        p, j, px = new_pos(e, i, I), i + 1, None
        while j < len(b):
            r = exit_px(p, b[j], e)
            if r:
                px = r[0]; break
            j += 1
        if px is None:
            break
        out.append((i + 1, e, j, px)); i = j + 1
    return out


def close(s, sym, px, t, why):   # as pullback.close
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
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            r = exit_px(p["leg"], x, p["entry"])
            if r:
                close(s, sym, r[0], x["t"] + M5, r[1])
                exited = True
        if sym in s["pos"] or exited or i < TREND_N or I[4][i] is None:
            continue
        go = signal(bars, i, I) if mode == "rule" else rng.random() < TWIN_P
        if not go:
            continue
        e, t, usd = bars[i + 1]["o"], bars[i + 1]["t"], s["start_usd"] / 3
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "แตะขอบล่าง BB RSI ต่ำ แท่งเด้ง" if mode == "rule" else "สุ่มเวลา"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, leg=new_pos(e, i, I),
                             entry_t=t, t=iso(t), why=why)
        s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_bbrsi5 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
