#!/usr/bin/env python3
"""Forward paper test: short a coin after Upbit announces a new listing (opened 24 Nov 2026). Fake money only.

Rule: when Upbit posts a new trading-support notice ("신규 거래지원") for a coin that already traded on Binance at least
3 days before, short it at the open of the second full hour after the notice (h1) and cover at h24 (23 h later).
1x, a quarter of the start per trade, 0.05% per side (Binance USDT perp taker), funding ignored (after a pump it is
usually positive, which pays shorts). Prices: Binance spot 1 h opens. Upbit blocks GitHub's runners, so the cloud reads the Mac's relay copy of the notice page.
Why: who loses is the late buyer chasing the Upbit pump. The pump itself is over within the first minute (long from
+1 min loses: median -0.6% over 15 min), but the fade lasts. Backtest of all 820 Upbit trade notices (Apr 2024 - Nov 2026),
70 listings of coins already on Binance: short h1 -> h24 mean +6.4%, median +7.5%, 81% winners (t 4.0); the same coins
7 days earlier -2.7%, 3 days earlier -3.5%, BTC in the same window -0.1%; first half +6.7%, second half +6.1%.
Worst trades -42%, -33%, -32%; the worst intraday run-up seen was about +57%, so no leverage here. Settings (h1, h24)
chosen by me from 5 tried. About 2 or 3 trades a month, so 50 trades take well over a year.
  state_fwd_upbitfade.json        the rule
  state_fwd_upbitfade_twin.json   control: short a random big alt over the same hours, same size and cost
  python3 fwd_upbitfade.py"""
import json, random, re, time, urllib.request
from datetime import datetime
from pathlib import Path
from byttrade import iso, load, save

COST, SIZE, H = 0.0005, 0.25, 3600 * 1000
NOTICES = "https://api-manager.upbit.com/api/v1/announcements?os=web&page=1&per_page=20&category=trade"
KL = "https://data-api.binance.vision/api/v3/klines?symbol={}USDT&interval=1h&startTime={}&limit={}"
RELAY = Path(__file__).parent / "data" / "upbit_notices.json"   # written by the Mac (crash.py upbit-pull in ../PaperTrade/agents.sh, every 2 min)
ALTS = "ETH SOL XRP ADA DOGE AVAX LINK DOT LTC BCH XLM ATOM NEAR UNI AAVE APT ARB OP SUI INJ".split()
ACCOUNTS = {"state_fwd_upbitfade.json": ("rule", "short เหรียญหลัง Upbit ประกาศรับเหรียญใหม่: เข้าชั่วโมงที่ 2 หลังประกาศ ถือ 23 ชม. (backtest 70 ไม้ เฉลี่ย +6.4% ชนะ 81%)"),
            "state_fwd_upbitfade_twin.json": ("random", "short หลังประกาศ Upbit ตัวควบคุม: short เหรียญใหญ่สุ่ม ช่วงเวลาเดียวกัน")}


def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())


def listings(notices):
    """(notice id, symbol, notice time ms) for each coin in a new-listing notice."""
    out = []
    for x in notices:
        t = x.get("title") or ""
        if "신규 거래지원" not in t:
            continue
        ts = datetime.fromisoformat(x.get("first_listed_at") or x["listed_at"]).timestamp() * 1000
        for sym in re.findall(r"\(([A-Z0-9]{2,10})\)", t.split("신규")[0]):
            out.append((f"{x.get('id')}-{sym}", sym, int(ts)))
    return out


def old_on_binance(sym, ts, kl=get):
    try:
        k = kl(KL.format(sym, ts - 3 * 86400 * 1000, 2))
    except Exception:
        return False
    return bool(k) and k[0][0] <= ts - 3 * 86400 * 1000 + H


def open_at(sym, t, kl=get):
    try:
        k = kl(KL.format(sym, t, 1))
    except Exception:
        return None
    return float(k[0][1]) if k and k[0][0] == t else None


def step(s, new, now, rng, kl=get):
    """new: (key, sym, notice ms) listings not seen before. Books entries and exits whose 1 h bar has opened."""
    q = s.setdefault("queue", [])
    for key, sym, ts in new:
        h0 = -(-ts // H) * H                            # first full hour at or after the notice
        q.append(dict(key=key, sym=sym if s["mode"] == "rule" else rng.choice(ALTS), notice=sym, entry_t=h0 + H, exit_t=h0 + 24 * H))
    for x in list(q):
        if now < x["entry_t"] + 60 * 1000:
            continue
        q.remove(x)
        px = open_at(x["sym"], x["entry_t"], kl)
        if px is None:
            s["log"].append(dict(kind="skip", t=iso(now), coin=x["sym"], why="ไม่มีราคา Binance ตอนเข้า"))
            continue
        usd = min(s["start_usd"] * SIZE, s["cash"])
        s["cash"] -= usd * COST
        s["pos"][x["key"]] = dict(side="short", d=-1, coin=x["sym"], qty=-usd / px, entry=px, last=px, usd=usd, exit_t=x["exit_t"],
                                  t=iso(x["entry_t"]), why=f"Upbit รับ {x['notice']}")
        s["log"].append(dict(kind="buy", t=iso(x["entry_t"]), coin=x["sym"], side="short", px=px, usd=usd, why=f"Upbit รับ {x['notice']}"))
    for k, p in list(s["pos"].items()):
        if now < p["exit_t"] + 60 * 1000:
            continue
        px = open_at(p["coin"], p["exit_t"], kl)
        if px is None:
            continue
        s["pos"].pop(k)
        ret = 1 - px / p["entry"]
        pnl = p["usd"] * ret - p["usd"] * (1 - ret) * COST
        s["cash"] += pnl
        s["log"].append(dict(kind="sell", t=iso(p["exit_t"]), coin=p["coin"], side="short", px=px, usd=p["usd"], ret=round(ret, 6), pnl=pnl,
                             cost_side=COST, why="ครบ 23 ชม."))


def main():
    now, rng = time.time() * 1000, random.Random()
    try:
        found = listings(get(NOTICES)["data"]["notices"])
    except Exception as e:                              # Upbit answers 403 to GitHub's runners: read the Mac's relay copy
        try:
            found = listings(json.loads(RELAY.read_text())["data"]["notices"])
        except Exception:
            print("fwd_upbitfade notices fetch failed", type(e).__name__, "and no relay copy")
            found = None
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        s["mode"] = mode
        if s.get("seen") is None:                       # first run: remember what is already posted, trade only new ones
            if found is None:
                continue
            s["seen"] = [k for k, _, _ in found]
        new = []
        for key, sym, ts in found or []:
            if key in s["seen"]:
                continue
            s["seen"].append(key)
            if now - ts < 6 * H and old_on_binance(sym, ts):
                new.append((key, sym, ts))
            else:
                s["log"].append(dict(kind="skip", t=iso(now), coin=sym, why="เหรียญใหม่บน Binance หรือประกาศเก่าเกิน 6 ชม."))
        s["seen"] = s["seen"][-200:]
        step(s, new, now, rng)
        save(f, s)


if __name__ == "__main__":
    main()
