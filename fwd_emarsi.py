#!/usr/bin/env python3
"""Forward paper test of NongNuea_Trojan's "1h price action cross EMA20/50 + RSI14 cross its smooth line" (X, May 2026,
a "$1,000 to $30,000" thread; no exit numbers posted) in its closest mechanical form, on BTC, ETH, SOL (opened 24 Nov
2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too). Fake money only.

On closed 1h Binance bars: close above EMA20 and EMA50 and RSI14 (Wilder) above its SMA14, all three true now but not
on the bar before -> long at the next open; all three the other way -> short. Stop 1.5 ATR14, target 3 ATR, from the
signal bar's ATR, checked on bar high/low from the entry bar on (gap through -> open, both touched -> stop); else out
at the close of the 48th bar. The post's volatility filter has no numbers, so it is left out.
One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_emarsi.json       BTC, ETH, SOL
  state_fwd_emarsi_twin.json  control: random entry bars (TWIN_P per free bar), random side, same exits
  python3 fwd_emarsi.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
H1 = 3600 * 1000
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice; the thread trades several coins (ETH, HYPE, ...)
SMOOTH = 14                    # my choice: TradingView's default RSI smoothing (SMA 14)
SL, TP, HOLD = 1.5, 3.0, 48    # my choices: the post says "TP and trailing stop" without numbers; 2R target, 2 days cap
TWIN_P = 1 / 8                 # my choice: about the rule's signal rate in the backtest (0.127 of BTC 1h bars)
LABEL = ("EMA20/50 + RSI ตัดเส้นเรียบ 1 ชม. (NongNuea_Trojan) BTC ETH SOL: ปิดเหนือ EMA20 และ EMA50 และ RSI14 เหนือ SMA14 "
         "ของมันครบครั้งแรก long (short กลับกัน) stop 1.5 ATR เป้า 3 ATR ถือไม่เกิน 48 แท่ง (เลขออกผมเลือกเอง) "
         "(backtest Binance 1 ชม. 2017-2026 หลังหัก 0.35%/ข้าง BTC 3,686 ไม้ -0.76% ETH 3,673 ไม้ -0.69% SOL 2,562 ไม้ -0.72% "
         "ต่อไม้ ก่อนหักราว 0% เท่าเข้าสุ่ม permutation 200 รอบบน 3 ปีล่าสุด p 0.866/0.622/0.124)")
ACCOUNTS = {"state_fwd_emarsi.json": ("rule", LABEL),
            "state_fwd_emarsi_twin.json": ("random", "EMA20/50 + RSI ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งสุ่ม stop 1.5 ATR เป้า 3 ATR ถือไม่เกิน 48 แท่งแบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ema(c, n):
    out, e, k = [None] * len(c), None, 2 / (n + 1)
    for i, v in enumerate(c):
        e = v if e is None else e + k * (v - e)
        out[i] = e
    return out


def ind(b):   # same as the scout's /tmp/scout_s24/bt.py (ema, rsi, watr, sig_emarsi)
    c, n = [x["c"] for x in b], len(b)
    e20, e50, r, atr, ag, al, a = ema(c, 20), ema(c, 50), [None] * n, [None] * n, 0.0, 0.0, None
    for i in range(1, n):
        d = c[i] - c[i - 1]; g, l = max(d, 0), max(-d, 0)
        if i <= 14:
            ag += g / 14; al += l / 14
        else:
            ag = (ag * 13 + g) / 14; al = (al * 13 + l) / 14
        if i >= 14:
            r[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
        tr = max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - c[i - 1]), abs(b[i]["l"] - c[i - 1]))
        a = tr if a is None else a + (tr - a) / 14
        if i >= 14:
            atr[i] = a
    sm = [None] * n
    for i in range(28, n):
        sm[i] = sum(r[i - SMOOTH + 1:i + 1]) / SMOOTH
    up = [sm[i] is not None and c[i] > e20[i] and c[i] > e50[i] and r[i] > sm[i] for i in range(n)]
    dn = [sm[i] is not None and c[i] < e20[i] and c[i] < e50[i] and r[i] < sm[i] for i in range(n)]
    sig = [0] * n
    for i in range(60, n):   # 60: my warm-up for EMA50
        sig[i] = 1 if up[i] and not up[i - 1] else -1 if dn[i] and not dn[i - 1] else 0
    return sig, atr


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
    sig, atr = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            o, h, l, d = x["o"], x["h"], x["l"], p["d"]
            hit = (o if o <= p["stop"] else p["stop"] if l <= p["stop"] else max(p["tgt"], o) if h >= p["tgt"] else None) if d > 0 else \
                  (o if o >= p["stop"] else p["stop"] if h >= p["stop"] else min(p["tgt"], o) if l <= p["tgt"] else None)
            p["held"] = p.get("held", 0) + 1      # closed bars from the entry bar on, counted like the backtest
            if hit is not None:
                close(s, sym, hit, x["t"] + H1, "stop" if (hit - p["entry"]) * d < 0 else "ถึงเป้า 3 ATR")
                exited = True
            elif p["held"] >= HOLD:
                close(s, sym, x["c"], x["t"] + H1, "ถือครบ 48 แท่ง")
                exited = True
        if sym in s["pos"] or exited or not atr[i]:
            continue
        if mode == "rule":
            d = sig[i]
        else:
            d = rng.choice((1, -1)) if i >= 60 and rng.random() < TWIN_P else 0
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "ปิดข้าม EMA20/50 และ RSI ตัดเส้นเรียบ" if mode == "rule" else "สุ่มแท่ง ฝั่งสุ่ม"
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=e - d * SL * atr[i], tgt=e + d * TP * atr[i], entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_emarsi fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
