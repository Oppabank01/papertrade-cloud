#!/usr/bin/env python3
"""Forward paper test of the "Crypto Desk" Analyst score (ramz1ss/binance-auto-trading-bot, GitHub 25 Nov 2026: a six-agent
rule-based Binance spot bot, paper mode by default) on 10 Binance majors (opened 27 Nov 2026 by the scout; backtest in LABEL,
opened at any p because the user asked to try weak ideas too). Fake money only.

On closed 1h Binance bars, long only, the repo's defaults (desk/analyst.py, desk/risk.py, config.example.toml):
  mom   = 0.5*clip(0.5 + r6h/0.08) + 0.5*clip(0.5 + r24h/0.20), times 0.8 when RSI14 (Wilder) > 75
  trend = 0.35*[close > EMA20] + 0.35*[EMA20 > EMA50] + 0.30*clip(0.5 + (EMA50 / EMA50 12 bars ago - 1)/0.02)
  score = 0.40*mom + 0.35*trend + 0.25*vol; BUY at the next open when score >= 0.6 and the coin is flat.
  Exit: stop -8% below entry; once the peak (bar highs) reaches +10%, stop = max(stop, peak*0.95), only upward. Each bar
  checks the low first (repo _apply): low <= stop sells at min(stop, open). No take-profit, no time limit.
  After a sell the coin waits one more bar (repo reentry_cooldown_min 60).
Mine: byttrade.fetch has no volume, so vol is fixed at a neutral 0.5 and the repo's 24h-volume filter is dropped; 1h bars
instead of the repo's 5-minute scan with 1-minute stop checks; 10 fixed coins instead of the top-20-by-volume universe;
no 3-position cap; one tenth of the start per coin; 0.35% per side as every account here.
  state_fwd_desk.json       BTC ETH SOL BNB XRP ADA DOGE AVAX LINK LTC
  state_fwd_desk_twin.json  control: random entry bars (TWIN_P per free bar), same stop and trail
  python3 fwd_desk.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT"]  # my choice
MIN_SCORE, STOP, ACT, TRAIL = 0.6, 0.08, 0.10, 0.05   # the repo's defaults
VOL_NEUTRAL = 0.5              # my choice: no volume from byttrade.fetch
WARM = 500                     # my choice: bars of the window used to settle EMA50 and RSI before a score counts
H1 = 3600 * 1000
TWIN_P = 1 / 35                # my choice: about the backtest's rate (one entry per 31 to 47 free bars)
LABEL = ("Crypto Desk คะแนน momentum+trend 1 ชม. (ramz1ss) 10 เหรียญ: ซื้อเมื่อคะแนน 0.4 momentum (6/24 ชม.) + 0.35 trend "
         "(EMA20/50) + 0.25 x 0.5 ถึง 0.6 stop -8% เมื่อขึ้นถึง +10% ตาม 5% จากยอด (backtest Binance 1 ชม. 2017 ถึง 27 พ.ย. 69 "
         "หลังหัก 0.35%/ข้าง ไม่มี volume: BTC 303 ไม้ +0.31% ETH -0.12% SOL -0.28% BNB +0.07% XRP -0.82% ADA -0.96% DOGE -0.57% "
         "AVAX -0.69% LINK -0.64% LTC -1.11% มัธยฐาน -8.6% ทุกเหรียญ ชนะตัวแฝดสุ่ม 7 ใน 10 แบบเฉียด ตั้งแต่ 2025 -0.8 ถึง -2.1% "
         "ยกเว้น BNB +0.56% permutation 200 รอบบน 6,000 แท่งล่าสุด กริด 2 แบบ (มี/ไม่มี volume) p ต่ำสุด BTC 0.020 ADA 0.035 "
         "ไม่มีเหรียญไหนต่ำกว่า 0.01)")
ACCOUNTS = {"state_fwd_desk.json": ("rule", LABEL),
            "state_fwd_desk_twin.json": ("random", "Crypto Desk 1 ชม. ตัวควบคุม: เข้าแท่งสุ่ม stop -8% ตาม 5% เมื่อขึ้น +10% แบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def clip(x):
    return max(0.0, min(1.0, x))


def scores(b, warm=WARM):
    """score per bar (None before warm); same as the scout's /tmp/scout_1457/desk.py scores(use_vol=False)"""
    n, c = len(b), [x["c"] for x in b]
    e20, e50, rsi = [c[0]] * n, [c[0]] * n, [50.0] * n
    ag = al = 0.0
    for i in range(1, n):
        e20[i] = c[i] * 2 / 21 + e20[i - 1] * (1 - 2 / 21)
        e50[i] = c[i] * 2 / 51 + e50[i - 1] * (1 - 2 / 51)
        d = c[i] - c[i - 1]
        g, l = max(d, 0), max(-d, 0)
        if i <= 14:
            ag += g / 14; al += l / 14
        else:
            ag = (ag * 13 + g) / 14; al = (al * 13 + l) / 14
        if i >= 14:
            rsi[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    out = [None] * n
    for i in range(max(warm, 24), n):
        mom = 0.5 * clip(0.5 + (c[i] / c[i - 6] - 1) / 0.08) + 0.5 * clip(0.5 + (c[i] / c[i - 24] - 1) / 0.20)
        if rsi[i] > 75:
            mom *= 0.8
        trend = 0.35 * (c[i] > e20[i]) + 0.35 * (e20[i] > e50[i]) + 0.30 * clip(0.5 + (e50[i] / e50[i - 12] - 1) / 0.02)
        out[i] = 0.40 * mom + 0.35 * trend + 0.25 * VOL_NEUTRAL
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen, cool = s.setdefault("seen", {}), s.setdefault("cool", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    sc = scores(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p:
            if x["t"] >= p["entry_t"]:
                if x["l"] <= p["stop"]:
                    why = f"trail 5% จากยอด {p['peak']:.6g}" if p["trailing"] else "stop -8%"
                    close(s, sym, min(p["stop"], x["o"]), x["t"] + H1, why)
                    cool[sym] = x["t"] + H1
                    continue
                p["peak"] = max(p["peak"], x["h"])
                if p["peak"] >= p["entry"] * (1 + ACT):
                    p["trailing"] = True
                    p["stop"] = max(p["stop"], p["peak"] * (1 - TRAIL))
            continue
        if x["t"] < cool.get(sym, 0):
            continue
        ok = (sc[i] is not None and sc[i] >= MIN_SCORE) if mode == "rule" else rng.random() < TWIN_P
        if not ok:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = f"คะแนน {sc[i]:.3f} ถึง 0.6" if mode == "rule" else "สุ่มแท่ง"
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / en, entry=en, last=en, usd=usd, entry_t=et, t=iso(et), why=why,
                             stop=en * (1 - STOP), peak=en, trailing=False)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=en, usd=usd, why=why,
                             stop_set=round(en * (1 - STOP), 8)))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_desk fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
