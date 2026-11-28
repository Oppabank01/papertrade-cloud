#!/usr/bin/env python3
"""Forward paper test of breakout_trend from lovgolf/honest-crypto-backtester (GitHub, Nov 2026; its README says the
sample walk-forward on SOL 1h lost money after costs: +$388 at zero cost, -$362 with costs). Opened 28 Nov 2026 by the
scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 1h Binance bars (the repo's defaults): flat and the close above the highest high of the 20 bars before and
above EMA100 (pandas ewm span 100, adjust=False, seeded with the first close fetched) -> long at the next open. Stop =
entry - 2 * ATR14, target = entry + 4 * ATR14 (ATR = simple mean of the last 14 true ranges at the signal bar), checked
on closed bars from the entry bar on; a gap through the stop fills at the open, a gap over the target at the open; both
touched = stop; otherwise out at the close of the 48th bar after the entry bar. No signal while held or on the exit bar
(my choice; the repo can re-enter on the exit bar). The repo's target needs the high to trade through it by a margin;
here touching it fills (my choice). One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_honestbrk.json       BTC, ETH, SOL
  state_fwd_honestbrk_twin.json  control: random entry bars (TWIN_P per free bar above EMA100), the same exits
  python3 fwd_honestbrk.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

H1 = 3600 * 1000
COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the repo's example is SOL; BTC and ETH as the scout's usual set
LOOK, EMA_N, AN, SL, TP, MAXB = 20, 100, 14, 2, 4, 48   # the repo's numbers
TWIN_P = 1 / 38                        # my choice: the backtest's random control rate (1.6 x the rule's entries per bar)
LABEL = ("breakout 1 ชม. (lovgolf/honest-crypto-backtester) BTC ETH SOL: ปิดเหนือ high 20 ชม. และเหนือ EMA100 ซื้อ stop 2 ATR "
         "เป้า 4 ATR ถือสูงสุด 48 ชม. (backtest Binance 1h 2017-2026 หลังหัก 0.35%/ข้าง BTC 1318 ไม้ -0.50% ต่อไม้ ETH 1336 ไม้ "
         "-0.54% SOL 923 ไม้ -0.50% ชนะ 37% ติดลบเกือบทุกปี ตัวแฝดเข้าสุ่ม -0.58/-0.57/-0.62% ก่อนหัก +0.20/+0.16/+0.20% "
         "permutation 200 รอบทั้งกริด 9 แบบ p 0.010/0.010/0.124 แรงทะลุมีจริงแต่เล็กกว่าค่าธรรมเนียม)")
ACCOUNTS = {"state_fwd_honestbrk.json": ("rule", LABEL),
            "state_fwd_honestbrk_twin.json": ("random", "breakout 1 ชม. ตัวควบคุม: เข้าแท่งสุ่มเหนือ EMA100 stop 2 ATR เป้า 4 ATR ถือสูงสุด 48 ชม. แบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ind(b):
    """EMA100 (adjust=False), ATR14 as the simple mean of true ranges, the highest high of the LOOK bars before."""
    n, k = len(b), 2 / (EMA_N + 1)
    ema, atr, hh, e, tr, hs = [None] * n, [None] * n, [None] * n, None, [None] * n, [x["h"] for x in b]
    for i, x in enumerate(b):
        e = x["c"] if e is None else e + k * (x["c"] - e)
        ema[i] = e
        if i >= 1:
            p = b[i - 1]["c"]
            tr[i] = max(x["h"] - x["l"], abs(x["h"] - p), abs(x["l"] - p))
        if i >= AN:
            atr[i] = sum(tr[i - AN + 1:i + 1]) / AN
        if i >= LOOK:
            hh[i] = max(hs[i - LOOK:i])
    return ema, atr, hh


def hit(x, stop, tgt):
    o = x["o"]
    return o if o <= stop else stop if x["l"] <= stop else max(tgt, o) if x["h"] >= tgt else None


def trades(b):
    """The backtest (same trades as the scout's /tmp/scout_1614/bt.py run()): (entry_t, entry, exit), oldest first."""
    ema, atr, hh = ind(b)
    out, i, n = [], LOOK, len(b)
    while i < n - 1:
        if not (atr[i] and b[i]["c"] > hh[i] and b[i]["c"] > ema[i]):
            i += 1
            continue
        ei = i + 1
        e = b[ei]["o"]
        stop, tgt = e - SL * atr[i], e + TP * atr[i]
        px, j = None, ei
        while j < n:
            px = hit(b[j], stop, tgt)
            if px is None and j - ei >= MAXB:
                px = b[j]["c"]
            if px is not None:
                break
            j += 1
        if px is None:
            break
        out.append((b[ei]["t"], e, px))
        i = j + 1
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px - p["qty"] * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    ema, atr, hh = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < LOOK:
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            px, why = hit(x, p["stop"], p["tgt"]), None
            if px is not None:
                why = "stop 2 ATR" if px < p["entry"] else "ถึงเป้า 4 ATR"
            elif x["t"] >= p["entry_t"] + MAXB * H1:
                px, why = x["c"], "ครบ 48 ชม."
            if px is not None:
                close(s, sym, px, x["t"] + H1, why)
                exited = True
        if sym in s["pos"] or exited or not atr[i]:
            continue
        if mode == "rule":
            go, why = x["c"] > hh[i] and x["c"] > ema[i], "ปิดเหนือจุดสูงสุด 20 ชม. และเหนือ EMA100"
        else:
            go, why = x["c"] > ema[i] and rng.random() < TWIN_P, "สุ่มแท่งเหนือ EMA100"
        if not go:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, stop=e - SL * atr[i],
                             tgt=e + TP * atr[i], entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_honestbrk fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
