#!/usr/bin/env python3
"""Forward paper test of a long-only version of "Breakout 4h" from yourshivv/neextdrop-bot-lab (GitHub 25 Nov 2026: 4h
break of the 20-candle high, skipped when the market mood is weak or hot, fixed 6R target, 10-day limit; the owner's
backtest on 124 perps was the only bot above zero over 3 years). Opened 27 Nov 2026 by the scout; backtest in LABEL,
opened at any p because the user asked to try weak ideas too. Fake money only.

Mood, per day, from the closed 1d Binance bars of the ten coins below: breadth = share of coins with a close above their
EMA20; weak = breadth < 35% and BTC below its EMA20, hot = breadth > 65% and BTC above, else neutral. A 4h bar uses the
mood of the last day closed when the bar closes. On closed 4h bars, long only: flat, mood neutral and the close above the
highest high of the previous 20 bars -> buy at the next open, stop entry - 2 x ATR14 (Wilder), target entry + 6 x the
stop distance. Each closed bar: open at or below the stop -> fill at the open; low at or below the stop -> stop; high at
or above the target -> max(target, open); both touched = stop; else on the 60th bar since entry sell at its close.
One position per coin, one tenth of the start per coin, 0.35% per side.
  state_fwd_moodbrk.json       BTC ETH SOL BNB XRP ADA DOGE AVAX LINK LTC
  state_fwd_moodbrk_twin.json  control: random entry on neutral-mood bars (TWIN_P), same exits
  python3 fwd_moodbrk.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                  # per side, as every account here
DAY = 86400 * 1000
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT"]
# my choice: the ten large coins Faraz-khan04/strategy-lab uses, both for breadth and for trading (the repo uses 124 perps)
BRK, TGT_R, HOLD = 20, 6, 60   # from the repo: 20-candle high, 6R target, 10 days = 60 bars of 4h
EMA_N, WEAK, HOT = 20, 0.35, 0.65   # from the repo's mood rule (EMA20, 35% / 65%)
ATR_N, K = 14, 2.0             # my choice: the repo does not say where the stop is; 2 x ATR14 below entry
TWIN_P = 1 / 25                # my choice: about 1.5 x the backtest entry rate on neutral bars
# also mine: long only (spot), no shorts, no break-even move after +2R (live bot since 30 Oct), no streak guard,
# breadth needs at least 3 coins with an EMA20 that day (a coin whose fetch failed drops out of breadth that round),
# equal size per coin
LABEL = ("ทะลุกรอบ 4 ชม. กรองอารมณ์ตลาด (yourshivv/neextdrop-bot-lab Breakout 4h รุ่น long อย่างเดียว) 10 เหรียญใหญ่: "
         "ซื้อเมื่อปิดเหนือจุดสูงสุด 20 แท่ง เฉพาะวันที่ตลาดไม่อ่อนและไม่ร้อน (สัดส่วนเหรียญเหนือ EMA20 รายวันกับ BTC) "
         "stop 2 ATR14 เป้า 6R ถือไม่เกิน 10 วัน (backtest Binance 4 ชม. 2017 ถึง 27 พ.ย. 69 หลังหัก 0.35%/ข้าง รวม 943 ไม้ "
         "+0.82% ต่อไม้ +0.16R มัธยฐาน -3.75% ชนะ 30% ตัวแฝดเข้าสุ่มแพ้กฎ 6 ใน 10 เหรียญ ปี 2022 -3.90% ต่อไม้ "
         "permutation 200 รอบบน 6,000 แท่งล่าสุด กริด stop 2/3 ATR p BTC 0.164 ETH 0.090 SOL 0.134 BNB 0.010 "
         "XRP 0.179 ADA 0.468 DOGE 0.035 AVAX 0.269 LINK 0.010 LTC 0.398)")
ACCOUNTS = {"state_fwd_moodbrk.json": ("rule", LABEL),
            "state_fwd_moodbrk_twin.json": ("random", "ทะลุกรอบ 4 ชม. กรองอารมณ์ตลาด ตัวควบคุม: เข้าสุ่มแท่งที่ตลาดกลางๆ ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ema_above(d):
    """{day_open_t: close > EMA20} from daily bars (EMA seeded with the first 20-day mean)"""
    out, e, a = {}, None, 2 / (EMA_N + 1)
    for i, x in enumerate(d):
        if i < EMA_N - 1:
            continue
        e = sum(y["c"] for y in d[:EMA_N]) / EMA_N if i == EMA_N - 1 else e + a * (x["c"] - e)
        out[x["t"]] = x["c"] > e
    return out


def moods(daily):
    """{day_open_t: 'weak' | 'neutral' | 'hot'} from {sym: closed daily bars}"""
    ab = {s: ema_above(d) for s, d in daily.items()}
    if "BTCUSDT" not in ab:
        return {}
    out = {}
    for t in sorted(set().union(*[set(v) for v in ab.values()])):
        v = [ab[s][t] for s in ab if t in ab[s]]
        if t not in ab["BTCUSDT"] or len(v) < 3:
            continue
        br, btc = sum(v) / len(v), ab["BTCUSDT"][t]
        out[t] = "weak" if br < WEAK and not btc else "hot" if br > HOT and btc else "neutral"
    return out


def mood_of(mood, t):
    """mood known when the 4h bar opening at t closes: the last daily bar closed by then"""
    return mood.get(((t + H4) // DAY) * DAY - DAY)


def atr(b, n=ATR_N):
    out, a = [None] * len(b), 0.0
    for i in range(1, len(b)):
        tr = max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - b[i - 1]["c"]), abs(b[i]["l"] - b[i - 1]["c"]))
        a = tr if i == 1 else (a * (n - 1) + tr) / n
        if i >= n:
            out[i] = a
    return out


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px - p["qty"] * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why,
                         stop_set=p["stop"]))


def step(s, sym, bars, mood, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    a = atr(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            p["n"] = p.get("n", 0) + 1
            o, h, l = x["o"], x["h"], x["l"]
            hit = o if o <= p["stop"] else p["stop"] if l <= p["stop"] else max(p["tgt"], o) if h >= p["tgt"] else None
            if hit is not None:
                close(s, sym, hit, x["t"] + H4, "stop" if hit < p["entry"] else "ถึงเป้า 6R")
                exited = True
            elif p["n"] >= HOLD:
                close(s, sym, x["c"], x["t"] + H4, "ครบ 10 วัน")
                exited = True
        if sym in s["pos"] or exited or i < BRK or not a[i] or mood_of(mood, x["t"]) != "neutral":
            continue
        if mode == "rule":
            go = x["c"] > max(y["h"] for y in bars[i - BRK:i])
        else:
            go = rng.random() < TWIN_P
        if not go:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "ตลาดกลางๆ ปิดทะลุจุดสูงสุด 20 แท่ง" if mode == "rule" else "สุ่มแท่งที่ตลาดกลางๆ"
        stop, et = e - K * a[i], bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, stop=stop,
                             tgt=e + TGT_R * K * a[i], entry_t=et, t=iso(et), why=why, n=0)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=e, usd=usd, why=why, stop_set=stop))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, h4, daily = random.Random(), {}, {}
    for sym in SYMS:
        try:
            daily[sym] = [x for x in fetch_iv(sym) if x["closed"]]
            h4[sym] = fetch(sym)
        except Exception as e:
            print("fwd_moodbrk fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    if "BTCUSDT" not in daily:
        return   # no BTC bars, no mood: no action this round
    mood = moods(daily)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in h4.items():
            step(s, sym, bars, mood, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
