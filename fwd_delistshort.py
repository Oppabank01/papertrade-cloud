#!/usr/bin/env python3
"""Forward paper test: short a coin 15 min after Binance announces its delisting (opened 26 Nov 2026). Fake money only.

Rule (R6 from the 26 Nov strategy hunt): when Binance posts "Binance Will Delist A, B on ..." (spot) or "Binance Futures
Will Delist AUSDT ..." in its delisting catalog, short each named coin at the open of the 1-minute bar 15 min after the
post, cover 4 h later or when a 1-minute high reaches +30% (fill max(open, stop) x 1.001). 1x, 10% of the start per coin,
at most 40% per announcement, 0.15% per side. Funding ignored (backtest mean over 24 h after the post: -0.05%).
Prices: Binance spot 1 m klines (data-api.binance.vision, reachable from GitHub), else Hyperliquid perp 1 m candles; the
perp itself (fapi) answers 451 to GitHub's US runners, so spot stands in for it. The whole trade is booked after the
4 h window from the bars, so a 5-minute cron that misses runs still books the same trade.
Who loses: late holders and people forced to sell before the delisting date.
Backtest (Binance USDT-M perps, Jul 2025 - Nov 2026, perp prices, funding included): 97 trades from 38 announcements,
mean +7.5%, median +7.0%, 80% winners, without the best 5 +6.1%; random times in the 30 days before the post -0.06%
(best of 300 seeds +1.1%). But the edge shrinks: Jul 2024 - Jun 2025 +1.7% (n 21, 48% winners), Jun - Nov 2026 +1.9%
(n 19). Expect about +2% per trade, not +7%. 33 settings tried, all positive. About 2 to 6 trades a month.
  state_fwd_delistshort.json        the rule
  state_fwd_delistshort_twin.json   control: short a random small alt over the same window, same size, cost and exits
  python3 fwd_delistshort.py"""
import json, random, re, time, urllib.request
from byttrade import iso, load, save

COST, SIZE, CAP, LAG, HOLD, STOP, M = 0.0015, 0.10, 0.40, 15, 240, 0.30, 60 * 1000
LIST = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&catalogId=161&pageNo=1&pageSize=20"
DETAIL = "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode={}"
KL = "https://data-api.binance.vision/api/v3/klines?symbol={}USDT&interval=1m&startTime={}&limit={}"
HL = "https://api.hyperliquid.xyz/info"
STABLE = {"USDP", "TUSD", "FDUSD", "USDC", "DAI", "AEUR", "EUR", "BUSD", "USDE", "PAXG"}
ALTS = "ONE ZIL IOTA KAVA CELO ROSE ANKR SKL GLMR ICX ONT QTUM RVN SXP DUSK CHZ MASK COTI CTSI LRC KNC STORJ BAT ZRX YGG MAGIC HIGH ACH".split()
ACCOUNTS = {"state_fwd_delistshort.json": ("rule", "short เหรียญหลัง Binance ประกาศ delist: เข้า 15 นาทีหลังประกาศ ถือ 4 ชม. stop +30% (backtest 97 ไม้ เฉลี่ย +7.5% แต่ช่วงหลังเหลือราว +2%)"),
            "state_fwd_delistshort_twin.json": ("random", "short หลังประกาศ delist ตัวควบคุม: short เหรียญเล็กสุ่ม ช่วงเวลาเดียวกัน")}


def get(u, body=None):
    h = {"User-Agent": "Mozilla/5.0", "clienttype": "web", "Content-Type": "application/json"}
    rq = urllib.request.Request(u, json.dumps(body).encode() if body else None, h)
    return json.loads(urllib.request.urlopen(rq, timeout=20).read())


def coins(title, body=""):
    """Coins named in a delisting title; [] for pair, margin, Alpha or other notices."""
    if re.match(r"Binance Will Delist ", title) and not re.search(r"Trading Pair|Margin|Alpha", title):
        part = title[len("Binance Will Delist "):].split(" on ")[0]
        out = [c.strip() for c in re.split(r",| and ", part) if c.strip()]
    elif title.startswith("Binance Futures Will Delist"):
        out = re.findall(r"\b([A-Z0-9]{2,15})USDT\b", title + " " + body)
        out = [re.sub(r"^1000+", "", c) for c in out]
    else:
        return []
    return [c for c in dict.fromkeys(out) if re.fullmatch(r"[A-Z0-9]{2,15}", c) and c not in STABLE]


def bars(sym, t0, n, kl=get):
    """[(t, open, high, close)] 1 m from t0: Binance spot, else Hyperliquid perp. [] when neither has it."""
    try:
        k = kl(KL.format(sym, t0, n))
        if k and k[0][0] == t0:
            return [(x[0], float(x[1]), float(x[2]), float(x[4])) for x in k]
    except Exception:
        pass
    try:
        k = kl(HL, dict(type="candleSnapshot", req=dict(coin=sym, interval="1m", startTime=t0, endTime=t0 + n * M)))
        if k and k[0]["t"] == t0:
            return [(x["t"], float(x["o"]), float(x["h"]), float(x["c"])) for x in k]
    except Exception:
        pass
    return []


def trade(b):
    """(exit price, why) for a short entered at b[0] open, held HOLD minutes, stop at +STOP checked on highs."""
    e = b[0][1]
    lvl = e * (1 + STOP)
    for t, o, h, c in b[:HOLD]:
        if h >= lvl:
            return max(o, lvl) * 1.001, "stop +30%"
    return b[min(HOLD, len(b)) - 1][3], "ครบ 4 ชม."


def step(s, new, now, rng, kl=get):
    """new: (key, [coins], post ms) announcements not seen before. Books a trade once its 4 h window is over."""
    q = s.setdefault("queue", [])
    for key, cs, ts in new:
        t0 = (ts // M + 1) * M + (LAG - 1) * M       # open of the 1 m bar 15 min after the post
        cs = cs[:int(CAP / SIZE)]
        picks = cs if s["mode"] == "rule" else rng.sample(ALTS, len(cs))
        for c, p in zip(cs, picks):
            q.append(dict(key=f"{key}-{c}", sym=p, notice=c, t0=t0))
    for x in list(q):
        if now < x["t0"] + (HOLD + 2) * M:
            continue
        q.remove(x)
        b = bars(x["sym"], x["t0"], HOLD, kl)
        if len(b) < HOLD * 0.9:
            s["log"].append(dict(kind="skip", t=iso(now), coin=x["sym"], why=f"ไม่มีแท่ง 1 นาทีครบ ({len(b)})"))
            continue
        px, why = trade(b)
        usd = min(s["start_usd"] * SIZE, s["cash"])
        e = b[0][1]
        ret = 1 - px / e
        s["cash"] -= usd * COST
        pnl = usd * ret - usd * (1 - ret) * COST
        s["cash"] += pnl
        s["log"].append(dict(kind="buy", t=iso(x["t0"]), coin=x["sym"], side="short", px=e, usd=usd, why=f"Binance delist {x['notice']}"))
        s["log"].append(dict(kind="sell", t=iso(b[-1][0]), coin=x["sym"], side="short", px=px, usd=usd, ret=round(ret, 6), pnl=pnl,
                             cost_side=COST, why=why))


def main():
    now, rng = time.time() * 1000, random.Random()
    try:
        arts = get(LIST)["data"]["catalogs"][0]["articles"]
    except Exception as e:
        print("fwd_delistshort list fetch failed", type(e).__name__)
        arts = None
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        s["mode"] = mode
        if s.get("seen") is None:                       # first run: remember what is already posted
            if arts is None:
                continue
            s["seen"] = [a["code"] for a in arts]
        new = []
        for a in arts or []:
            if a["code"] in s["seen"]:
                continue
            s["seen"].append(a["code"])
            body = ""
            if "Multiple" in a["title"]:
                try:
                    body = json.dumps(get(DETAIL.format(a["code"]))["data"])[:30000]
                except Exception:
                    pass
            cs = coins(a["title"], body)
            if not cs:
                continue
            if now - a["releaseDate"] < 30 * M:
                new.append((a["code"], cs, a["releaseDate"]))
            else:
                s["log"].append(dict(kind="skip", t=iso(now), coin=",".join(cs), why="เห็นประกาศช้ากว่า 30 นาที"))
        s["seen"] = s["seen"][-200:]
        step(s, new, now, rng)
        save(f, s)


if __name__ == "__main__":
    main()
