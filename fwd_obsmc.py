#!/usr/bin/env python3
"""Forward paper test of "3: Order Block (SMC)" from pumarathaworn01/tomorn-trading-bot (GitHub, Nov 2026, bot/backtest.py
class S3; the author's own 5-year test found no strategy profitable after costs) on BTC, ETH, SOL, BNB, XRP 4h bars
(opened 24 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too).
Fake money only.

On closed 4h Binance bars, as the repo: a bullish fair value gap confirmed at bar i (low[i] > high[i-2], bar i-1 green);
the order block is the last red bar among i-2..i-6; if bar i's low already touched its high the block is mitigated and
there is no signal. Otherwise rest a limit buy at the block high, stop 0.3% below the block low, target the most recent
confirmed swing high (3/3 fractal) above block high + 0.2%, else 2R. The order lives EXPIRE bars. A fill happens when a
bar's low reaches the limit, at min(open, limit); the trade is skipped when its reward:risk after costs on both legs is
below 1.5. Exits on the bar path from the fill bar on: stop first when one bar touches both, a gap through the stop or
target fills at the open. No time stop (the repo has none). Long only. One position or order per coin, one fifth of the
start per coin, 0.35% per side.
  state_fwd_obsmc.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_obsmc_twin.json  control: random bars (TWIN_P per free bar) buy at the next open, stop -TWIN_D, target 2R
  python3 fwd_obsmc.py"""
import random
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                      # per side, as every account here (the repo used 0.12%)
H = H4
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # the repo's five coins
SLB, EXPIRE, RR, MIN_NET_RR, TP_PAD, FR = 0.003, 100, 2.0, 1.5, 0.002, 3   # the repo's S3 / engine settings
LOOK = 500                         # my choice: swing highs older than 500 bars are ignored, so the 1000-bar window cron
                                   # sees gives the same target as full history (the repo searches all history)
TWIN_P = 1 / 40                    # my choice: about the rule's order rate per free bar
TWIN_D = 0.02                      # my choice: about the rule's median stop distance (1.9% over its 7,014 orders)
HOLD_H = 10 ** 9                   # no time stop
LABEL = ("Order Block SMC 4 ชม. BTC ETH SOL BNB XRP (pumarathaworn01/tomorn-trading-bot กลยุทธ์ 3): ช่องว่าง FVG ขาขึ้น "
         "ตั้ง limit ที่ยอดแท่งแดงสุดท้ายก่อนพุ่ง stop ใต้แท่งนั้น 0.3% เป้า swing high ถัดไป ข้ามไม้ที่ R:R หลังหักต้นทุนไม่ถึง 1.5 "
         "long อย่างเดียว (backtest 2017-2026 หลังหัก 0.35%/ข้าง BTC 81 ไม้ -0.42% ETH 124 ไม้ -0.37% SOL 93 ไม้ -0.86% "
         "BNB 99 ไม้ -0.41% XRP 122 ไม้ -1.17% ต่อไม้ ก่อนหัก +0.28/+0.33/-0.17/+0.29/-0.47% มัธยฐาน -2.0 ถึง -2.8% "
         "ชนะ 20-32% ตัวแฝดเข้าสุ่ม stop -2% เป้า 2R -0.71/-0.64/-0.77/-0.61/-0.78% permutation 200 รอบ p 0.29/0.30/0.91/0.46/0.99)")
ACCOUNTS = {"state_fwd_obsmc.json": ("rule", LABEL),
            "state_fwd_obsmc_twin.json": ("random", "Order Block ตัวควบคุม: ซื้อแท่งสุ่มที่เปิดแท่งถัดไป stop -2% เป้า 2R")}


def swings(b):
    """(j, high) of 3/3 fractal highs; one at j is known from the close of bar j + FR."""
    out = []
    for j in range(FR, len(b) - FR):
        w = [x["h"] for x in b[j - FR:j + FR + 1]]
        if b[j]["h"] == max(w) and w.count(b[j]["h"]) == 1:
            out.append((j, b[j]["h"]))
    return out


def swing_high_above(sh, i, price):
    for j, v in reversed(sh):
        if j + FR > i:
            continue
        if j < i - LOOK:
            return None
        if v > price:
            return v
    return None


def signal(b, i, sh):
    """Pending limit order dict at the close of bar i, or None."""
    if i < 8 or not (b[i]["l"] > b[i - 2]["h"] and b[i - 1]["c"] > b[i - 1]["o"]):
        return None
    for k in range(i - 2, i - 7, -1):
        if b[k]["c"] < b[k]["o"]:
            ob_h, ob_l = b[k]["h"], b[k]["l"]
            if b[i]["l"] <= ob_h:
                return None
            return dict(lim=ob_h, sl=ob_l * (1 - SLB), tp=swing_high_above(sh, i, ob_h * (1 + TP_PAD)),
                        exp_t=b[i]["t"] + EXPIRE * H)
    return None


def net_rr(e, sl, tp):
    k = (1 - COST) ** 2
    return (k * tp / e - 1) / (1 - k * sl / e)


def fill(o, x):
    """(entry, stop, target) when pending order o fills on bar x, 'drop' if it ends unfilled or is skipped, else None."""
    if o.get("mkt"):
        e = x["o"]
        return e, e * (1 - TWIN_D), e * (1 + RR * TWIN_D)
    if x["t"] > o["exp_t"]:
        return "drop"
    if x["l"] > o["lim"]:
        return None
    e, sl, tp = min(x["o"], o["lim"]), o["sl"], o["tp"]
    if not sl < e:
        return "drop"
    if not tp or tp <= e:
        tp = e + RR * (e - sl)
    return (e, sl, tp) if net_rr(e, sl, tp) >= MIN_NET_RR else "drop"


def hit(p, x):
    if x["l"] <= p["stop"]:
        return min(x["o"], p["stop"])
    if x["h"] >= p["target"]:
        return max(x["o"], p["target"])
    return None


def trades(b, mode="rule", rng=None, first=1):
    """The backtest: (entry_t, entry_px, exit_t, exit_px), oldest first."""
    sh = swings(b) if mode == "rule" else []
    out, pos, pend = [], None, None
    for i in range(first, len(b)):
        x = b[i]
        if pend and pos is None:
            f = fill(pend, x)
            if f is not None:
                pend = None
                if f != "drop":
                    pos = dict(entry=f[0], stop=f[1], target=f[2], t=x["t"])
        if pos:
            px = hit(pos, x)
            if px is not None:
                out.append((pos["t"], pos["entry"], x["t"], px)); pos = None
        if pos is None and pend is None and i < len(b) - 1:
            pend = signal(b, i, sh) if mode == "rule" else (dict(mkt=True) if rng.random() < TWIN_P else None)
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px * (1 - COST)
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen, pend = s.setdefault("seen", {}), s.setdefault("pend", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    sh = swings(bars) if mode == "rule" else []
    usd = s["start_usd"] / len(SYMS)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        if sym in pend and sym not in s["pos"]:
            f = fill(pend[sym], x)
            if f is not None:
                o = pend.pop(sym)
                if f != "drop" and s["cash"] >= usd * (1 + COST):
                    e = f[0]
                    s["cash"] -= usd * (1 + COST)
                    s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, stop=f[1], target=f[2],
                                         entry_t=x["t"], t=iso(x["t"]), why=o["why"])
                    s["log"].append(dict(kind="buy", t=iso(x["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=o["why"]))
        p = s["pos"].get(sym)
        if p:
            px = hit(p, x)
            if px is not None:
                close(s, sym, px, x["t"], "ถึงเป้า swing high หรือ 2R" if px > p["entry"] else "หลุด stop ใต้ order block")
        if sym in s["pos"] or sym in pend:
            continue
        o = signal(bars, i, sh) if mode == "rule" else (dict(mkt=True) if rng.random() < TWIN_P else None)
        if o:
            o["t"] = iso(x["t"])
            o["why"] = ("FVG ขาขึ้น ตั้ง limit ที่ยอด order block %.6g" % o["lim"]) if mode == "rule" else "สุ่มแท่ง"
            pend[sym] = o
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_obsmc fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
