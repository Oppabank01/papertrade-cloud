#!/usr/bin/env python3
"""Forward paper test: buy a coin on Bitkub when its ask is 2%+ below Binance (opened 27 Nov 2026). Fake money only.

Why forward and not more backtest: the 27 Nov weird-idea hunt found Bitkub coins that trade 2%+ cheaper than Binance
(THB/USDT adjusted) and buying them then selling when the gap closes made +2.8% per trade on next-minute-open fills
(n 361, every year since 2019), but only +0.4% when filled at the worst price inside the minute. The whole edge sits
inside the bid-ask spread, so only real quotes can settle it. This account trades on the live Bitkub order book.
Rule: each cloud run (about every 5 min), for every Bitkub coin with at least 5M THB traded in 24 h that Binance also
lists against USDT: premium = Bitkub lowest ask / USDT_THB mid / Binance last - 1. If premium <= -2% (and > -25%,
a cap against tickers that are different coins on the two venues, e.g. LUNA), buy at the Bitkub ask, 10% of the start, at most 5 open. Sell at the Bitkub highest bid when
bid / USDT_THB mid / Binance last - 1 >= -0.5%, or after 6 h. 0.25% per side (Bitkub taker). No hedge.
Who loses: Thai sellers dumping on Bitkub in a hurry (panic, or cashing out to THB) below the global price.
Thai users can trade this for real (Bitkub is licensed in Thailand). If Bitkub blocks GitHub's runners the script
prints the error and books nothing.
  state_fwd_bitkubgap.json        the rule
  state_fwd_bitkubgap_twin.json   control: when the rule buys, buy a random other liquid Bitkub coin at its ask,
                                  sell at its bid when the rule's trade closes
  python3 fwd_bitkubgap.py"""
import json, random, time, urllib.request
from byttrade import iso, load, save

COST, SIZE, MAXOPEN, ENTER, EXIT, HOLD, MINVOL = 0.0025, 0.10, 5, -0.02, -0.005, 6 * 3600 * 1000, 5e6
BK = "https://api.bitkub.com/api/v3/market/ticker"
BN = "https://data-api.binance.vision/api/v3/ticker/price"
ACCOUNTS = {"state_fwd_bitkubgap.json": ("rule", "ซื้อเหรียญบน Bitkub ที่ราคาขายถูกกว่า Binance 2% ขึ้นไป ขายเมื่อส่วนต่างเหลือไม่ถึง 0.5% หรือครบ 6 ชม. (ราคาจริงจากกระดาน)"),
            "state_fwd_bitkubgap_twin.json": ("random", "Bitkub ส่วนต่างราคา ตัวควบคุม: ซื้อเหรียญสุ่มบน Bitkub ตอนท่าหลักซื้อ ขายพร้อมกัน")}


def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())


def quotes(bk, bn):
    """{coin: (ask premium, bid premium, ask thb, bid thb)} for liquid Bitkub coins also on Binance."""
    t = {x["symbol"]: x for x in bk}
    u = t["USDT_THB"]
    usdt = (float(u["highest_bid"]) + float(u["lowest_ask"])) / 2
    px = {x["symbol"][:-4]: float(x["price"]) for x in bn if x["symbol"].endswith("USDT")}
    out = {}
    for sym, x in t.items():
        c = sym.split("_")[0]
        if not sym.endswith("_THB") or c == "USDT" or c not in px or px[c] <= 0 or float(x["quote_volume"]) < MINVOL:
            continue
        a, b = float(x["lowest_ask"]), float(x["highest_bid"])
        if a <= 0 or b <= 0:
            continue
        out[c] = (a / usdt / px[c] - 1, b / usdt / px[c] - 1, a, b)
    return out


def buy(s, c, q, now, why, link=None):
    usd = min(s["start_usd"] * SIZE, s["cash"])
    if usd <= 0:
        return
    s["cash"] -= usd * (1 + COST)
    s["pos"][c] = dict(side="long", coin=c, qty=usd / q[2], entry=q[2], last=q[3], usd=usd, t=iso(now), t_ms=now, link=link, prem=round(q[0], 4))
    s["log"].append(dict(kind="buy", t=iso(now), coin=c, px=q[2], usd=usd, why=why))


def sell(s, c, q, now, why):
    p = s["pos"].pop(c)
    px = q[3] if q else p["last"]
    s["cash"] += p["qty"] * px * (1 - COST)
    s["log"].append(dict(kind="sell", t=iso(now), coin=c, px=px, usd=p["usd"], ret=round(px / p["entry"] - 1, 6),
                         pnl=p["qty"] * px * (1 - COST) - p["usd"] * (1 + COST), cost_side=COST, why=why))


def step(rule, twin, Q, now, rng):
    """One run: exits first, then entries. The twin mirrors the rule's entries and exits on a random coin."""
    closed = []
    for c, p in list(rule["pos"].items()):
        q = Q.get(c)
        if q:
            p["last"] = q[3]
        if q and q[1] >= EXIT:
            sell(rule, c, q, now, f"ส่วนต่างเหลือ {q[1]:+.1%}"); closed.append(c)
        elif now - p["t_ms"] >= HOLD:
            sell(rule, c, q, now, "ครบ 6 ชม."); closed.append(c)
    for c, p in list(twin["pos"].items()):
        q = Q.get(c)
        if q:
            p["last"] = q[3]
        if p["link"] in closed or p["link"] not in rule["pos"]:
            sell(twin, c, q, now, "ท่าหลักขายแล้ว")
    for c, q in sorted(Q.items(), key=lambda kv: kv[1][0]):
        if len(rule["pos"]) >= MAXOPEN or not (-0.25 < q[0] <= ENTER) or c in rule["pos"] or c in closed:
            continue
        buy(rule, c, q, now, f"Bitkub ถูกกว่า Binance {q[0]:+.1%}")
        others = [k for k in Q if k != c and k not in twin["pos"]]
        if others:
            k = rng.choice(others)
            buy(twin, k, Q[k], now, f"สุ่มคู่กับ {c}", link=c)


def main():
    now, rng = time.time() * 1000, random.Random()
    try:
        Q = quotes(get(BK), get(BN))
    except Exception as e:
        print("fwd_bitkubgap fetch failed", type(e).__name__)
        return
    (fr, (_, lr)), (ft, (_, lt)) = ACCOUNTS.items()
    rule, twin = load(fr, lr), load(ft, lt)
    step(rule, twin, Q, now, rng)
    save(fr, rule); save(ft, twin)


if __name__ == "__main__":
    main()
