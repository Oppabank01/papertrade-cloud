#!/usr/bin/env python3
"""Forward paper test of strategy v3-B "Range Mean-Reversion" of ShuWayne/crypto-trading-intelligence-terminal
(docs/strategy.md) on BTC and SOL, the two coins the repo trades (opened 23 Nov 2026 by the scout; backtest in LABEL,
opened at any p because the user asked to try weak ideas too). Fake money only.

On closed 4h Binance bars, all on the same bar (the repo's numbers, none tuned here):
  ranging: |SMA20 - SMA50| <= 1% of close and (20-bar swing high - swing low, current bar excluded) >= 4 ATR14
  long: min(low of this and previous bar) <= swing low + 0.5 ATR, min(RSI14 of the two) < 32, green bar closing in its
        upper half, RSI14 <= 40, true range <= 2.5 ATR; short is the mirror (68 / 60, red bar in the lower half)
  enter at the next open (the repo fills at the signal close; the next open is what a 4h walk can get), stop 1.5 ATR,
  target 3 ATR (the signal bar's ATR), time exit at the close of the 24th bar; both touched = stop, gaps fill at the open.
The repo's daily loss cap, 2-trades-a-day and breakeven move are left out (2 coins, one position each). Half the start
per coin, 0.35% per side.
  state_fwd_rangerev.json       BTC, SOL
  state_fwd_rangerev_twin.json  control: random entry bars (TWIN_P per free bar), random side, same stop/target/time exit
  python3 fwd_rangerev.py"""
import random
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "SOLUSDT"]      # the repo's scope (ETH and PAXG excluded there)
WARM = 100                         # the repo's warm-up in bars
TWIN_P = 1 / 150                   # my choice: the rule fired 362 times in ~54,000 coin-bars (BTC ETH SOL), about 1 in 150
LABEL = ("range mean-reversion v3-B 4 ชม. BTC SOL: ตลาดไซด์เวย์ (SMA20 ห่าง SMA50 ไม่เกิน 1% กรอบ 20 แท่งกว้าง 4 ATR ขึ้นไป) "
         "แตะขอบล่าง RSI ต่ำกว่า 32 แท่งเขียวปิดครึ่งบน ซื้อ (short กลับกัน) stop 1.5 ATR เป้า 3 ATR ถือไม่เกิน 24 แท่ง "
         "(backtest 2017-2026 หลังหัก 0.35%/ข้าง BTC 171 ไม้ -1.17% p 0.920 SOL 64 ไม้ -1.78% p 0.851 ETH 127 ไม้ -1.34% "
         "แพ้ตัวแฝดเข้าสุ่ม -0.54 ถึง -0.73% ต่อไม้ ติดลบทุกปี)")
ACCOUNTS = {"state_fwd_rangerev.json": ("rule", LABEL),
            "state_fwd_rangerev_twin.json": ("random", "range mean-reversion ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งสุ่ม stop 1.5 ATR เป้า 3 ATR ถือไม่เกิน 24 แท่งแบบเดียวกัน")}


def ind(b):
    c, n = [x["c"] for x in b], len(b)
    s20, s50, rsi, atr, tr = [None] * n, [None] * n, [None] * n, [None] * n, [None] * n
    ag = al = a = 0.0
    for i in range(n):
        if i >= 19:
            s20[i] = sum(c[i - 19:i + 1]) / 20
        if i >= 49:
            s50[i] = sum(c[i - 49:i + 1]) / 50
        if i == 0:
            continue
        d = c[i] - c[i - 1]
        g, l = max(d, 0), max(-d, 0)
        if i <= 14:
            ag += g / 14; al += l / 14
        else:
            ag = (ag * 13 + g) / 14; al = (al * 13 + l) / 14
        if i >= 14:
            rsi[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
        tr[i] = max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - c[i - 1]), abs(b[i]["l"] - c[i - 1]))
        a = tr[i] if i == 1 else (a * 13 + tr[i]) / 14
        if i >= 14:
            atr[i] = a
    return s20, s50, rsi, atr, tr


def signal(b, i, I):
    s20, s50, rsi, atr, tr = I
    if i < max(WARM, 50) or None in (s20[i], s50[i], rsi[i], rsi[i - 1], atr[i]):
        return 0
    x, y, a = b[i], b[i - 1], atr[i]
    hi, lo = max(z["h"] for z in b[i - 20:i]), min(z["l"] for z in b[i - 20:i])
    if abs(s20[i] - s50[i]) > 0.01 * x["c"] or hi - lo < 4 * a or tr[i] > 2.5 * a:
        return 0
    mid = (x["h"] + x["l"]) / 2
    if min(x["l"], y["l"]) <= lo + 0.5 * a and min(rsi[i], rsi[i - 1]) < 32 and x["c"] > x["o"] and x["c"] > mid and rsi[i] <= 40:
        return 1
    if max(x["h"], y["h"]) >= hi - 0.5 * a and max(rsi[i], rsi[i - 1]) > 68 and x["c"] < x["o"] and x["c"] < mid and rsi[i] >= 60:
        return -1
    return 0


def hit(y, d, stop, tgt):
    o, h, l = y["o"], y["h"], y["l"]
    if d > 0:
        return o if o <= stop else stop if l <= stop else max(tgt, o) if h >= tgt else None
    return o if o >= stop else stop if h >= stop else min(tgt, o) if l <= tgt else None


def trades(b, first=WARM):
    """The backtest (the scout's /tmp/scout_0427.py calls this): list of dict(t, d, e, x, why), oldest first."""
    I, out, i, n = ind(b), [], first, len(b)
    while i < n - 1:
        d = signal(b, i, I)
        if not d:
            i += 1
            continue
        e = b[i + 1]["o"]; stop, tgt = e - d * 1.5 * I[3][i], e + d * 3 * I[3][i]
        px, j = None, i + 1
        while j < n:
            px = hit(b[j], d, stop, tgt)
            if px is None and j - i >= 24:
                px = b[j]["c"]
            if px is not None:
                break
            j += 1
        if px is None:
            break
        out.append(dict(t=b[i + 1]["t"], d=d, e=e, x=px))
        i = j + 1
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
            px, why = hit(x, p["d"], p["stop"], p["tgt"]), None
            if px is not None:
                why = "stop" if (px - p["entry"]) * p["d"] < 0 else "ถึงเป้า 3 ATR"
            elif (x["t"] - p["entry_t"]) // H4 + 1 >= 24:
                px, why = x["c"], "ครบ 24 แท่ง"
            if px is not None:
                close(s, sym, px, x["t"] + H4, why)
                exited = True
        if sym in s["pos"] or exited or i < max(WARM, 50) or not I[3][i]:
            continue
        if mode == "rule":
            d = signal(bars, i, I)
        else:
            d = rng.choice((1, -1)) if rng.random() < TWIN_P else 0
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 2
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = ("แตะขอบล่างกรอบ RSI ต่ำ" if d > 0 else "แตะขอบบนกรอบ RSI สูง") if mode == "rule" else "สุ่มแท่ง สุ่มฝั่ง"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=e - d * 1.5 * I[3][i], tgt=e + d * 3 * I[3][i], entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_rangerev fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
