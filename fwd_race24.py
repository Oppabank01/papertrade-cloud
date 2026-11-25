#!/usr/bin/env python3
"""Forward paper test of masadawasesa-cloud/btc-race-bot (GitHub, Nov 2026, a make.fun "Race a BTC trading bot live for 24
hours" entry): confirmed-strength hold with a 2.5% trailing stop, long only. Opened 25 Nov 2026 by the scout; backtest in
LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

Each UTC day is one 24 h race, on closed 5m Binance bars (numbers from the README): flat with no entry yet today and the
close at least 0.5% above the close 12 bars (1 h) earlier -> long at the next open. Out at the next open when a close is
2.5% under the highest close since entry. One re-entry a day, only on a close above the peak before that exit. No entry by
the 11:55 bar -> long at the 12:00 open (its "halfway fallback"). Whatever is held sells at the close of the day's last bar.
One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_race24.json       BTC, ETH, SOL
  state_fwd_race24_twin.json  control: buys at a random bar of the first half of each day, same trail and day-end exit
  python3 fwd_race24.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
DAY, BAR = 86400 * 1000, 5 * 60 * 1000
PER = DAY // BAR                       # 288 bars a race
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the repo trades only cbBTC; ETH and SOL as every scout account
LOOK, STRONG, TRAIL = 12, 0.005, 0.025     # from the README: +0.5% over an hour, 2.5% under the highest close
HALF = PER // 2 - 1                    # from the README ("halfway fallback"); the bar before 12:00 UTC is my reading
# also mine: 5m bars (the race bar size is not in the README), the race reset at 00:00 UTC every day, the day-end sale
LABEL = ("ซื้อตามแรง (masadawasesa-cloud บอทแข่ง make.fun) BTC ETH SOL แท่ง 5 นาที แข่งวันละรอบตามวัน UTC: ปิดสูงกว่า 1 ชม. ก่อน 0.5% "
         "ออกเมื่อปิดต่ำกว่าปิดสูงสุด 2.5% เข้าใหม่ได้ 1 ครั้งเมื่อปิดเหนือจุดสูงสุดก่อนออก ไม่มีไม้ถึงเที่ยงซื้อ 12:00 ขายตอนจบวัน "
         "(backtest Binance 5 นาที 365 วันถึง 25 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 371 ไม้ -0.81% ETH 383 ไม้ -0.69% SOL 405 ไม้ "
         "-0.78% ต่อไม้ ก่อนหัก -0.11/+0.01/-0.08% ชนะ 24-29% ตัวแฝดเข้าสุ่ม -0.79/-0.72/-0.81% permutation 200 รอบ "
         "p 0.87/0.14/0.54 ไม่ต่างจากสุ่ม ช่วงนั้นถือเฉยๆ -33 ถึง -50%)")
ACCOUNTS = {"state_fwd_race24.json": ("rule", LABEL),
            "state_fwd_race24_twin.json": ("random", "ซื้อตามแรงแข่งรายวัน ตัวควบคุม: ซื้อแท่งสุ่มครึ่งแรกของวัน ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="5m"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def strong(b, i):
    return i >= LOOK and b[i]["c"] >= (1 + STRONG) * b[i - LOOK]["c"]


def trades(b):
    """The backtest (same legs as the scout's /tmp/scout_1719/bt2.py run): list of (entry t, entry, exit t, exit) over
    every whole UTC day in b after the first one."""
    out, k = [], 0
    while k < len(b) and b[k]["t"] % DAY:
        k += 1
    k += PER                           # the first whole day only feeds the 1 h look-back
    while k + PER <= len(b):
        if b[k + PER - 1]["t"] - b[k]["t"] != (PER - 1) * BAR:
            k += 1
            while k < len(b) and b[k]["t"] % DAY:
                k += 1
            continue
        pos, entries, peak, pre = None, 0, 0.0, None
        for i in range(k, k + PER):
            last = i == k + PER - 1
            if pos:
                peak = max(peak, b[i]["c"])
                if last:
                    out.append((pos[0], pos[1], b[i]["t"] + BAR, b[i]["c"])); pos = None; break
                if b[i]["c"] <= (1 - TRAIL) * peak:
                    out.append((pos[0], pos[1], b[i + 1]["t"], b[i + 1]["o"])); pos, pre = None, peak
                continue
            if last:
                break
            go = (strong(b, i) or i - k == HALF) if entries == 0 else (entries == 1 and pre is not None and b[i]["c"] > pre)
            if go:
                pos = (b[i + 1]["t"], b[i + 1]["o"]); entries += 1; peak = b[i + 1]["o"]
        k += PER
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen, race = s.setdefault("seen", {}), s.setdefault("race", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        day, k = x["t"] // DAY, (x["t"] % DAY) // BAR
        r = race.get(sym)
        if r is None or r["day"] != day:
            r = race[sym] = dict(day=day, entries=0, pre=None, rnd=rng.randrange(0, PER // 2))
        last = k == PER - 1
        p = s["pos"].get(sym)
        if p:
            if x["t"] < p["entry_t"]:
                continue
            p["hc"] = max(p["hc"], x["c"])
            if last:
                close(s, sym, x["c"], x["t"] + BAR, "จบวันแข่ง")
            elif x["c"] <= (1 - TRAIL) * p["hc"]:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "ปิดต่ำกว่าปิดสูงสุด 2.5%")
                r["pre"] = p["hc"]
            continue
        if last:
            continue
        if mode == "rule":
            go = (strong(bars, i) or k == HALF) if r["entries"] == 0 else (r["entries"] == 1 and r["pre"] is not None and x["c"] > r["pre"])
        else:
            go = r["entries"] == 0 and k == r["rnd"]
        if not go:
            continue
        e, t, usd = bars[i + 1]["o"], bars[i + 1]["t"], s["start_usd"] / 3
        if s["cash"] < usd * (1 + COST):
            continue
        r["entries"] += 1
        s["cash"] -= usd + usd * COST
        why = ("ซื้อตอนเที่ยง (ยังไม่มีไม้)" if k == HALF and r["entries"] == 1 and not strong(bars, i) else
               "ปิดสูงกว่า 1 ชม. ก่อน 0.5%" if r["entries"] == 1 else "ปิดเหนือจุดสูงสุดก่อนออก") if mode == "rule" else "สุ่มเวลา"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, hc=e, entry_t=t, t=iso(t), why=why)
        s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_race24 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
