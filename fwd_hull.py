#!/usr/bin/env python3
"""Forward paper test of CaffeSatoshi's Bitcoin Hull moving average trend posts (X, 18 and 25 Nov 2026: "Hull GR (72) on
the daily chart", price under a falling Hull = no recovery; the posts give no exact rule). Opened 26 Nov 2026 by the scout
as the closest mechanical version; backtest in LABEL, opened at any p because the user asked to try weak ideas too.
Fake money only.

On closed daily Binance bars (UTC), per coin: close above HMA72 and HMA72 above its value one bar before -> long at the
next open; out at the next open on the first close where either fails. One position per coin, half the start per coin,
0.35% per side.
  state_fwd_hull.json       BTC ETH
  state_fwd_hull_twin.json  control: random entries (1 in 16 free days), same exits
  python3 fwd_hull.py"""
import math, random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT"]          # BTC from the posts; ETH is my choice (a second coin, tested the same way)
N = 72                                 # from the post ("Hull GR (72) on the daily chart")
TWIN_P = 1 / 16                        # my choice: about twice the rule's entry rate, the twin leaves at once when the rule is off
# also mine: "price above a rising Hull" as the entry and its loss as the exit (the posts only read the chart this way),
# HMA = WMA(2 WMA(n/2) - WMA(n), sqrt n) as Alan Hull defines it, signals on closes, fills at the next open
LABEL = ("Hull MA 72 วัน (CaffeSatoshi) BTC ETH รายวัน: ปิดเหนือ HMA72 และ HMA72 ชี้ขึ้น ซื้อตอนเปิดวันถัดไป ออกเมื่อข้อใดข้อหนึ่งหลุด "
         "ไม้ละครึ่งทุน (backtest Binance รายวัน ส.ค. 60 ถึง 24 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 107 ไม้ +3.51% ต่อไม้ มัธยฐาน -1.81% "
         "ชนะ 36% ทบต้น +1,040% แพ้ถือเฉยๆ +1,296% ETH 99 ไม้ +5.68% ทบต้น +5,144% ชนะถือเฉยๆ +456% ตัวแฝดเข้าสุ่ม +0.79/+0.82% "
         "ตั้งแต่ 30 มิ.ย. 67 BTC 30 ไม้ +0.01% ETH 20 ไม้ +3.04% permutation 200 รอบ กริด 12 แบบ (HMA 50/72/100/150 x 3 กฎ) "
         "BTC ดีสุด +17.3% เทียบแท่งสลับ +7.6% p 0.104 ETH +16.3% เทียบ +9.0% p 0.174 ไม่ผ่าน)")
ACCOUNTS = {"state_fwd_hull.json": ("rule", LABEL),
            "state_fwd_hull_twin.json": ("random", "Hull MA 72 วัน ตัวควบคุม: เข้าสุ่ม 1 ใน 16 วัน ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def wma(x, n):
    w = list(range(1, n + 1))
    sw, out = sum(w), [None] * len(x)
    for i in range(n - 1, len(x)):
        v = x[i - n + 1:i + 1]
        if None not in v:
            out[i] = sum(a * b for a, b in zip(v, w)) / sw
    return out


def hma(c, n=N):
    a, b = wma(c, n // 2), wma(c, n)
    return wma([None if p is None or q is None else 2 * p - q for p, q in zip(a, b)], int(math.sqrt(n)))


def on(c, H, i):
    """None while the HMA is not ready, else True when the close is above a rising HMA."""
    if H[i] is None or H[i - 1] is None:
        return None
    return H[i] > H[i - 1] and c[i] > H[i]


def trades(b):
    """The backtest (same trades as the scout's /tmp/scout_0546/bt_hma.py run(b, 72, "both")): list of
    (entry t, entry, exit t, exit) on closed daily bars."""
    c = [x["c"] for x in b]
    H, pos, out = hma(c), None, []
    for i in range(1, len(b) - 1):
        g = on(c, H, i)
        if g is None:
            continue
        if pos is not None:
            if not g:
                out.append((pos[1], pos[0], b[i + 1]["t"], b[i + 1]["o"]))
                pos = None
            continue
        if g:
            pos = (b[i + 1]["o"], b[i + 1]["t"])
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, b, mode, rng):
    """b: daily bars of one coin, the last day may still be forming. Walks every closed day after s['seen'][sym]."""
    shut = [i for i in range(len(b)) if b[i]["closed"]]
    seen = s["seen"] if isinstance(s.get("seen"), dict) else {}
    s["seen"] = seen
    if sym not in seen:
        seen[sym] = b[shut[-1]]["t"]
        return
    c = [x["c"] for x in b]
    H = hma(c)
    for i in shut:
        if b[i]["t"] <= seen[sym] or i + 1 >= len(b) or i < 1:
            continue
        seen[sym] = b[i]["t"]
        g = on(c, H, i)
        if g is None:
            continue
        p = s["pos"].get(sym)
        if p:
            if b[i]["t"] >= p["entry_t"] and not g:
                close(s, sym, b[i + 1]["o"], b[i + 1]["t"], "ปิดต่ำกว่า HMA72" if c[i] <= H[i] else "HMA72 หันลง")
            continue
        if not (g if mode == "rule" else rng.random() < TWIN_P):
            continue
        e, t = b[i + 1]["o"], b[i + 1]["t"]
        usd = min(s["start_usd"] / len(SYMS), s["cash"] / (1 + COST))   # my choice: take what cash is left after losses
        if usd < 0.01:
            continue
        s["cash"] -= usd + usd * COST
        why = f"ปิด {c[i]:.2f} เหนือ HMA72 {H[i]:.2f} ที่ชี้ขึ้น" if mode == "rule" else "สุ่มเวลา"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=t, t=iso(t), why=why)
        s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = b[-1]["c"]


def main():
    rng = random.Random()
    bars = {}
    for sym in SYMS:
        try:
            bars[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_hull fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        for sym, b in bars.items():
            step(s, sym, b, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
