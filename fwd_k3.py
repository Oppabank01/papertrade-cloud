#!/usr/bin/env python3
"""Forward paper test of NC1 SOL-K3-TK-T400-NOREG "deep capitulation, no regime filter" (kalambyryura/ai-trading-arena,
strategies/opus-nc1-sol-k3-tk-t400-noreg; failed that project's gate on its 2025-2026 tail), opened 24 Nov 2026 by the
scout on 1h bars; backtest numbers in LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

The recipe runs on 1-minute and 5-minute bars; this is the 1h version. On a closed 1h bar: log(close / highest high of
the last HH_N bars, this one included) <= -DEPTH x sigma, sigma = stdev of the last SIG_N hourly log returns, and the
bar closed above its open (the recipe's "last close above the close 15 min earlier", read on the hour) -> buy at the next
open. Stop -5%, target +4%, out at the open of the bar 12 h after entry; checked on closed bars from the entry bar on;
both touched = stop; a gap through the stop fills at the open. One position per coin, one third of the start per coin,
0.35% per side.
  state_fwd_k3.json       SOL, ETH, BTC
  state_fwd_k3_twin.json  control: random entry hours (TWIN_P per free hour), same exits
  python3 fwd_k3.py"""
import math
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
H = 3600 * 1000
SYMS = ["SOLUSDT", "ETHUSDT", "BTCUSDT"]   # recipe: SOL; ETH and BTC added by me for more trades
DEPTH, HH_N, SIG_N = 6.0, 4, 720       # from the recipe: -6 sigma below the 4 h high, sigma of 720 hourly returns
STOP, TGT, HOLD_H = 0.05, 0.04, 12     # from the recipe: 500 / 400 bps, 12 h
TWIN_P = 1 / 300                       # my choice: a little above the rule's rate (about 20 trades a year per coin)
LABEL = ("K3 ช้อนร่วงลึก 1 ชม. SOL ETH BTC (ai-trading-arena NC1 ไม่มีตัวกรอง ตกเกณฑ์ของเขาช่วงท้าย): ปิดต่ำกว่าจุดสูงสุด 4 ชม. "
         "เกิน 6 sigma (sigma จาก 720 ชม.) และแท่งปิดเขียว ซื้อเปิดแท่งถัดไป stop -5% เป้า +4% ถือไม่เกิน 12 ชม. "
         "(backtest Binance 1 ชม. 2017-2026 หลังหัก 0.35%/ข้าง SOL 118 ไม้ -1.18% ต่อไม้ ก่อนหัก -0.49% permutation 200 รอบ "
         "p 0.960, ETH 215 ไม้ -0.89% p 0.791, BTC 206 ไม้ -0.98% p 0.970 แย่กว่าตัวแฝดเวลาสุ่ม -0.73 ถึง -0.75% "
         "ก่อนหักติดลบทั้ง 3 เหรียญ คาดว่าแพ้ เปิดเพราะผู้ใช้ให้ลองท่าอ่อนด้วย)")
ACCOUNTS = {"state_fwd_k3.json": ("rule", LABEL),
            "state_fwd_k3_twin.json": ("random", "K3 ตัวควบคุม: เข้าชั่วโมงสุ่ม stop -5% เป้า +4% ถือไม่เกิน 12 ชม. แบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ind(b):
    """sig[i]: sample stdev of the hourly log returns of bars i-SIG_N+1..i."""
    n, sig, s1, s2, r = len(b), [None] * len(b), 0.0, 0.0, [0.0] * len(b)
    for i in range(1, n):
        r[i] = math.log(b[i]["c"] / b[i - 1]["c"])
        s1 += r[i]; s2 += r[i] ** 2
        if i > SIG_N:
            s1 -= r[i - SIG_N]; s2 -= r[i - SIG_N] ** 2
        if i >= SIG_N:
            sig[i] = math.sqrt(max(s2 - s1 * s1 / SIG_N, 0.0) / (SIG_N - 1))
    return sig


def signal(b, i, sig):
    if i < HH_N or sig[i] is None:
        return False
    hh = max(x["h"] for x in b[i - HH_N + 1:i + 1])
    return math.log(b[i]["c"] / hh) <= -DEPTH * sig[i] and b[i]["c"] > b[i]["o"]


def exit_px(p, x):
    if x["t"] >= p["exit_t"]:
        return x["o"], f"ครบ {HOLD_H} ชม."
    if x["o"] <= p["stop"]:
        return x["o"], "stop"
    if x["l"] <= p["stop"]:
        return p["stop"], "stop"
    if x["h"] >= p["tgt"]:
        return max(p["tgt"], x["o"]), "ถึงเป้า +4%"
    return None


def trades(b, first=1):
    """The backtest: (entry_t, entry_px, exit_t, exit_px), oldest first."""
    sig, out, pos = ind(b), [], None
    for i in range(first, len(b)):
        x = b[i]
        if pos:
            r = exit_px(pos, x)
            if r:
                out.append((pos["entry_t"], pos["entry"], x["t"], r[0])); pos = None
            continue
        if i + 1 < len(b) and sig[i] is not None and signal(b, i, sig):
            e = b[i + 1]["o"]
            pos = dict(entry=e, entry_t=b[i + 1]["t"], exit_t=b[i + 1]["t"] + HOLD_H * H, stop=e * (1 - STOP), tgt=e * (1 + TGT))
    return out


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px * (1 - COST)
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    sig = ind(bars)
    usd = s["start_usd"] / len(SYMS)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p:
            if x["t"] >= p["entry_t"]:
                r = exit_px(p, x)
                if r:
                    close(s, sym, r[0], x["t"], r[1])
            continue
        if sig[i] is None:
            continue
        go = signal(bars, i, sig) if mode == "rule" else rng.random() < TWIN_P
        if not go or s["cash"] < usd * (1 + COST):
            continue
        nx = bars[i + 1]
        e = nx["o"]
        s["cash"] -= usd * (1 + COST)
        hh = max(y["h"] for y in bars[i - HH_N + 1:i + 1])
        why = "ร่วงจากจุดสูงสุด 4 ชม. %.1f%% (%.1f sigma) แท่งปิดเขียว" % (100 * (x["c"] / hh - 1), math.log(x["c"] / hh) / sig[i]) \
            if mode == "rule" else "สุ่มชั่วโมง"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=nx["t"],
                             exit_t=nx["t"] + HOLD_H * H, stop=e * (1 - STOP), tgt=e * (1 + TGT), t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_k3 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
