#!/usr/bin/env python3
"""Forward paper test: short ETH after the Fear & Greed index drops 15+ points in a day (opened 27 Nov 2026). Fake money only.

Rule (closest miss of the 27 Nov weird-idea hunt, opened to test before rejecting): the alternative.me Fear & Greed
value for day D is published just after 00:00 UTC of D. If value(D) - value(D-1) <= -15, short ETH at the open of the
daily bar D+1 (24 h after publication), cover at the close of the 14th daily bar or when a daily high reaches +15%
(fill max(open, stop) x 1.001). One trade at a time, a quarter of the start, 0.15% per side, funding ignored.
Prices: Binance spot ETHUSDT daily klines (data-api.binance.vision, reachable from GitHub). The whole trade is booked
after its 14 days from the bars, like fwd_delistshort.
Who loses: late longs who keep buying the dip after a panic day while the selling continues.
Backtest 2018 - Nov 2026: n 45, mean +3.66%, median +4.42%, 62% winners, halves +3.61 / +3.70, random-day shorts -0.70%;
but without the best 5 only +0.45%, 2021 -5.8% over 8 trades, BTC version without best 5 -1.66%, and about 130 settings
were tried in this family. About one signal every two months.
  state_fwd_fgshort.json        the rule
  state_fwd_fgshort_twin.json   control: short ETH on random days (about one in 65), same exits
  python3 fwd_fgshort.py"""
import json, random, time, urllib.request
from byttrade import iso, load, save

COST, SIZE, DROP, HOLD, STOP, D = 0.0015, 0.25, 15, 14, 0.15, 86400 * 1000
FNG = "https://api.alternative.me/fng/?limit=10"
KL = "https://data-api.binance.vision/api/v3/klines?symbol=ETHUSDT&interval=1d&startTime={}&limit={}"
ACCOUNTS = {"state_fwd_fgshort.json": ("rule", "short ETH หลังดัชนี Fear & Greed ร่วง 15 จุดในวันเดียว ถือ 14 วัน stop +15% (backtest 45 ไม้ เฉลี่ย +3.7% แต่ตัด 5 ไม้ดีสุดเหลือ +0.5%)"),
            "state_fwd_fgshort_twin.json": ("random", "short ETH หลัง Fear & Greed ร่วง ตัวควบคุม: short วันสุ่ม ทางออกเดียวกัน")}


def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())


def signals(fng):
    """{day ms: drop} for every day whose value fell DROP+ points from the day before."""
    v = {int(x["timestamp"]) * 1000: int(x["value"]) for x in fng}
    return {d: v[d - D] - v[d] for d in v if d - D in v and v[d] - v[d - D] <= -DROP}


def trade(b):
    """(exit price, why) for a short entered at b[0] open, HOLD daily bars, stop +STOP on highs."""
    e = b[0][1]
    lvl = e * (1 + STOP)
    for t, o, h, c in b[:HOLD]:
        if h >= lvl:
            return max(o, lvl) * 1.001, "stop +15%"
    return b[HOLD - 1][3], "ครบ 14 วัน"


def step(s, days, now, rng, kl=get):
    """days: {day ms: drop} published so far. Queues entries for days not seen, books trades whose 14 days are over."""
    q = s.setdefault("queue", [])
    seen = s["seen"]
    for d in sorted(days):
        if d in seen:
            continue
        seen.append(d)
        hit = days[d] is not None if s["mode"] == "rule" else rng.random() < 1 / 65
        busy = any(x["t0"] + HOLD * D > d + D for x in q)
        if hit and not busy:
            q.append(dict(t0=d + D, why=f"Fear & Greed ร่วง {days[d]} จุด" if s["mode"] == "rule" else "วันสุ่ม"))
    s["seen"] = seen[-60:]
    for x in list(q):
        if now < x["t0"] + HOLD * D + 60 * 1000:
            continue
        q.remove(x)
        try:
            b = [(k[0], float(k[1]), float(k[2]), float(k[4])) for k in kl(KL.format(x["t0"], HOLD))]
        except Exception as e:
            q.append(x)
            print("fwd_fgshort klines", type(e).__name__)
            continue
        if len(b) < HOLD or b[0][0] != x["t0"]:
            s["log"].append(dict(kind="skip", t=iso(now), coin="ETH", why=f"แท่งรายวันไม่ครบ ({len(b)})"))
            continue
        px, why = trade(b)
        e = b[0][1]
        usd = min(s["start_usd"] * SIZE, s["cash"])
        ret = 1 - px / e
        s["cash"] -= usd * COST
        pnl = usd * ret - usd * (1 - ret) * COST
        s["cash"] += pnl
        s["log"].append(dict(kind="buy", t=iso(x["t0"]), coin="ETH", side="short", px=e, usd=usd, why=x["why"]))
        s["log"].append(dict(kind="sell", t=iso(b[HOLD - 1][0] + D), coin="ETH", side="short", px=px, usd=usd, ret=round(ret, 6), pnl=pnl,
                             cost_side=COST, why=why))


def main():
    now, rng = time.time() * 1000, random.Random()
    try:
        fng = get(FNG)["data"]
        hits = signals(fng)
        days = {int(x["timestamp"]) * 1000: hits.get(int(x["timestamp"]) * 1000) for x in fng}
    except Exception as e:
        print("fwd_fgshort fng fetch failed", type(e).__name__)
        days = None
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        s["mode"] = mode
        if s.get("seen") is None:                       # first run: only days published from now on
            if days is None:
                continue
            s["seen"] = sorted(days)
        step(s, days or {}, now, rng)
        save(f, s)


if __name__ == "__main__":
    main()
