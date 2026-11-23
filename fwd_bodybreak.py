#!/usr/bin/env python3
"""Forward paper test of Andrea Unger's daily "small body, range breakout" BTC system (The Cryptonomist, republished on
cryptonews.net 22 May 2026) on BTC, ETH, SOL (opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p because
the user asked to try weak ideas too). Fake money only.

Days are UTC days built from closed 1h Binance bars. If yesterday's body |close - open| < DFAC x its range (high - low),
today place a buy stop at yesterday's close + yesterday's range; long only. Filled at max(hour open, level) on the first
hour whose high reaches it. Then stop -SL and target +TP from the fill, checked hour by hour; a gap through either fills
at the hour's open; in the entry hour and in any hour that touches both, the stop counts (we cannot see the order inside
an hour). Not out by the end of the day -> out at the day's last hourly close. One position per coin, one third of the
start per coin, 0.35% per side. The article reports no costs (gross average about +0.45% per trade).
  state_fwd_bodybreak.json       BTC, ETH, SOL
  state_fwd_bodybreak_twin.json  control: random days (TWIN_P per day), buy at the day's first open, same exits
  python3 fwd_bodybreak.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch, DAY

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # the article shows BTC numbers and ETH/BNB/SOL curves; these three are my choice
DFAC = 0.75                        # the article's pick from its grid 0.50 to 1.00 step 0.05
GRID = [round(0.5 + 0.05 * k, 2) for k in range(11)]   # that grid, rerun inside the permutation test
SL, TP = 0.02, 0.10                # the article's first stop/target ($2,000 / $10,000 on $100,000)
TWIN_P = 1 / 8                     # my choice: about the rule's trade rate per coin-day in the backtest
LABEL = ("แท่งตัวเล็ก buy stop รายวัน BTC ETH SOL (Andrea Unger, Cryptonomist): เมื่อวานตัวแท่งเล็กกว่า 0.75 ของช่วง วันนี้ซื้อเมื่อทะลุปิดเมื่อวาน "
         "+ ช่วงเมื่อวาน stop -2% เป้า +10% ออกสิ้นวัน (backtest แท่ง 1 ชม. 2017-2026 หลังหัก 0.35%/ข้าง BTC 561 ไม้ -0.69% "
         "ETH 529 ไม้ -0.89% SOL 344 ไม้ -1.55% ก่อนหัก +0.01/-0.19/-0.85% ชนะ 19-27% ปี 2024+ -0.62/-0.90/-1.26% "
         "ตัวแฝดซื้อวันสุ่ม -0.62/-0.63/-0.70% แพ้ตัวแฝด permutation p 0.005 เพราะข้อมูลสลับแย่กว่า ไม่ใช่เพราะบวก)")
ACCOUNTS = {"state_fwd_bodybreak.json": ("rule", LABEL),
            "state_fwd_bodybreak_twin.json": ("random", "แท่งตัวเล็ก ตัวควบคุม: ซื้อวันสุ่มตอนเปิดวัน stop -2% เป้า +10% ออกสิ้นวันแบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def days(hb):
    """Complete UTC days from 1h bars (a day is complete once a bar of a later day exists): dict(t, o, h, l, c, hrs)."""
    out = []
    for x in hb:
        d = x["t"] // DAY * DAY
        if not out or out[-1]["t"] != d:
            out.append(dict(t=d, o=x["o"], h=x["h"], l=x["l"], c=x["c"], hrs=[x]))
        else:
            y = out[-1]
            y["h"], y["l"], y["c"] = max(y["h"], x["h"]), min(y["l"], x["l"]), x["c"]
            y["hrs"].append(x)
    return out[:-1]


def path(hrs, level):
    """Buy stop at level (None = buy the first open) then the SL/TP/end-of-day exit: (entry t, entry, exit, why, exit t)."""
    e = None
    for x in hrs:
        if e is None:
            if level is not None and x["h"] < level:
                continue
            t, e = x["t"], x["o"] if level is None else max(x["o"], level)
            stop, tp = e * (1 - SL), e * (1 + TP)
            if x["l"] <= stop:
                return t, e, stop, "stop ในชั่วโมงที่เข้า", x["t"]
            if x["h"] >= tp:
                return t, e, tp, "ถึงเป้า", x["t"]
            continue
        if x["o"] <= stop:
            return t, e, x["o"], "เปิดหลุด stop", x["t"]
        if x["l"] <= stop:
            return t, e, stop, "หลุด stop", x["t"]
        if x["o"] >= tp:
            return t, e, x["o"], "เปิดเหนือเป้า", x["t"]
        if x["h"] >= tp:
            return t, e, tp, "ถึงเป้า", x["t"]
    return None if e is None else (t, e, hrs[-1]["c"], "สิ้นวัน", hrs[-1]["t"] + 3600 * 1000)


def level(y, dfac=DFAC):
    """Yesterday's bar y -> today's buy-stop level, or None when the body is not small."""
    r = y["h"] - y["l"]
    return y["c"] + r if r > 0 and abs(y["c"] - y["o"]) < dfac * r else None


def trades(hb, dfac=DFAC, first=1, D=None):
    """The backtest (the scout's /tmp/scout_1115.py calls this): list of dict(t, d, e, x), oldest first."""
    D, out = D or days(hb), []
    for k in range(max(first, 1), len(D)):
        lv = level(D[k - 1], dfac)
        r = path(D[k]["hrs"], lv) if lv is not None else None
        if r:
            out.append(dict(t=r[0], d=1, e=r[1], x=r[2]))
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    D = days(bars)
    if sym not in seen:
        if D:
            seen[sym] = D[-1]["t"]
        return
    for k in range(1, len(D)):
        if D[k]["t"] <= seen[sym]:
            continue
        seen[sym] = D[k]["t"]
        if mode == "rule":
            lv = level(D[k - 1])
            r = path(D[k]["hrs"], lv) if lv is not None else None
            why = f"ตัวแท่งเมื่อวานเล็ก ทะลุ {lv:g}" if lv is not None else ""
        else:
            r = path(D[k]["hrs"], None) if rng.random() < TWIN_P else None
            why = "สุ่มวัน"
        if not r:
            continue
        t, e, x, why_out, tx = r
        usd = s["start_usd"] / 3
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += -usd - usd * COST
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=t, t=iso(t), why=why)
        s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
        close(s, sym, x, tx, why_out)


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_bodybreak fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
