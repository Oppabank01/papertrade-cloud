#!/usr/bin/env python3
"""Perp paper accounts from the Fable research round (19 Nov 2026), fake money only. Prices: Hyperliquid perps
(mark price for fills, closed 1h candles for signals, current funding accrued each hour). The research used Binance
perps 2022-26; Hyperliquid's coin list and prices differ a little, so these accounts are the live check of that work.

  c_crashbounce_24h_500  top-30 perps by 24h volume: coin closed 24h <= -15% while BTC 24h <= -5% -> long, sell after 24h
  c_crashbounce_72h_500  same, sell after 72h
  n_crashshort_500       21:00 Bangkok: short top-30 perps whose last 6h <= -10% (max 5), cover at 09:00, each night booked
  n_low30short_500       21:00 Bangkok: short perps (24h volume >= $10M) closing at/below their prior 30-day low after a
                         12h drop of 5%+, up to the 5 biggest losers, whole account split equally, cover at 09:00
                         (Fable round 2 "rule A": closest overnight near-miss, a measurement account, not a pass)
  l_newlist_short_500    a perp that newly appears on Hyperliquid: short at the first UTC day after it lists (max 10),
                         cover after 30 days or at +50% against us
  u_upbit_buy_500        "buy only on big news" (user idea, 20 Nov): an Upbit new-listing notice (KRW or BTC/USDT market)
                         -> long that coin's Hyperliquid perp on the next run, stop -8%, trail 15% once +15%, max 16h.
                         Backtest of 120 Upbit notices 2024-26 (1m Binance/Bybit/OKX, entry 5 min after): 16h -6.8%, dead
  u_upbit_fade_500       same notices, short instead ("sell the news"), cover after 16h or at +25% against us.
                         Same backtest: +6.2% a trade, 73% win, but worst -71% and about 0 in 2026 Q3-Q4
  b_bnlist_buy_500       "Binance Will List X" notice -> long X's Hyperliquid perp, buy exits above.
                         Backtest only 21 notices 2023-26: 4h mean +9%, median +1%, a few big winners carry it

  python3 crash.py init 500 | run | report | upbit-pull (Mac only, see UPBIT_FILE)
"""
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HL = "https://api.hyperliquid.xyz/info"
TH = timezone(timedelta(hours=7))
HERE = Path(__file__).parent
H = 3600_000
ACCOUNTS = {   # name: (label, kind, params)
    "c_crashbounce_24h_500": ("Fable: ช้อน alt วันตลาดพัง (เหรียญ -15% และ BTC -5% ใน 24 ชม.) ถือ 24 ชม.", "crash", dict(hold_h=24, slots=5, cost=0.0025)),
    "c_crashbounce_72h_500": ("Fable: ช้อน alt วันตลาดพัง ถือ 72 ชม.", "crash", dict(hold_h=72, slots=5, cost=0.0025)),
    "n_crashshort_500": ("Fable: 21:00 short เหรียญที่ร่วง 10%+ ใน 6 ชม. ปิด 09:00 (กะดึก)", "night", dict(slots=5, cost=0.0025)),
    "n_low30short_500": ("Fable: 21:00 short เหรียญปิดต่ำสุด 30 วันและร่วง 5%+ ใน 12 ชม. ปิด 09:00 (วัดผล)", "night", dict(slots=5, cost=0.0025, signal="low30")),
    "l_newlist_short_500": ("Fable: short เหรียญเพิ่งเข้า Hyperliquid ถือ 30 วัน stop +50%", "newlist", dict(slots=10, cost=0.003)),
    "u_upbit_buy_500": ("ข่าวใหญ่: ซื้อเมื่อ Upbit ประกาศลิสต์ stop -8% trail 15% ถือไม่เกิน 16 ชม.", "news", dict(src="upbit", side=1, slots=5, cost=0.003)),
    "u_upbit_fade_500": ("ข่าวใหญ่: short เมื่อ Upbit ประกาศลิสต์ (ขายข่าว) ปิด 16 ชม. stop +25%", "news", dict(src="upbit", side=-1, slots=5, cost=0.003)),
    "b_bnlist_buy_500": ("ข่าวใหญ่: ซื้อเมื่อ Binance ประกาศ Will List stop -8% trail 15% ถือไม่เกิน 16 ชม.", "news", dict(src="binance", side=1, slots=5, cost=0.003)),
}
UPBIT = "https://api-manager.upbit.com/api/v1/announcements?os=web&page=1&per_page=20&category=trade"
UPBIT_FILE = HERE / "data" / "upbit_notices.json"   # Upbit answers 403 to GitHub's US runners: the Mac fetches it (upbit-pull)
BINANCE = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&catalogId=48&pageNo=1&pageSize=20"


def post(body):
    req = urllib.request.Request(HL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def market():
    """{coin: (mark, hourly funding, 24h notional volume)} for listed perps, and the full name list."""
    meta, ctx = post({"type": "metaAndAssetCtxs"})
    live = {u["name"]: (float(c["markPx"]), float(c["funding"]), float(c["dayNtlVlm"]))
            for u, c in zip(meta["universe"], ctx) if not u.get("isDelisted") and c.get("markPx")}
    return live


def closes(coin, now):
    """Closed 1h closes for the last 30 hours, oldest first."""
    rows = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1h", "startTime": now - 31 * H, "endTime": now}})
    return [float(x["c"]) for x in rows if x["T"] < now]


def low30(coin, now):
    """(12h return, last close, lowest low of the 30 days before the last closed hour) from closed 1h candles."""
    rows = [x for x in post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1h", "startTime": now - 31 * 24 * H, "endTime": now}})
            if x["T"] < now]
    if len(rows) < 30 * 24 + 1:
        return None                         # listed under 30 days: no 30-day low yet
    c = [float(x["c"]) for x in rows]
    return c[-1] / c[-13] - 1, c[-1], min(float(x["l"]) for x in rows[-721:-1])


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
        return json.load(r)


def notices(src, data):
    """[(id, ms, [tickers], title)] new-listing notices from one page of the Upbit or Binance announcement API."""
    out = []
    if src == "upbit":
        for n in data["data"]["notices"]:
            t = n["title"]
            if "신규 거래지원" in t and "안내" in t:
                ms = int(datetime.fromisoformat(n["first_listed_at"]).timestamp() * 1000)
                out.append((f"u{n['id']}", ms, re.findall(r"\(([A-Z0-9]{2,12})\)", t.split("신규 거래지원")[0]), t[:90]))
    else:
        for a in data["data"]["catalogs"][0]["articles"]:
            if m := re.match(r"Binance Will List .*?\(([A-Z0-9]{2,12})\)", a["title"]):
                out.append((f"b{a['id']}", a["releaseDate"], [m[1]], a["title"][:90]))
    return out


def ret(c, hours):
    return c[-1] / c[-1 - hours] - 1 if len(c) > hours else None


def path(name):
    return HERE / f"state_perp_{name}.json"


def value(p, px):
    return p["usd"] * (1 + p["side"] * (px / p["entry"] - 1))


def equity(s, mk):
    return s["cash"] + sum(value(p, mk.get(k, (p["last"],))[0]) for k, p in s["pos"].items())


def log(s, now, **kw):
    s["log"].append(dict(t=datetime.fromtimestamp(now / 1000, TH).isoformat(timespec="minutes"), **kw))


def open_pos(s, now, coin, side, px, cost, slots, mk, why):
    spend = min(s["cash"], equity(s, mk) / slots)
    if spend < 0.05:
        return
    s["cash"] -= spend
    s["pos"][coin] = dict(side=side, usd=spend * (1 - cost), entry=px, last=px, t=now)
    s["cool"][coin] = now
    log(s, now, kind="buy" if side > 0 else "short", coin=coin, price=px, usd=round(spend, 4), why=why)


def close_pos(s, now, coin, px, cost, why):
    p = s["pos"].pop(coin)
    got = value(p, px) * (1 - cost)
    s["cash"] += got
    log(s, now, kind="sell" if p["side"] > 0 else "cover", coin=coin, price=px, pnl=round(got - p["usd"] / (1 - cost), 4), why=why)


def step(name, s, mk, cl, now, new_hour, lo=None, news=None):
    """One round for one account. mk: market(); cl: {coin: closed 1h closes} (only filled on a new hour);
    lo: {coin: low30()} for the 21:00 round of the 30-day-low account; news: {src: notices()} (None on an API error)."""
    kind, p = ACCOUNTS[name][1], ACCOUNTS[name][2]
    for k, q in s["pos"].items():
        if k in mk:
            q["last"] = mk[k][0]
            if new_hour:
                q["usd"] *= 1 - q["side"] * mk[k][1]     # hourly funding: longs pay a positive rate, shorts receive it
    top = sorted((c for c in mk if c in cl), key=lambda c: -mk[c][2])[:30]
    bkk = datetime.fromtimestamp(now / 1000, TH)
    if kind == "crash":
        for k in [k for k, q in s["pos"].items() if now - q["t"] >= p["hold_h"] * H and k in mk]:
            close_pos(s, now, k, mk[k][0], p["cost"], f"ครบ {p['hold_h']} ชม.")
        btc = ret(cl.get("BTC", []), 24)
        if new_hour and btc is not None and btc <= -0.05:
            hits = sorted((r, c) for c in top if c != "BTC" and (r := ret(cl[c], 24)) is not None and r <= -0.15)
            for r, c in hits:
                if len(s["pos"]) < p["slots"] and c not in s["pos"] and now - s["cool"].get(c, 0) >= 72 * H:
                    open_pos(s, now, c, 1, mk[c][0], p["cost"], p["slots"], mk, f"24 ชม. {r:+.1%} BTC {btc:+.1%}")
    elif kind == "night":
        if s["pos"] and 9 <= bkk.hour < 21:
            for k in list(s["pos"]):
                close_pos(s, now, k, mk.get(k, (s["pos"][k]["last"],))[0], p["cost"], "ปิด 09:00")
        if s.get("night_start") and not s["pos"] and 9 <= bkk.hour < 21:
            s["nights"].append(dict(night=s["night"], ret=round(s["cash"] / s["night_start"] - 1, 5)))
            s.update(night=None, night_start=None)
        if new_hour and bkk.hour == 21 and not s.get("night_start"):
            s.update(night=bkk.date().isoformat(), night_start=equity(s, mk))
            if p.get("signal") == "low30":
                hits = sorted((v[0], c) for c, v in (lo or {}).items() if v and v[0] <= -0.05 and v[1] <= v[2] and c in mk)[:p["slots"]]
                for i, (r, c) in enumerate(hits):   # whole account split equally over tonight's signals
                    open_pos(s, now, c, -1, mk[c][0], p["cost"], len(hits) - i, mk, f"ต่ำสุด 30 วัน 12 ชม. {r:+.1%}")
            else:
                hits = sorted((r, c) for c in top if (r := ret(cl[c], 6)) is not None and r <= -0.10)
                for r, c in hits[:p["slots"]]:
                    open_pos(s, now, c, -1, mk[c][0], p["cost"], p["slots"], mk, f"6 ชม. {r:+.1%}")
    elif kind == "news":
        for k, q in list(s["pos"].items()):
            if k not in mk:
                continue
            px, age = mk[k][0], now - q["t"]
            q["hi"] = max(q.get("hi", q["entry"]), px)
            if p["side"] > 0:
                why = ("stop -8%" if px <= q["entry"] * 0.92 else "trail 15%" if q["hi"] >= q["entry"] * 1.15 and px <= q["hi"] * 0.85
                       else "ครบ 16 ชม." if age >= 16 * H else None)
            else:
                why = "stop +25%" if px >= q["entry"] * 1.25 else "ครบ 16 ชม." if age >= 16 * H else None
            if why:
                close_pos(s, now, k, px, p["cost"], why)
        if news is None or news.get(p["src"]) is None:
            return                                # announcement API failed this run: exits only, never guess
        first = "seen" not in s
        seen = s.setdefault("seen", [])
        for nid, ms, tickers, title in news[p["src"]]:
            if nid in seen:
                continue
            seen.append(nid)
            if first:
                continue                          # notices from before the account started are old news
            if now - ms > 30 * 60_000:
                log(s, now, kind="late", why=f"ประกาศเก่า {(now - ms) // 60_000} นาที", title=title)
                continue
            for t in tickers:
                c = t if t in mk else "k" + t if "k" + t in mk else None
                if c is None:
                    log(s, now, kind="skip", coin=t, why="ไม่มี perp บน Hyperliquid", title=title)
                elif c not in s["pos"] and len(s["pos"]) < p["slots"]:
                    open_pos(s, now, c, p["side"], mk[c][0], p["cost"], p["slots"], mk, title)
    else:   # newlist
        if not s.get("known"):
            s["known"] = sorted(mk)               # first run: everything already listed is old, no back-filling
        today = datetime.fromtimestamp(now / 1000, timezone.utc).date().isoformat()
        for c in mk:
            if c not in s["known"]:
                s["known"].append(c)
                s["pending"][c] = today
                log(s, now, kind="listed", coin=c)
        for c, d in list(s["pending"].items()):
            if d < today and c in mk:
                s["pending"].pop(c)
                if len(s["pos"]) < p["slots"]:
                    open_pos(s, now, c, -1, mk[c][0], p["cost"], p["slots"], mk, f"เข้า Hyperliquid {d}")
        for k, q in list(s["pos"].items()):
            if k in mk and (mk[k][0] >= q["entry"] * 1.5 or now - q["t"] >= 30 * 24 * H):
                close_pos(s, now, k, mk[k][0], p["cost"], "stop +50%" if mk[k][0] >= q["entry"] * 1.5 else "ครบ 30 วัน")


def cmd_init(thb):
    with urllib.request.urlopen("https://api.binance.th/api/v1/ticker/price?symbol=USDTTHB", timeout=20) as r:
        usd = float(thb) / float(json.load(r)["price"])
    for name, (label, kind, _) in ACCOUNTS.items():
        if not path(name).exists():
            path(name).write_text(json.dumps(dict(label=label, start_usd=usd, start_thb=float(thb), cash=usd, pos={}, cool={},
                                                  log=[], nights=[], pending={}, known=[], hour=0), ensure_ascii=False, indent=1))
            print(f"init {name}")


def cmd_run():
    states = {n: json.loads(path(n).read_text()) for n in ACCOUNTS if path(n).exists()}
    if not states:
        return
    now = int(time.time() * 1000)
    hour = now // H
    try:
        mk = market()
        new_hour = any(s["hour"] != hour for s in states.values())
        cl = {}
        if new_hour:
            for c in sorted(mk, key=lambda c: -mk[c][2])[:31] + ["BTC"]:
                if c not in cl:
                    cl[c] = closes(c, now)
                    time.sleep(0.2)
        lo = {}
        if new_hour and datetime.fromtimestamp(now / 1000, TH).hour == 21 and "n_low30short_500" in states:
            for c in [c for c in mk if mk[c][2] >= 10e6]:   # shortcut: today's 24h volume stands in for the 30-day average
                lo[c] = low30(c, now)
                time.sleep(0.3)
    except Exception as e:                      # an API error is a missed round, never a guessed price
        return print(f"crash run error: {e!r}"[:200])
    news = {}
    for src, url in (("upbit", UPBIT), ("binance", BINANCE)):
        if any(ACCOUNTS[n][1] == "news" and ACCOUNTS[n][2]["src"] == src for n in states):
            try:
                news[src] = notices(src, get(url))
            except Exception as e:              # missed notices this run; the next run still sees them while under 30 min old
                news[src] = notices(src, json.loads(UPBIT_FILE.read_text())) if src == "upbit" and UPBIT_FILE.exists() else None
                print(f"crash news {src} error: {e!r}, using the Mac copy: {news[src] is not None}"[:200])
    for name, s in states.items():
        try:
            step(name, s, mk, cl, now, s["hour"] != hour, lo, news)
            s["hour"] = hour
        except Exception as e:
            print(f"crash {name} error: {e!r}"[:200])
            continue
        path(name).write_text(json.dumps(s, ensure_ascii=False, indent=1))


def cmd_upbit_pull():
    """Mac side: save the Upbit notice page for the cloud; prints "changed" only when the listing notices differ (then push)."""
    new = get(UPBIT)
    old = json.loads(UPBIT_FILE.read_text()) if UPBIT_FILE.exists() else None
    if old is None or [x[0] for x in notices("upbit", old)] != [x[0] for x in notices("upbit", new)]:
        UPBIT_FILE.write_text(json.dumps(new, ensure_ascii=False))
        print("changed")


def cmd_report():
    for name in ACCOUNTS:
        if path(name).exists():
            s = json.loads(path(name).read_text())
            eq = s["cash"] + sum(value(p, p["last"]) for p in s["pos"].values())
            n = sum(x["kind"] in ("sell", "cover") for x in s["log"])
            nights = s["nights"]
            extra = f" คืน {len(nights)} บวก {sum(x['ret'] > 0 for x in nights)}" if ACCOUNTS[name][1] == "night" else ""
            print(f"{eq / s['start_usd'] - 1:+7.2%}  {name:22s} ไม้ปิด {n:3d} เปิดอยู่ {len(s['pos'])}{extra}  {s['label']}")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmds = {"init": lambda: cmd_init(a[1]), "run": cmd_run, "report": cmd_report, "upbit-pull": cmd_upbit_pull}
    if not a or a[0] not in cmds:
        sys.exit(__doc__)
    cmds[a[0]]()
