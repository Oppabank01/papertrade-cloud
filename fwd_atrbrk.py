#!/usr/bin/env python3
"""Forward paper test of the "Supertrend + RSI" rule of salainiyo/public-trading-engine (a prop-firm XAUUSD H1 bot; the
README calls it supertrend but it is an ATR(10) band plus a 20-bar breakout), moved to Binance 4h coins and PAXG (gold).
Opened 24 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too.
Fake money only.

On closed 4h bars: band = (high + low) / 2 - 3 * ATR10. Close above the prior 20-bar high, above the band and RSI14 > 60
-> long; close below the prior 20-bar low, below the band and RSI14 < 40 -> short. Enter at the next open, stop
SL_ATR * ATR14, target RR times the stop, checked on closed 4h bars; a gap through the stop fills at the open; both
touched = stop. The short leg is the repo's literal rule (close below the LOWER band) and never fired in the
backtest (0 shorts on all six coins), so in practice this is long only. One position per coin, one sixth of the start per coin, 0.35% per side.
  state_fwd_atrbrk.json       BTC, ETH, SOL, BNB, XRP, PAXG
  state_fwd_atrbrk_twin.json  control: random long entries (TWIN_P per free bar), same exits
  python3 fwd_atrbrk.py"""
import random
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "PAXGUSDT"]   # my choice: 5 large coins + PAXG for the gold original
LOOK, BAND_M, RSI_L, RSI_S = 20, 3.0, 60, 40   # the repo's 20-bar extremes, 3 * ATR10 band, RSI14 > 60 / < 40
SL_ATR = 1.5                           # my choice: the repo's fixed $25 gold stop is about 1.5 ATR14 of H1 gold
RR = 3.0                               # the repo's RR 3 ($25 stop, $75 target)
TWIN_P = 1 / 50                        # my choice: about the rule's trade rate in the backtest
LABEL = ("ATR band breakout (salainiyo Supertrend+RSI ทองคำ H1 ย้ายมา 4 ชม.) BTC ETH SOL BNB XRP PAXG: ปิดเหนือจุดสูงสุด "
         "20 แท่ง เหนือ band (H+L)/2-3ATR10 RSI14 เกิน 60 ซื้อ (short กลับกัน RSI ต่ำกว่า 40) stop 1.5 ATR14 เป้า 3 เท่า "
         "(backtest Binance 4 ชม. ทั้งประวัติ หลังหัก 0.35%/ข้าง BTC 374 ไม้ -0.28% ETH 412 ไม้ -0.44% SOL 266 ไม้ -0.54% "
         "BNB 385 ไม้ +0.33% XRP 318 ไม้ +0.03% PAXG 208 ไม้ -0.30% ต่อไม้ มัธยฐาน -1.4 ถึง -4.2% ชนะ 26-37% "
         "ตัวแฝดเข้าสุ่ม -0.16/-0.61/-0.40/-0.08/-1.09/-0.58% permutation 200 รอบ p 0.070/0.269/0.582/0.005/0.010/0.005 "
         "BNB บวกเพราะปี 2017 5 ไม้ ปี 2022-2026 ติดลบเกือบทุกเหรียญ ขา short ตามกฎเดิมไม่เคยเกิด จึงเป็น long อย่างเดียว)")
ACCOUNTS = {"state_fwd_atrbrk.json": ("rule", LABEL),
            "state_fwd_atrbrk_twin.json": ("random", "ATR band breakout ตัวควบคุม: เข้า long สุ่มเวลา ออกแบบเดียวกัน")}


def wilder(vals, n):
    out, a = [None] * len(vals), None
    for i, v in enumerate(vals):
        if v is None:
            continue
        a = v if a is None else (a * (n - 1) + v) / n
        out[i] = a
    return out


def ind(b):
    """Per bar: Wilder ATR10, ATR14 and RSI14 (as the scout's /tmp/scout_1715/bt.py)."""
    n, c = len(b), [x["c"] for x in b]
    tr = [None] + [max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - c[i - 1]), abs(b[i]["l"] - c[i - 1])) for i in range(1, n)]
    ag = wilder([None] + [max(c[i] - c[i - 1], 0) for i in range(1, n)], 14)
    al = wilder([None] + [max(c[i - 1] - c[i], 0) for i in range(1, n)], 14)
    rsi = [None if i < 14 else (100 if al[i] == 0 else 100 - 100 / (1 + ag[i] / al[i])) for i in range(n)]
    return wilder(tr, 10), wilder(tr, 14), rsi


def signal(b, i, atr10, rsi):
    if i < max(LOOK, 30) or atr10[i] is None or rsi[i] is None:
        return 0
    x = b[i]
    band = (x["h"] + x["l"]) / 2 - BAND_M * atr10[i]
    hh, ll = max(y["h"] for y in b[i - LOOK:i]), min(y["l"] for y in b[i - LOOK:i])
    if x["c"] > hh and x["c"] > band and rsi[i] > RSI_L:
        return 1
    if x["c"] < ll and x["c"] < band and rsi[i] < RSI_S:
        return -1
    return 0


def hit(x, p):
    o, h, l, d = x["o"], x["h"], x["l"], p["d"]
    if d > 0:
        return o if o <= p["stop"] else p["stop"] if l <= p["stop"] else max(p["tgt"], o) if h >= p["tgt"] else None
    return o if o >= p["stop"] else p["stop"] if h >= p["stop"] else min(p["tgt"], o) if l <= p["tgt"] else None


def trades(b, first=0):
    """The backtest: list of (entry_px, exit_px, side), oldest first."""
    atr10, atr14, rsi = ind(b)
    out, i, n = [], first, len(b)
    while i < n - 1:
        d = signal(b, i, atr10, rsi)
        if not d or not atr14[i]:
            i += 1
            continue
        e = b[i + 1]["o"]
        p = dict(d=d, stop=e - d * SL_ATR * atr14[i], tgt=e + d * RR * SL_ATR * atr14[i])
        j, px = i + 1, None
        while j < n:
            px = hit(b[j], p)
            if px is not None:
                break
            j += 1
        if px is None:
            break
        out.append((e, px, d))
        i = j + 1
    return out


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
    atr10, atr14, rsi = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            px = hit(x, p)
            if px is not None:
                close(s, sym, px, x["t"] + H4, "stop" if (px - p["entry"]) * p["d"] < 0 else f"ถึงเป้า {RR:g} เท่า stop")
                exited = True
        if sym in s["pos"] or exited or not atr14[i]:
            continue
        if mode == "rule":
            d = signal(bars, i, atr10, rsi)
        else:
            d = 1 if rng.random() < TWIN_P else 0   # long only, as the rule turned out
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = ("ทะลุ 20 แท่ง เหนือ band RSI เกิน 60" if d > 0 else "หลุด 20 แท่ง ใต้ band RSI ต่ำกว่า 40") if mode == "rule" else "สุ่มเวลา"
        sd = SL_ATR * atr14[i]
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=e - d * sd, tgt=e + d * RR * sd, entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_atrbrk fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
