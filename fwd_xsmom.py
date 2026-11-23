#!/usr/bin/env python3
"""Forward paper test of weekly cross-sectional momentum among big coins, opened 23 Nov 2026. Fake money only.

Rule: every Monday at the 00:00 UTC daily open, rank the 27 coins below by their return over the last 28 days (open to open)
and hold the top 3, a third of the account each, until next Monday. A coin that stays in the top 3 is not sold and rebought
(no cost); it still books one "trade" per week so the weekly result is counted. 0.35% per side on coins that change.
Backtest 2018-2026 (Binance daily, coins listed today, so survivorship bias in both legs): top 3 +1.38%/week after costs,
equal-weight all 27 +1.10%, bottom 3 +0.42%; random 3 a week (paying full turnover) +0.50%, p < 0.01. But it trailed the
equal-weight basket in 2021, 2022, 2025 and 2026 (2026: -68% vs -37%), so the recent edge is doubtful. Settings chosen by me
(28 d, top 3) from 6 tried. The test replay of the last 139 Mondays: top 3 -80%, all coins -63%. Opened because the user wants weak ideas tried live.
  state_fwd_xsmom.json        the rule
  state_fwd_xsmom_twin.json   control: all eligible coins equal weight, same Monday schedule and cost
  python3 fwd_xsmom.py"""
import time
import byttrade as B
from byttrade import iso, load, save

COST, LOOK, K = 0.0035, 28, 3
DAY = 86400 * 1000
COINS = "BTC ETH BNB SOL XRP ADA DOGE TRX AVAX LINK DOT LTC BCH XLM ATOM ETC FIL NEAR UNI AAVE HBAR ICP APT ARB OP SUI INJ".split()
ACCOUNTS = {"state_fwd_xsmom.json": ("top", "โมเมนตัมข้ามเหรียญ: ทุกจันทร์ถือ 3 เหรียญที่ขึ้นแรงสุดใน 28 วัน จาก 27 เหรียญใหญ่ (backtest ชนะสุ่ม แต่ปี 2025-26 แพ้ถือทุกเหรียญ)"),
            "state_fwd_xsmom_twin.json": ("all", "โมเมนตัมข้ามเหรียญ ตัวควบคุม: ถือทุกเหรียญเท่าๆ กัน ปรับทุกจันทร์")}


def fetch_daily(sym):
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=1d")
    try:
        return B.fetch(sym)
    finally:
        B.URL = old


def mondays_after(t0, px):
    """Monday 00:00 UTC opens after t0 that the BTC series already has."""
    return sorted(d for d in px["BTC"] if d > t0 and (d // DAY + 3) % 7 == 0)


def pick(px, d, mode):
    el = [c for c in px if d in px[c] and d - LOOK * DAY in px[c]]
    if mode == "all":
        return el
    return sorted(el, key=lambda c: -(px[c][d] / px[c][d - LOOK * DAY]))[:K]


def week(s, px, d, mode):
    new = pick(px, d, mode)
    for c, p in list(s["pos"].items()):
        if d not in px.get(c, {}):
            continue                                  # no price for this coin today: keep holding, try next week
        price = px[c][d]
        value = p["qty"] * price
        out = value * COST if c not in new else 0.0
        s["pos"].pop(c)
        s["cash"] += value - out
        s["log"].append(dict(kind="sell", t=iso(d), coin=c, side="long", px=price, usd=p["usd"], ret=round(price / p["entry"] - 1, 6),
                             pnl=value - out - p["usd"], cost_side=COST, why="ครบสัปดาห์" + ("" if c in new else " หลุดอันดับ")))
    new = [c for c in new if c not in s["pos"]]
    if not new:
        return
    usd = s["cash"] / len(new)
    for c in new:
        price = px[c][d]
        cost = usd * COST if c not in s.get("last_pick", []) else 0.0
        s["cash"] -= usd
        s["pos"][c] = dict(side="long", d=1, qty=(usd - cost) / price, entry=price, last=price, usd=usd, t=iso(d), why=f"อันดับ {mode}")
        s["log"].append(dict(kind="buy", t=iso(d), coin=c, side="long", px=price, usd=usd, why="ติด 3 อันดับแรก 28 วัน" if mode == "top" else "ถือทุกเหรียญ"))
    s["last_pick"] = sorted(s["pos"])


def step(s, px, mode, closes=None):
    if s.get("seen") is None:
        s["seen"] = max(px["BTC"])
        return
    for d in mondays_after(s["seen"], px):
        week(s, px, d, mode)
        s["seen"] = d
    for c, p in s["pos"].items():
        if c in (closes or {}):
            p["last"] = closes[c]


def main():
    states = {f: load(f, label) for f, (mode, label) in ACCOUNTS.items()}
    now = time.time() * 1000
    last_monday = (now // DAY - (now // DAY + 3) % 7) * DAY
    if all(s.get("seen") is not None and s["seen"] >= last_monday for s in states.values()) and int(now / 1000) % 21600 > 1800:
        return                                         # nothing new: skip the 27 downloads (marks still refresh about every 6 h)
    px, closes = {}, {}
    for c in COINS:
        try:
            b = fetch_daily(c + "USDT")
            px[c], closes[c] = {x["t"]: x["o"] for x in b}, b[-1]["c"]
        except Exception as e:
            print("fwd_xsmom fetch failed", c, type(e).__name__)
    if "BTC" not in px:
        return
    for f, (mode, label) in ACCOUNTS.items():
        step(states[f], px, mode, closes)
        save(f, states[f])


if __name__ == "__main__":
    main()
