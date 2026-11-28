#!/usr/bin/env python3
"""Forward paper test of S06 Triple EMA from tiagocosta1234/ema-futures-study (GitHub, Nov 2026: 12 EMA rules on 13
futures with pass criteria written before the test; S06 was the only one to pass, narrowly). Backtested by the scout in
the 17:55 run (rule rewritten, repo code not run) and opened in the 19:31 run because that run's two fwd slots were used.
Opened at any p because the user asked to try weak ideas too. Fake money only.

On closed daily Binance bars, with EMA(12) > EMA(26) > EMA(50) of closes: the first bar where that order holds -> long at
the next open; the first bar of the mirror order -> short. Exit at the next open when EMA12 crosses back through EMA26;
the opposite entry signal reverses at the next open. Stop 3 x ATR14 (simple average of true range, my choice) from the
signal bar's close, checked on every bar from the entry bar (a gap through it fills at the open). One position per coin,
one third of the start per coin, 0.35% per side.
  state_fwd_tripleema.json       BTC, ETH, SOL
  state_fwd_tripleema_twin.json  control: random entries (TWIN_P per bar) on the EMA12-vs-EMA26 side, the same exits
  python3 fwd_tripleema.py"""
import random
import byttrade as B
from byttrade import iso, load, save

COST = 0.0035
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]          # my choice: the three coins of the other daily accounts
F, M, SL, ATR_N, STOP_ATR = 12, 26, 50, 14, 3.0    # from the repo (12/26/50, 3 ATR stop); ATR as a simple average is mine
WARM = 2 * SL                                      # my choice: first 100 bars only warm the EMAs
TWIN_P = 0.04                                      # my choice: about the twin rate of the 17:55 backtest (trades / bars x 1.6)
LABEL = ("Triple EMA 12/26/50 รายวัน (tiagocosta1234/ema-futures-study S06): เข้าแท่งแรกที่ EMA12 > EMA26 > EMA50 long "
         "กลับด้าน short ออกเมื่อ EMA12 ตัดกลับ EMA26 stop 3 ATR BTC ETH SOL "
         "(backtest Binance รายวันถึง 27 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 70 ไม้ +9.2% ETH 63 ไม้ +8.0% SOL 48 ไม้ +26.3% ต่อไม้ "
         "มัธยฐาน BTC -3.0% ชนะ 41% ตัวแฝดเข้าสุ่ม +8.1/+6.6/+24.1% เกือบเท่ากฎ permutation 200 รอบกริดก่อนหัก p 0.050/0.030/0.070)")
ACCOUNTS = {"state_fwd_tripleema.json": ("rule", LABEL),
            "state_fwd_tripleema_twin.json": ("random", "Triple EMA ตัวควบคุม: เข้าแท่งสุ่มฝั่งตาม EMA12 เทียบ EMA26 ออกแบบเดียวกัน")}


def fetch_daily(sym):   # as fwd_xsmom.fetch_daily
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=1d")
    try:
        return B.fetch(sym)
    finally:
        B.URL = old


def ema(c, n):
    k, e, out = 2 / (n + 1), None, []
    for x in c:
        e = x if e is None else e + k * (x - e)
        out.append(e)
    return out


def ind(b):
    c = [x["c"] for x in b]
    f, m, s = ema(c, F), ema(c, M), ema(c, SL)
    tr, atr = [None] * len(b), [None] * len(b)
    for i in range(1, len(b)):
        tr[i] = max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - c[i - 1]), abs(b[i]["l"] - c[i - 1]))
        if i >= ATR_N:
            atr[i] = sum(tr[i - ATR_N + 1:i + 1]) / ATR_N
    up = [f[i] > m[i] > s[i] for i in range(len(b))]
    dn = [f[i] < m[i] < s[i] for i in range(len(b))]
    return f, m, up, dn, atr


def stop_hit(d, stop, x):
    """Fill price if bar x hits the stop of a position on side d, else None."""
    if d > 0 and (x["o"] <= stop or x["l"] <= stop):
        return min(x["o"], stop)
    if d < 0 and (x["o"] >= stop or x["h"] >= stop):
        return max(x["o"], stop)
    return None


def decide(i, side, pre, rng):
    """At the close of bar i, with the position side after its stop check: new side for the next open, or None to do nothing."""
    f, m, up, dn, atr = pre
    if rng is not None:
        lsig = side != 1 and f[i] > m[i] and rng.random() < TWIN_P
        ssig = side != -1 and f[i] < m[i] and rng.random() < TWIN_P
    else:
        lsig = side != 1 and up[i] and not up[i - 1]
        ssig = side != -1 and dn[i] and not dn[i - 1]
    if lsig:
        return 1
    if ssig:
        return -1
    if side == 1 and f[i] < m[i] and f[i - 1] >= m[i - 1]:
        return 0
    if side == -1 and f[i] > m[i] and f[i - 1] <= m[i - 1]:
        return 0
    return None


def trades(b, first=WARM, rng=None):
    """The backtest (same rule as the scout's /tmp/scout_1755/bt.py run(n=12, ls=True)): list of dict(t, d, e, x)."""
    pre = ind(b)
    out, p = [], None
    for i in range(max(first, WARM, ATR_N + 1), len(b) - 1):
        if p and b[i]["t"] >= p["t"]:
            px = stop_hit(p["d"], p["stop"], b[i])
            if px is not None:
                out.append(dict(t=p["t"], d=p["d"], e=p["e"], x=px))
                p = None
        if pre[4][i] is None:
            continue
        nd = decide(i, p["d"] if p else 0, pre, rng)
        if nd is None:
            continue
        e = b[i + 1]["o"]
        if p:
            out.append(dict(t=p["t"], d=p["d"], e=p["e"], x=e))
            p = None
        if nd:
            p = dict(t=b[i + 1]["t"], d=nd, e=e, stop=b[i]["c"] - nd * STOP_ATR * pre[4][i])
    return out


def close(s, sym, px, t, why):   # as fwd_c20swing.close
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
    pre = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < max(WARM, ATR_N + 1):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            px = stop_hit(p["d"], p["stop"], x)
            if px is not None:
                close(s, sym, px, x["t"], "stop 3 ATR")
        if pre[4][i] is None:
            continue
        p = s["pos"].get(sym)
        nd = decide(i, p["d"] if p else 0, pre, rng if mode == "random" else None)
        if nd is None:
            continue
        nb = bars[i + 1]
        if p:
            close(s, sym, nb["o"], nb["t"], "EMA12 ตัดกลับ EMA26" if nd == 0 else "สัญญาณฝั่งตรงข้าม กลับข้าง")
        if not nd:
            continue
        e, usd = nb["o"], s["start_usd"] / 3
        if nd > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if nd > 0 else usd) - usd * COST
        why = "EMA 12/26/50 เรียงตัวแท่งแรก" if mode == "rule" else "สุ่มแท่ง ฝั่งตาม EMA12 เทียบ EMA26"
        s["pos"][sym] = dict(side="long" if nd > 0 else "short", d=nd, qty=nd * usd / e, entry=e, last=e, usd=usd,
                             stop=x["c"] - nd * STOP_ATR * pre[4][i], entry_t=nb["t"], t=iso(nb["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nb["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_daily(sym)
        except Exception as e:
            print("fwd_tripleema fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
