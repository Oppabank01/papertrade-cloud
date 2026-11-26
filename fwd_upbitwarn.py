#!/usr/bin/env python3
"""Forward paper test: short a coin on Binance after Upbit designates it a trade-caution coin (opened 27 Nov 2026). Fake money only.

Rule (closest miss of the 27 Nov round-2 hunt, opened to test before rejecting): when Upbit posts a notice designating
a coin "거래 유의 종목 지정" (trade caution), short it at the first 1-hour open at least 2 minutes after the notice (and
after this account first saw it), cover 72 h later or when a 1 h high reaches +15% (fill max(open, stop) x 1.001).
1x, a quarter of the start per coin, 0.15% per side, funding ignored. Prices: Binance spot 1 h klines
(data-api.binance.vision). Upbit answers 403 to GitHub's runners, so the cloud falls back to the Mac's relay copy
(data/upbit_notices.json, the same one fwd_upbitfade reads). The trade is booked after its 72 h from the bars.
Who loses: holders who wait for Upbit to lift the caution while Korean traders sell ahead of a possible delisting.
Backtest (all 823 Upbit trade notices 2017-2026): n 42, mean +4.36%, median +4.57%, 69% winners, without best 5 +1.61%,
random hours in the same coin +0.55%; but the second half is only +0.89% (first +7.83%). A few trades a month at most.
  state_fwd_upbitwarn.json        the rule
  state_fwd_upbitwarn_twin.json   control: short a random big alt over the same 72 h, same size, cost and exits
  python3 fwd_upbitwarn.py"""
import json, random, re, time, urllib.request
from datetime import datetime
from pathlib import Path
from byttrade import iso, load, save

COST, SIZE, HOLD, STOP, H = 0.0015, 0.25, 72, 0.15, 3600 * 1000
NOTICES = "https://api-manager.upbit.com/api/v1/announcements?os=web&page=1&per_page=20&category=trade"
KL = "https://data-api.binance.vision/api/v3/klines?symbol={}USDT&interval=1h&startTime={}&limit={}"
RELAY = Path(__file__).parent / "data" / "upbit_notices.json"
ALTS = "ETH SOL XRP ADA DOGE AVAX LINK DOT LTC BCH XLM ATOM NEAR UNI AAVE APT ARB OP SUI INJ".split()
ACCOUNTS = {"state_fwd_upbitwarn.json": ("rule", "short เหรียญหลัง Upbit ขึ้นเตือนเป็นเหรียญที่ต้องระวัง ถือ 72 ชม. stop +15% (backtest 42 ไม้ เฉลี่ย +4.4% แต่ช่วงหลังเหลือ +0.9%)"),
            "state_fwd_upbitwarn_twin.json": ("random", "short หลัง Upbit เตือน ตัวควบคุม: short เหรียญใหญ่สุ่ม ช่วงเวลาเดียวกัน")}


def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())


def warnings(notices):
    """(key, symbol, notice ms) for each coin newly designated trade-caution (not extensions or lifts)."""
    out = []
    for x in notices:
        t = x.get("title") or ""
        if not ("유의 종목 지정" in t or "유의종목 지정" in t) or "연장" in t or "해제" in t:
            continue
        ts = int(datetime.fromisoformat(x.get("first_listed_at") or x["listed_at"]).timestamp() * 1000)
        for sym in dict.fromkeys(re.findall(r"\(([A-Z0-9]{2,10})\)", t)):
            out.append((f"{x.get('id')}-{sym}", sym, ts))
    return out


def trade(b):
    """(exit price, why) for a short entered at b[0] open, HOLD 1 h bars, stop +STOP on highs."""
    lvl = b[0][1] * (1 + STOP)
    for t, o, h, c in b[:HOLD]:
        if h >= lvl:
            return max(o, lvl) * 1.001, "stop +15%"
    return b[HOLD - 1][3], "ครบ 72 ชม."


def step(s, new, now, rng, kl=get):
    """new: (key, sym, notice ms, seen ms). Queues shorts, books them once 72 h of bars exist."""
    q = s.setdefault("queue", [])
    for key, sym, ts, seen in new:
        t0 = -(-max(ts + 2 * 60 * 1000, seen) // H) * H       # first 1 h open at or after both
        q.append(dict(key=key, sym=sym if s["mode"] == "rule" else rng.choice(ALTS), notice=sym, t0=t0))
    for x in list(q):
        if now < x["t0"] + HOLD * H + 60 * 1000:
            continue
        q.remove(x)
        try:
            k = kl(KL.format(x["sym"], x["t0"], HOLD))
        except Exception as e:
            q.append(x)
            print("fwd_upbitwarn klines", type(e).__name__)
            continue
        b = [(r[0], float(r[1]), float(r[2]), float(r[4])) for r in k]
        if len(b) < HOLD or b[0][0] != x["t0"]:
            s["log"].append(dict(kind="skip", t=iso(now), coin=x["sym"], why=f"ไม่มีแท่ง Binance ครบ ({len(b)})"))
            continue
        px, why = trade(b)
        e = b[0][1]
        usd = min(s["start_usd"] * SIZE, s["cash"])
        ret = 1 - px / e
        s["cash"] -= usd * COST
        pnl = usd * ret - usd * (1 - ret) * COST
        s["cash"] += pnl
        s["log"].append(dict(kind="buy", t=iso(x["t0"]), coin=x["sym"], side="short", px=e, usd=usd, why=f"Upbit เตือน {x['notice']}"))
        s["log"].append(dict(kind="sell", t=iso(b[HOLD - 1][0] + H), coin=x["sym"], side="short", px=px, usd=usd, ret=round(ret, 6), pnl=pnl,
                             cost_side=COST, why=why))


def main():
    now, rng = time.time() * 1000, random.Random()
    try:
        found = warnings(get(NOTICES)["data"]["notices"])
    except Exception as e:                              # 403 on GitHub's runners: the Mac's relay copy
        try:
            found = warnings(json.loads(RELAY.read_text())["data"]["notices"])
        except Exception:
            print("fwd_upbitwarn notices fetch failed", type(e).__name__, "and no relay copy")
            found = None
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        s["mode"] = mode
        if s.get("seen") is None:                       # first run: remember what is already posted
            if found is None:
                continue
            s["seen"] = [k for k, _, _ in found]
        new = []
        for key, sym, ts in found or []:
            if key in s["seen"]:
                continue
            s["seen"].append(key)
            if now - ts < 6 * H:
                new.append((key, sym, ts, now))
            else:
                s["log"].append(dict(kind="skip", t=iso(now), coin=sym, why="เห็นประกาศช้ากว่า 6 ชม."))
        s["seen"] = s["seen"][-200:]
        step(s, new, now, rng)
        save(f, s)


if __name__ == "__main__":
    main()
