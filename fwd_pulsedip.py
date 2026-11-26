#!/usr/bin/env python3
"""Forward paper test of gurbanmradov/pulsebot "rsi_ema_dip" with its RiskManager exits (GitHub, 25 Nov 2026, a
stdlib-only backtest and paper engine; its defaults are BTCUSDT 1h) on BTC, ETH, SOL (opened 26 Nov 2026 by the scout;
backtest in LABEL, opened at any p because the user asked to try weak ideas too). Fake money only.

On closed 1h Binance bars, long only, the repo's defaults: RSI14 (Wilder) <= 35 and the close at or above EMA50 x 0.98
-> long at the next open. Every later closed bar, in the repo's order: close <= entry x 0.97 (stop); else the highest
close since entry >= entry x 1.05 and the close <= that high x 0.98 (trailing take-profit); else RSI14 >= 68 -> out at the
next open. No new entry until 3 bars after the exit bar. Indicators exactly as pulsebot/indicators.py (EMA seeded with
the SMA of the first 50 closes, RSI seeded with the first 14 moves) over the bars this script is given.
One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_pulsedip.json       BTC, ETH, SOL
  state_fwd_pulsedip_twin.json  control: random entry bars (TWIN_P per free bar), same exits and cooldown
  python3 fwd_pulsedip.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here (the repo uses 0.1% fee + 0.05% slippage)
H1 = 3600 * 1000
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the repo's default BTC plus the two coins it shows (SOL in the README)
RSI_N, EMA_N, RSI_BUY, RSI_SELL, TOL = 14, 50, 35.0, 68.0, 0.02   # the repo's defaults
SL, TP_ARM, TRAIL, COOL = 0.03, 0.05, 0.02, 3                    # the repo's RiskConfig defaults
TWIN_P = 1 / 150               # my choice: about the rule's entry rate (410 entries in 81,175 BTC 1h bars, about 1 in 200)
# also mine: fills at the next open in place of the signal close, size one third of the start per coin in place of 25% of
# equity, and the repo's daily 3% loss kill-switch left out (with a 3% close stop on a quarter of equity it barely binds)
LABEL = ("RSI ย่อในขาขึ้น 1 ชม. (gurbanmradov/pulsebot rsi_ema_dip ค่าเริ่มต้น) BTC ETH SOL: RSI14 ไม่เกิน 35 และปิดไม่ต่ำกว่า "
         "EMA50 ลบ 2% ซื้อ ออกเมื่อปิดต่ำกว่าทุน 3% หรือขึ้นถึง +5% แล้วย่อจากจุดสูงสุด 2% หรือ RSI14 ถึง 68 "
         "(backtest Binance 1 ชม. 2017 ถึง 26 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 410 ไม้ -0.58% ต่อไม้ มัธยฐาน +0.33% ชนะ 53% "
         "ETH 301 ไม้ -0.82% SOL 117 ไม้ -0.70% ตัวแฝดเข้าสุ่ม -0.66/-0.71/-0.91% ก่อนหักราว 0% "
         "permutation 200 รอบบน 20,000 แท่งล่าสุด กริด 6 แบบ (RSI 30/35/40 x EMA 50/200) p 0.920/0.602/0.731)")
ACCOUNTS = {"state_fwd_pulsedip.json": ("rule", LABEL),
            "state_fwd_pulsedip_twin.json": ("random", "RSI ย่อในขาขึ้น 1 ชม. ตัวควบคุม: เข้าแท่งสุ่ม ออกด้วย stop 3% trail และ RSI 68 แบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ema(v, p):   # pulsebot.indicators.ema
    out = [None] * len(v)
    if len(v) < p:
        return out
    prev, k = sum(v[:p]) / p, 2.0 / (p + 1)
    out[p - 1] = prev
    for i in range(p, len(v)):
        prev = v[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def _rs(g, l):
    if g == 0 and l == 0:
        return 50.0
    if l == 0:
        return 100.0
    return 100.0 - 100.0 / (1 + g / l)


def rsi(v, p=RSI_N):   # pulsebot.indicators.rsi (Wilder)
    n, out = len(v), [None] * len(v)
    if n <= p:
        return out
    g = l = 0.0
    for i in range(1, p + 1):
        d = v[i] - v[i - 1]
        g, l = g + max(d, 0), l + max(-d, 0)
    g, l = g / p, l / p
    out[p] = _rs(g, l)
    for i in range(p + 1, n):
        d = v[i] - v[i - 1]
        g, l = (g * (p - 1) + max(d, 0)) / p, (l * (p - 1) + max(-d, 0)) / p
        out[i] = _rs(g, l)
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    cool = s.setdefault("cool", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    c = [x["c"] for x in bars]
    r, e = rsi(c), ema(c, EMA_N)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p:
            if x["t"] < p["entry_t"]:
                continue
            p["hi"] = max(p["hi"], x["c"])
            why = ("ปิดต่ำกว่าทุน 3%" if x["c"] <= p["entry"] * (1 - SL) else
                   "ย่อ 2% จากจุดสูงสุดหลังขึ้น 5%" if p["hi"] >= p["entry"] * (1 + TP_ARM) and x["c"] <= p["hi"] * (1 - TRAIL) else
                   "RSI ถึง 68" if r[i] is not None and r[i] >= RSI_SELL else None)
            if why:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], why)
                cool[sym] = x["t"]
            continue
        if sym in cool and (x["t"] - cool[sym]) // H1 < COOL:
            continue
        if r[i] is None or e[i] is None:
            continue
        ok = (r[i] <= RSI_BUY and x["c"] >= e[i] * (1 - TOL)) if mode == "rule" else rng.random() < TWIN_P
        if not ok:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = f"RSI {r[i]:.1f} เหนือ EMA50 ลบ 2%" if mode == "rule" else "สุ่มแท่ง"
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / en, entry=en, last=en, hi=en, usd=usd, entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=en, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_pulsedip fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
