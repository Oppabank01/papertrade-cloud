#!/usr/bin/env python3
"""Forward paper test of the 4H "close crosses the Rolling VWAP" rule (PridiL/rvwap-signals, build.py, Nov 2026: the 4H
close crossing TradingView's 3-day Rolling VWAP, cross up = LONG, cross down = SHORT, each cross scored 6 / 18 / 30 bars
later; published for 28 FX pairs and 9 indices, no results claimed), opened 26 Nov 2026 by the scout; backtest in LABEL,
opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 4h bars: the close goes from at or below the line to above it -> long at the next open; from at or above to
below -> short. Line = mean of (h+l+c)/3 over the last 18 bars (3 days); byttrade.fetch gives no volume, so this is the
time-weighted line (the backtest shows it within 0.1% per trade of the volume-weighted one). Out at the open 30 bars
after the entry (the repo's longest scoring horizon), no stop or target; the exit bar's close may signal again. One
position per coin, a quarter of the start per coin, 0.35% per side.
  state_fwd_rvwap.json       BTC, ETH, SOL, PAXG
  state_fwd_rvwap_twin.json  control: random entry bars (1 in 40 free bars) on the side of the line, same exit
  python3 fwd_rvwap.py"""
import random
from byttrade import iso, load, save, fetch

COST = 0.0035                 # per side, as every account here
W, HOLD = 18, 30              # 3 days of 4h bars (the repo's 4H window); 30 bars = the repo's longest scoring horizon
TWIN_P = 1 / 40               # my choice: about as often as the rule fires per coin (489 crosses in 20,305 BTC bars)
# my choices: Binance spot coins instead of FX and indices (PAXG stands in for XAUUSD), the time-weighted line, entry at
# the next open, exit at the open 30 bars later, one position per coin (crosses while holding are ignored)
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]
LABEL = ("4 ชม. ปิดตัดเส้น Rolling VWAP 3 วัน (PridiL rvwap-signals) BTC ETH SOL PAXG: ตัดขึ้น long ตัดลง short ถือ 30 แท่ง "
         "(backtest Binance 4 ชม. 2017-2026 หลังหัก 0.35%/ข้าง BTC 489 ไม้ -0.34% ต่อไม้ ก่อนหัก +0.36% ตัวแฝดเข้าสุ่ม +0.15% "
         "ETH 495 ไม้ -1.02% SOL 335 ไม้ -1.53% PAXG 335 ไม้ -0.61% permutation 200 รอบ กริด 6 แบบ BTC p 0.27 PAXG p 0.42 ไม่ผ่าน)")
ACCOUNTS = {"state_fwd_rvwap.json": ("rule", LABEL),
            "state_fwd_rvwap_twin.json": ("random", "Rolling VWAP cross ตัวควบคุม: เข้าสุ่มเวลาตามฝั่งของเส้น ออกแบบเดียวกัน")}


def line(b):   # same as the scout's /tmp/scout_0405/bt_rv.py rv(b, vol=False)
    out, s = [None] * len(b), 0.0
    for i, x in enumerate(b):
        s += (x["h"] + x["l"] + x["c"]) / 3
        if i >= W:
            y = b[i - W]
            s -= (y["h"] + y["l"] + y["c"]) / 3
        if i >= W - 1:
            out[i] = s / W
    return out


def signal(b, i, L):
    if i < W or L[i] is None or L[i - 1] is None:
        return 0
    c, pc = b[i]["c"], b[i - 1]["c"]
    return 1 if c > L[i] and pc <= L[i - 1] else -1 if c < L[i] and pc >= L[i - 1] else 0


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
    L = line(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < 1:
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] > p["entry_t"]:
            p["held"] = p.get("held", 0) + 1      # bars counted, not hours, so a gap in Binance data does not shift the exit
            if p["held"] >= HOLD:
                close(s, sym, x["o"], x["t"], f"ครบ {HOLD} แท่ง")
        if sym in s["pos"]:
            continue
        if mode == "rule":
            d = signal(bars, i, L)
        else:
            d = (1 if x["c"] > L[i] else -1) if i >= W and L[i] and rng.random() < TWIN_P else 0
        usd = s["start_usd"] / len(SYMS)
        if not d or (d > 0 and s["cash"] < usd * (1 + COST)):
            continue
        e, et = bars[i + 1]["o"], bars[i + 1]["t"]
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "ปิดตัดเส้น Rolling VWAP 3 วัน" if mode == "rule" else "สุ่มเวลา ตามฝั่งของเส้น"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=et, held=0, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_rvwap fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
