#!/usr/bin/env python3
"""Forward paper test of Drssptra/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1-entry (GitHub, Nov 2026, a make.fun
"Tiny Bot" bounty entry): EMA6/EMA12 + 12h momentum rotation on hourly Solana-ecosystem coins, long only, 3% stop.
Opened 26 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too.
Fake money only.

On closed 1h Binance bars, all 7 coins at once (numbers from strategy.ts): exits first, out at the next open when the
close is under 0.97 x the entry (then no re-entry for 3 hours), the EMA6 is under 0.998 x the EMA12, or the 12-bar return
is under -2%. Then entries: coins with no position whose 12-bar return is above +1.5% and whose EMA6 is above 1.002 x the
EMA12, best 12-bar return first, while fewer than 3 coins are held -> long at the next open. One quarter of the start per
coin (the source's 25% weight cap), 0.35% per side.
  state_fwd_emarot.json       SOL JUP JTO PYTH RAY BONK WIF
  state_fwd_emarot_twin.json  control: random entries (1 in 55 free coin-bars, random order, same 3-coin cap), same exits
  python3 fwd_emarot.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here (the bounty harness charged its own fees)
H1 = 3600 * 1000
SYMS = ["SOLUSDT", "JUPUSDT", "JTOUSDT", "PYTHUSDT", "RAYUSDT", "BONKUSDT", "WIFUSDT"]   # my choice: the source only says
# "hourly bars" of the replay universe; these are the 7 Solana coins with Binance spot history since Mar 2024 (as fwd_tinydon)
FAST, SLOW, MOM = 6, 12, 12            # from strategy.ts
ENT, EXM, HYST, STOP = 0.015, -0.02, 0.002, 0.03   # from strategy.ts
NAMES, COOL = 3, 3                     # from strategy.ts: at most 3 coins, 3 bars before re-entry after a stop
TWIN_P = 1 / 55                        # my choice: about as many twin trades as rule trades
# also mine: EMAs seeded with the first close of the fetched window (strategy.ts seeds with the first bar it sees; after
# 1000 bars the seed no longer matters), the stop is checked on closes (as strategy.ts), fills at the next open, the
# cooldown counted in hours from the stop bar
LABEL = ("EMA6/12 + โมเมนตัม 12 ชม. หมุนเหรียญ (Drssptra Tiny Bot make.fun) SOL JUP JTO PYTH RAY BONK WIF แท่ง 1 ชม.: "
         "EMA6 เหนือ EMA12 0.2% และขึ้น 12 แท่งเกิน 1.5% ซื้อตัวที่ขึ้นแรงสุดไม่เกิน 3 ตัว ออกเมื่อ EMA6 ต่ำกว่า EMA12 0.2% "
         "12 แท่งลงเกิน 2% หรือต่ำกว่าทุน 3% ไม้ละ 1 ใน 4 (backtest Binance 1 ชม. มี.ค. 67 ถึง 25 พ.ย. 69 หลังหัก 0.35%/ข้าง "
         "2,338 ไม้ -0.70% ต่อไม้ มัธยฐาน -2.36% ก่อนหัก 0.00% ชนะ 28% ตัวแฝดเข้าสุ่ม -0.68% ติดลบทุกปี กริด 18 แบบ "
         "-0.66 ถึง -0.75% permutation 200 รอบ 365 วันล่าสุด ดีสุด -0.62% เทียบแท่งสลับ -0.68% p 0.31 "
         "ช่วงนั้นถือ 7 เหรียญเท่ากัน -70%)")
ACCOUNTS = {"state_fwd_emarot.json": ("rule", LABEL),
            "state_fwd_emarot_twin.json": ("random", "EMA6/12 หมุนเหรียญ ตัวควบคุม: เข้าสุ่ม 1 ใน 55 แท่ง ไม่เกิน 3 ตัว ออกแบบเดียวกัน")}


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


def emas(c):
    af, asl = 2 / (FAST + 1), 2 / (SLOW + 1)
    f = sl = c[0]
    F, L = [f], [sl]
    for x in c[1:]:
        f += (x - f) * af
        sl += (x - sl) * asl
        F.append(f)
        L.append(sl)
    return F, L


def out_why(c, e, f, sl, m):
    return ("ต่ำกว่าทุน 3%" if c < (1 - STOP) * e else "EMA6 ต่ำกว่า EMA12" if f < sl * (1 - HYST)
            else "12 แท่งลงเกิน 2%" if m < EXM else None)


def go_rule(f, sl, m):
    return m > ENT and f > sl * (1 + HYST)


def trades(bb, mode="rule", rng=None):
    """The backtest (same trades as the scout's /tmp/scout_0546/bt_ema.py at the strategy.ts settings): list of
    (sym, entry t, entry, exit t, exit) on aligned closed bars."""
    C = {s: [x["c"] for x in b] for s, b in bb.items()}
    E = {s: emas(C[s]) for s in C}
    ref = next(iter(bb.values()))
    pos, cool, out = {}, {}, []
    for i in range(MOM + 1, len(ref) - 1):
        for s in list(pos):
            e, et = pos[s]
            c, m = C[s][i], C[s][i] / C[s][i - MOM] - 1
            why = out_why(c, e, E[s][0][i], E[s][1][i], m)
            if why:
                if why == "ต่ำกว่าทุน 3%":
                    cool[s] = ref[i]["t"] + COOL * H1
                out.append((s, et, e, bb[s][i + 1]["t"], bb[s][i + 1]["o"]))
                del pos[s]
        cand = []
        for s in C:
            if s in pos or ref[i]["t"] < cool.get(s, 0):
                continue
            m = C[s][i] / C[s][i - MOM] - 1
            if mode == "rule":
                if go_rule(E[s][0][i], E[s][1][i], m):
                    cand.append((m, s))
            elif rng.random() < TWIN_P:
                cand.append((rng.random(), s))
        cand.sort(key=lambda x: -x[0])
        for m, s in cand[:max(0, NAMES - len(pos))]:
            pos[s] = (bb[s][i + 1]["o"], bb[s][i + 1]["t"])
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
    E = {k: emas(C[k]) for k in C}
    cool = s.setdefault("cool", {})
    for i in shut:
        if ref[i]["t"] <= s["seen"] or i + 1 >= len(ref) or i <= MOM:
            continue
        s["seen"] = ref[i]["t"]
        for sym, b in bb.items():
            p = s["pos"].get(sym)
            if not p or b[i]["t"] < p["entry_t"]:
                continue
            c, m = C[sym][i], C[sym][i] / C[sym][i - MOM] - 1
            why = out_why(c, p["entry"], E[sym][0][i], E[sym][1][i], m)
            if why:
                if why == "ต่ำกว่าทุน 3%":
                    cool[sym] = ref[i]["t"] + COOL * H1
                close(s, sym, b[i + 1]["o"], b[i + 1]["t"], why)
        cand = []
        for sym in bb:
            if sym in s["pos"] or ref[i]["t"] < cool.get(sym, 0):
                continue
            m = C[sym][i] / C[sym][i - MOM] - 1
            if mode == "rule":
                if go_rule(E[sym][0][i], E[sym][1][i], m):
                    cand.append((m, sym))
            elif rng.random() < TWIN_P:
                cand.append((rng.random(), sym))
        cand.sort(key=lambda x: -x[0])
        for m, sym in cand[:max(0, NAMES - len(s["pos"]))]:
            b = bb[sym]
            e, t = b[i + 1]["o"], b[i + 1]["t"]
            usd = min(s["start_usd"] / 4, s["cash"] / (1 + COST))   # my choice: after losses take what cash is left (as
            if usd < 0.01:                                           # the source's notional > cashLeft clamp), so the trades
                continue                                             # stay those of the backtest
            s["cash"] -= usd + usd * COST
            why = f"EMA6 เหนือ EMA12 ขึ้น 12 แท่ง {m:+.1%}" if mode == "rule" else "สุ่มเวลา"
            s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=t, t=iso(t), why=why)
            s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    for sym, p in s["pos"].items():
        p["last"] = bb[sym][-1]["c"]


def main():
    rng, raw = random.Random(), {}
    for sym in SYMS:
        try:
            raw[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_emarot fetch failed", sym, type(e).__name__)
    if len(raw) < len(SYMS):
        return                         # the rank needs every coin; a failed fetch means no action this tick
    bb = align(raw)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        step(s, bb, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
