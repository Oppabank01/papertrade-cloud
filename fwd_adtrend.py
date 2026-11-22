#!/usr/bin/env python3
"""Forward paper test of the single-coin core of "AdaptiveTrend" (arXiv 2602.11708, 2026): momentum entry on 6h bars,
exit only on an ATR trailing stop, on BTC, ETH, SOL (opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p
because the user asked to try weak ideas too). Fake money only.

On closed 6h Binance bars, when flat: MOM = close / close L bars ago - 1; MOM > TH -> long, MOM < -TH -> short, at the next
open. Stop starts at signal close -/+ ALPHA x ATR14 and trails: each closed bar, if the close is through the stop -> out at
the next open, else stop = max(stop, close - ALPHA x ATR14) for a long (min(...) + for a short). No target, no time stop.
The paper re-fits L and TH monthly over 150 coins with a Sharpe filter; here L and TH are fixed (chosen in-sample, below).
One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_adtrend.json       BTC, ETH, SOL
  state_fwd_adtrend_twin.json  control: random entry bars (TWIN_P per free bar), random side, same trailing exit
  python3 fwd_adtrend.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch, wilder_atr

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # the paper used 150+ perps; these three are my choice
ALPHA = 2.5                        # the paper's stated optimum (plateau 2.0 to 3.5)
ATR_N = 14                         # my choice: the paper gives no ATR period
# grid tried in-sample (bars before 2024, BTC+ETH+SOL pooled): L 12/28/56 bars (3/7/14 days) x TH 0/5% = 6 settings
GRID = [(l, th) for l in (12, 28, 56) for th in (0.0, 0.05)]
L, TH = 12, 0.05                   # chosen: best pooled in-sample mean per trade after costs (+1.85%, 592 trades)
TWIN_P = 1 / 20                    # my choice: about the rule's re-entry rate once flat
LABEL = ("AdaptiveTrend 6 ชม. BTC ETH SOL (arXiv 2602.11708): โมเมนตัม 3 วันเกิน +5% long ต่ำกว่า -5% short ออกด้วย trailing 2.5 ATR "
         "(backtest 2017-2026 หลังหัก 0.35%/ข้าง BTC 296 ไม้ +0.93% p 0.015 ETH 353 ไม้ +0.40% p 0.020 SOL 255 ไม้ +2.52% p 0.005 "
         "มัธยฐานราว -3% ชนะ 37% ปี 2024+ BTC -0.55% ETH -0.38% SOL +0.42% ตัวแฝดสุ่ม -0.12/+0.08/+1.69%)")
ACCOUNTS = {"state_fwd_adtrend.json": ("rule", LABEL),
            "state_fwd_adtrend_twin.json": ("random", "AdaptiveTrend ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งสุ่ม ออกด้วย trailing 2.5 ATR แบบเดียวกัน")}


def fetch_iv(sym, iv="6h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def signal(b, i, l=L, th=TH):
    if i < l:
        return 0
    m = b[i]["c"] / b[i - l]["c"] - 1
    return 1 if m > th else -1 if m < -th else 0


def trail(p, c, a):
    """One closed bar against an open position p (dict with d, stop): True = out at the next open, else ratchet the stop."""
    if (c - p["stop"]) * p["d"] < 0:
        return True
    p["stop"] = max(p["stop"], c - ALPHA * a) if p["d"] > 0 else min(p["stop"], c + ALPHA * a)
    return False


def trades(b, l=L, th=TH, first=60, atr=None):
    """The backtest (the scout's /tmp/scout_0613.py calls this): list of dict(t, d, e, x), oldest first."""
    atr, out, p = atr or wilder_atr(b, ATR_N), [], None
    for i in range(first, len(b) - 1):
        if p and b[i]["t"] >= p["t"]:
            if trail(p, b[i]["c"], atr[i]):
                out.append(dict(t=p["t"], d=p["d"], e=p["e"], x=b[i + 1]["o"]))
                p = None
            continue
        if p or atr[i] is None:
            continue
        d = signal(b, i, l, th)
        if d:
            p = dict(t=b[i + 1]["t"], d=d, e=b[i + 1]["o"], stop=b[i]["c"] - d * ALPHA * atr[i])
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
    atr = wilder_atr(bars, ATR_N)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            if trail(p, x["c"], atr[i]):
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], f"หลุด trailing {ALPHA:g} ATR")
            continue
        if p or atr[i] is None:
            continue
        d = signal(bars, i) if mode == "rule" else (rng.choice((1, -1)) if rng.random() < TWIN_P else 0)
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = (f"โมเมนตัม {L} แท่ง {x['c'] / bars[i - L]['c'] - 1:+.1%}" if mode == "rule" else "สุ่มแท่ง สุ่มฝั่ง")
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=x["c"] - d * ALPHA * atr[i], entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "6h")
        except Exception as e:
            print("fwd_adtrend fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
