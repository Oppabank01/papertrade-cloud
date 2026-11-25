#!/usr/bin/env python3
"""Forward paper test of satriax30-commits/makefun-tiny-bot-sol (GitHub, Nov 2026, a make.fun "Tiny Bot" bounty entry):
Donchian breakout filtered by cross-sectional momentum rank on hourly Solana-ecosystem coins, long only. Opened 26 Nov 2026
by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 1h Binance bars, every coin at once (numbers from the README): a coin with no position whose close is above the
highest close of the previous 12 bars, whose 24-bar return is positive and which is in the top 3 of the 7 coins by that
24-bar return -> long at the next open. Out at the next open when a close is under the lowest close of the previous 6
bars, at or under 0.9 x the entry, or at or under 0.9 x the highest close since entry. One position per coin, one seventh
of the start per coin (the README's equity / 7), 0.35% per side.
  state_fwd_tinydon.json       SOL JUP JTO PYTH RAY BONK WIF
  state_fwd_tinydon_twin.json  control: random entries (1 in 40 free coin-bars), same exits
  python3 fwd_tinydon.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here (the bounty harness charged 0.15%)
H1 = 3600 * 1000
SYMS = ["SOLUSDT", "JUPUSDT", "JTOUSDT", "PYTHUSDT", "RAYUSDT", "BONKUSDT", "WIFUSDT"]   # my choice: the README says only
# "the 7-symbol universe" of hourly Solana prices; these are the 7 Solana coins with Binance spot history since Mar 2024
ENT, MOM, TOP, EX, HARD, TRAIL = 12, 24, 3, 6, 0.10, 0.10   # all from the README
TWIN_P = 1 / 40                        # my choice: about as many twin trades as rule trades per coin
# also mine: the -10% hard stop and the trail are checked on closes (as the README's other exits), fills at the next open
LABEL = ("ทะลุ 12 ชม. + อันดับโมเมนตัม (satriax30 Tiny Bot make.fun) SOL JUP JTO PYTH RAY BONK WIF แท่ง 1 ชม.: ปิดเหนือสูงสุด 12 แท่ง "
         "ขึ้น 24 แท่งและติด 3 อันดับแรกจาก 7 เหรียญ ออกเมื่อปิดต่ำกว่าต่ำสุด 6 แท่ง ต่ำกว่าทุน 10% หรือต่ำกว่าปิดสูงสุด 10% ไม้ละ 1 ใน 7 "
         "(backtest Binance 1 ชม. มี.ค. 67 ถึง 23 พ.ย. 69 หลังหัก 0.35%/ข้าง 3,394 ไม้ -0.62% ต่อไม้ มัธยฐาน -1.58% ก่อนหัก +0.08% "
         "ชนะ 28% ตัวแฝดเข้าสุ่ม -0.68% permutation 200 รอบ 365 วันล่าสุด ดีสุดจาก 18 แบบ -0.48% เทียบแท่งสลับ -0.66% "
         "p 0.010 ชนะแท่งสลับแต่หลังหักยังติดลบ ช่วงนั้นถือ 7 เหรียญเท่ากัน -66%)")
ACCOUNTS = {"state_fwd_tinydon.json": ("rule", LABEL),
            "state_fwd_tinydon_twin.json": ("random", "ทะลุ 12 ชม. + อันดับโมเมนตัม ตัวควบคุม: เข้าสุ่ม 1 ใน 40 แท่ง ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def align(raw):
    """{sym: bars} -> the same hours for every coin, oldest first."""
    ts = sorted(set.intersection(*[set(x["t"] for x in b) for b in raw.values()]))
    idx = {s: {x["t"]: x for x in b} for s, b in raw.items()}
    return {s: [idx[s][t] for t in ts] for s in raw}


def ranks(C, i):
    r = {s: C[s][i] / C[s][i - MOM] - 1 for s in C}
    return r, sorted(C, key=lambda s: -r[s])[:TOP]


def out_now(c, prev, entry, hc):
    return c < min(prev) or c <= (1 - HARD) * entry or c <= (1 - TRAIL) * hc


def trades(bb):
    """The backtest (same trades as the scout's /tmp/scout_0031/bt.py run at the README settings): list of
    (sym, entry t, entry, exit t, exit) on aligned closed bars."""
    C = {s: [x["c"] for x in b] for s, b in bb.items()}
    n, out, pos = len(next(iter(bb.values()))), [], {}
    for i in range(max(ENT, MOM, EX), n - 1):
        r, top = ranks(C, i)
        for s, b in bb.items():
            c = C[s][i]
            if s in pos:
                e, hc, et = pos[s]
                hc = max(hc, c)
                pos[s] = (e, hc, et)
                if out_now(c, C[s][i - EX:i], e, hc):
                    out.append((s, et, e, b[i + 1]["t"], b[i + 1]["o"]))
                    del pos[s]
                continue
            if c > max(C[s][i - ENT:i]) and r[s] > 0 and s in top:
                pos[s] = (b[i + 1]["o"], b[i + 1]["o"], b[i + 1]["t"])
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, bb, mode, rng):
    """bb: aligned bars of every coin, the last hour may still be forming. Walks every closed hour after s['seen']."""
    ref = next(iter(bb.values()))
    shut = [i for i in range(len(ref)) if all(b[i]["closed"] for b in bb.values())]
    if s.get("seen") is None:
        s["seen"] = ref[shut[-1]]["t"]
        return
    C = {k: [x["c"] for x in b] for k, b in bb.items()}
    for i in shut:
        if ref[i]["t"] <= s["seen"] or i + 1 >= len(ref) or i < max(ENT, MOM, EX):
            continue
        s["seen"] = ref[i]["t"]
        r, top = ranks(C, i)
        for sym, b in bb.items():
            c, p = C[sym][i], s["pos"].get(sym)
            if p:
                if b[i]["t"] < p["entry_t"]:
                    continue
                p["hc"] = max(p["hc"], c)
                if out_now(c, C[sym][i - EX:i], p["entry"], p["hc"]):
                    why = ("ปิดต่ำกว่าต่ำสุด 6 แท่ง" if c < min(C[sym][i - EX:i]) else
                           "ต่ำกว่าทุน 10%" if c <= (1 - HARD) * p["entry"] else "ต่ำกว่าปิดสูงสุด 10%")
                    close(s, sym, b[i + 1]["o"], b[i + 1]["t"], why)
                continue
            if mode == "rule":
                go = c > max(C[sym][i - ENT:i]) and r[sym] > 0 and sym in top
            else:
                go = rng.random() < TWIN_P
            if not go:
                continue
            e, t, usd = b[i + 1]["o"], b[i + 1]["t"], s["start_usd"] / len(SYMS)
            if s["cash"] < usd * (1 + COST):
                continue
            s["cash"] -= usd + usd * COST
            why = f"ทะลุ 12 แท่ง อันดับ {top.index(sym) + 1} ขึ้น 24 แท่ง {r[sym]:+.1%}" if mode == "rule" else "สุ่มเวลา"
            s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, hc=e, entry_t=t, t=iso(t), why=why)
            s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    for sym, p in s["pos"].items():
        p["last"] = bb[sym][-1]["c"]


def main():
    rng, raw = random.Random(), {}
    for sym in SYMS:
        try:
            raw[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_tinydon fetch failed", sym, type(e).__name__)
    if len(raw) < len(SYMS):
        return                         # the rank needs every coin; a failed fetch means no action this tick
    bb = align(raw)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        step(s, bb, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
