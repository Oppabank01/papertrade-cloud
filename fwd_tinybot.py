#!/usr/bin/env python3
"""Forward paper test of "Tiny Bot: Snap-Back + Trend Ride" (h05meigames/makefun-tiny-bot-gorun, GitHub 25 Nov 2026: a
make.fun bounty entry for hourly Solana bars, +3.17% vs buy-and-hold -8.69% on the kit's 136-bar dev window) on the four
of its seven coins that Binance spot lists (opened 27 Nov 2026 by the scout; backtest in LABEL, opened at any p because
the user asked to try weak ideas too). Fake money only.

On closed 1h Binance bars, long only, the repo's rules (README "Strategy"):
  EMA6 / EMA24 seeded as the mean of their first span of closes, RSI10 Wilder, r12 = close / close 12 bars ago - 1.
  Entry A (snap-back): RSI10 < 32 and close < EMA24 * 0.98 and r12 < -3%.
  Entry B (trend ride): EMA6 crosses above EMA24 on this bar and r12 > +2%.
  Exit the whole position when RSI10 > 65, or close >= entry * 1.10, or close <= entry * 0.88, or EMA6 crosses below EMA24.
Mine: every signal is read on a closed bar and filled at the next bar's open (the repo's kit fills by its own grader);
TP and stop are read on closes, as the repo does, so a bar can close far past -12%; Binance spot has no FARTCOIN, POPCAT
or JITOSOL, so the coins are SOL, ETH (for WETH), WIF and RAY; one quarter of the start per coin instead of the repo's
equity / slots with a 25% cap; 0.35% per side as every account here.
  state_fwd_tinybot.json       SOL ETH WIF RAY
  state_fwd_tinybot_twin.json  control: random entry bars (TWIN_P per free bar), same exits
  python3 fwd_tinybot.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                                   # per side, as every account here
SYMS = ["SOLUSDT", "ETHUSDT", "WIFUSDT", "RAYUSDT"]   # my choice: the repo's coins that Binance spot lists
RSI_IN, BELOW, DROP, RISE = 32, 0.98, -0.03, 0.02     # the repo's entry numbers
RSI_OUT, TP, SL = 65, 1.10, 0.88                       # the repo's exit numbers
WARM = 300                     # my choice: window bars that settle EMA24 and RSI10 before an entry counts
H1 = 3600 * 1000
TWIN_P = 1 / 70                # my choice: about the backtest's rate (one entry per 56 to 94 bars)
LABEL = ("Tiny Bot snap-back + trend ride 1 ชม. (h05meigames งาน make.fun) SOL ETH WIF RAY: ซื้อเมื่อ RSI10 ต่ำกว่า 32 "
         "ปิดต่ำกว่า EMA24 2% และ 12 ชม. ลง 3%+ หรือ EMA6 ตัดขึ้น EMA24 และ 12 ชม. ขึ้น 2%+ ขายเมื่อ RSI10 เกิน 65 ปิด +10% "
         "ปิด -12% หรือ EMA6 ตัดลง (backtest Binance 1 ชม. ถึง 27 พ.ย. 69 หลังหัก 0.35%/ข้าง: SOL 787 ไม้ -0.30% ก่อนหัก +0.40% "
         "ETH 863 ไม้ -0.44% WIF 428 ไม้ -0.77% RAY 737 ไม้ -0.61% ตัวแฝดสุ่ม -0.56 -0.70 -0.99 -0.51% ตั้งแต่ 2025 "
         "-0.64 -0.87 -1.17 -0.53% permutation 200 รอบบน 6,000 แท่งล่าสุด p SOL 0.94 ETH 0.95 WIF 0.27 RAY 0.27 ไม่ผ่าน)")
ACCOUNTS = {"state_fwd_tinybot.json": ("rule", LABEL),
            "state_fwd_tinybot_twin.json": ("random", "Tiny Bot 1 ชม. ตัวควบคุม: เข้าแท่งสุ่ม ออกด้วย RSI10 65 TP 10% SL 12% EMA ตัดลงแบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ema_seeded(c, n):
    out = [None] * len(c)
    if len(c) < n:
        return out
    e = sum(c[:n]) / n
    out[n - 1] = e
    k = 2 / (n + 1)
    for i in range(n, len(c)):
        e = c[i] * k + e * (1 - k)
        out[i] = e
    return out


def rsi_wilder(c, n=10):
    out, ag, al = [None] * len(c), 0.0, 0.0
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        g, l = max(d, 0), max(-d, 0)
        if i <= n:
            ag += g / n; al += l / n
        else:
            ag = (ag * (n - 1) + g) / n; al = (al * (n - 1) + l) / n
        if i >= n:
            out[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def ind(b):   # same as the scout's /tmp/scout_1959/tiny.py ind()
    c = [x["c"] for x in b]
    return ema_seeded(c, 6), ema_seeded(c, 24), rsi_wilder(c, 10), c


def entry_sig(i, e6, e24, rsi, c):
    if i < 25 or e24[i - 1] is None or rsi[i] is None:
        return None
    r12 = c[i] / c[i - 12] - 1
    if rsi[i] < RSI_IN and c[i] < e24[i] * BELOW and r12 < DROP:
        return "A"
    if e6[i] > e24[i] and e6[i - 1] <= e24[i - 1] and r12 > RISE:
        return "B"
    return None


def exit_sig(i, entry, e6, e24, rsi, c):
    if rsi[i] > RSI_OUT:
        return "RSI10 เกิน 65"
    if c[i] >= entry * TP:
        return "ปิด +10%"
    if c[i] <= entry * SL:
        return "ปิด -12%"
    if e6[i] < e24[i] and e6[i - 1] >= e24[i - 1]:
        return "EMA6 ตัดลง EMA24"
    return None


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
    e6, e24, rsi, c = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p:
            if x["t"] >= p["entry_t"]:
                why = exit_sig(i, p["entry"], e6, e24, rsi, c)
                if why:
                    close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], why)
            continue
        if i < WARM:
            continue
        k = entry_sig(i, e6, e24, rsi, c) if mode == "rule" else ("R" if rng.random() < TWIN_P else None)
        if not k:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = {"A": f"snap-back RSI10 {rsi[i]:.1f}", "B": "EMA6 ตัดขึ้น EMA24 12 ชม. ขึ้น 2%+", "R": "สุ่มแท่ง"}[k]
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / en, entry=en, last=en, usd=usd, entry_t=et, t=iso(et), why=why,
                             stop_set=round(en * SL, 8))
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=en, usd=usd, why=why,
                             stop_set=round(en * SL, 8)))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_tinybot fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
