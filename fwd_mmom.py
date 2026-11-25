#!/usr/bin/env python3
"""Forward paper test of "morning direction carries into the 13:30 ET COMEX close", one of the effects that
Jitheandra98/strategy-research-lab (GitHub, Nov 2026, pre-registered gold-futures studies) found real (t 4.8) but smaller
than its costs. Rebuilt on Binance 30m bars by the scout on 25 Nov 2026; backtest in LABEL, opened at any p because the
user asked to try weak ideas too. Fake money only.

Mon-Fri, New York time: at the close of the 12:30 bar, r = that close / the open of the 08:30 bar - 1. r > 0 -> long,
r < 0 -> short, at the open of the 13:00 bar; out at its close (13:30, the COMEX gold close). One position per coin, one
third of the start per coin, 0.35% per side.
  state_fwd_mmom.json       PAXG (gold), BTC, ETH
  state_fwd_mmom_twin.json  control: the same bar on a coin flip (half the days), random side
  python3 fwd_mmom.py"""
import random
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
M30 = 30 * 60 * 1000
ET = ZoneInfo("America/New_York")
SYMS = ["PAXGUSDT", "BTCUSDT", "ETHUSDT"]   # my choice: PAXG stands in for gold futures; BTC and ETH as every scout account
OPEN, SIG, HOLD = 8 * 60 + 30, 12 * 60 + 30, 13 * 60   # COMEX gold 08:30 open and 13:30 close from the study; the
# 08:30 to 13:00 signal window and the single 13:00 to 13:30 bar are my reading of "morning direction into the close"
THR = 0.0                              # my choice: no size filter (0.5% and 1% were also backtested, see LABEL)
LABEL = ("ทิศเช้าถึงปิดตลาดทอง (Jitheandra98 งานวิจัยทองล่วงหน้า) PAXG BTC ETH แท่ง 30 นาที เวลานิวยอร์ก จันทร์ถึงศุกร์: "
         "ราคา 08:30 ถึง 13:00 ขึ้นซื้อ ลงขาย short ถือ 13:00 ถึง 13:30 "
         "(backtest Binance 30 นาที พ.ย. 63 ถึง 25 พ.ย. 69 หลังหัก 0.35%/ข้าง PAXG 1,521 ไม้ -0.71% BTC 1,571 ไม้ -0.69% "
         "ETH 1,570 ไม้ -0.71% ต่อไม้ ก่อนหัก -0.01/+0.01/-0.01% ตัวแฝดฝั่งสุ่ม -0.70/-0.70/-0.69% "
         "permutation 200 รอบ 3 ปีล่าสุด ดีสุดจาก 6 แบบ p 0.67/0.14/0.27 แท่งครึ่งชั่วโมงขยับน้อยกว่าต้นทุนไปกลับ 0.7%)")
ACCOUNTS = {"state_fwd_mmom.json": ("rule", LABEL),
            "state_fwd_mmom_twin.json": ("random", "ทิศเช้าถึงปิดตลาดทอง ตัวควบคุม: แท่งเดียวกัน วันสุ่มครึ่งหนึ่ง ฝั่งสุ่ม")}


def fetch_iv(sym, iv="30m"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def et(t):
    d = datetime.fromtimestamp(t / 1000, timezone.utc).astimezone(ET)
    return d.weekday(), d.hour * 60 + d.minute, d.date().isoformat()


def side(b, i, opens):
    """+1/-1/0 at the close of bar i (the 12:30 ET bar), opens = {ET date: open of its 08:30 bar}."""
    wd, m, dt = et(b[i]["t"])
    if wd > 4 or m != SIG or dt not in opens or i + 1 >= len(b) or et(b[i + 1]["t"])[1] != HOLD:
        return 0
    r = b[i]["c"] / opens[dt] - 1
    return 0 if abs(r) < THR or r == 0 else (1 if r > 0 else -1)


def trades(b):
    """The backtest (same trades as the scout's /tmp/scout_1719/bt.py mmom with thr 0, both sides): (entry t, side, entry, exit)."""
    out, opens = [], {}
    for i in range(len(b) - 1):
        wd, m, dt = et(b[i]["t"])
        if wd <= 4 and m == OPEN:
            opens[dt] = b[i]["o"]
        d = side(b, i, opens)
        if d:
            out.append((b[i + 1]["t"], d, b[i + 1]["o"], b[i + 1]["c"]))
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
    opens = {}
    for i, x in enumerate(bars):
        wd, m, dt = et(x["t"])
        if wd <= 4 and m == OPEN:
            opens[dt] = x["o"]
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            close(s, sym, x["c"], x["t"] + M30, "ครบ 13:30 นิวยอร์ก")
            continue
        if p:
            continue
        d = side(bars, i, opens)
        if mode == "random":
            d = rng.choice((1, -1)) if wd <= 4 and m == SIG and et(bars[i + 1]["t"])[1] == HOLD and rng.random() < 0.5 else 0
        if not d:
            continue
        e, t, usd = bars[i + 1]["o"], bars[i + 1]["t"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = ("เช้าขึ้น ซื้อ" if d > 0 else "เช้าลง short") if mode == "rule" else "สุ่มวันและฝั่ง"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=t, t=iso(t), why=why)
        s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_mmom fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
