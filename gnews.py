#!/usr/bin/env python3
"""Gemini news desk (Mac only: needs a logged-in `agy`). Paper money only, no wallet, no orders anywhere.

Every run: read new crypto headlines from RSS, ask Gemini 4 Hydrogen (fast) for a call on each, and paper-trade
the confident ones on big coins. state_gnews_twin.json opens a random coin and side at the same moments with the
same size and exits, as the control. Prices come from Binance; a failed price or a failed model call means no
trade (never a guessed value).
"""
import json, os, random, re, subprocess, sys, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

TZ = timezone(timedelta(hours=7))
FEEDS = ["https://www.coindesk.com/arc/outboundfeeds/rss", "https://cointelegraph.com/rss",
         "https://decrypt.co/feed", "https://www.theblock.co/rss.xml"]
# Public Telegram channels (read through the t.me/s web preview, no login): the fast headline feeds traders watch.
TELEGRAM = ["BWEnews", "WatcherGuru", "wublockchainenglish", "WalterBloomberg", "theblockbeats"]
COINS = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX", "LINK", "SUI"]
MODELS = ["gemini-4-hydrogen-low"]   # user: never Argon (22 Nov); a quota-out run just skips
THB, RATE = 500.0, 33.9                  # same 500 THB start as the other accounts
SIZE, TP, SL, MAX_H, MIN_CONF = 0.20, 0.04, 0.02, 12, 70
COST = 0.001                             # Binance spot fee per side
FRESH_MIN = 90                           # ignore headlines older than this: the move is already priced
ACCOUNTS = {"state_gnews.json": "ข่าว Gemini: Hydrogen อ่านข่าวคริปโตแล้วเลือกเหรียญใหญ่ ไม้ละ 20% TP +4% SL -2% ถือไม่เกิน 12 ชม.",
            "state_gnews_twin.json": "ตัวควบคุมข่าว Gemini: สุ่มเหรียญและฝั่ง ณ เวลาเดียวกัน ขนาดและกฎออกเท่ากัน"}
LOG, SEEN = "data/gnews_log.json", "data/gnews_seen.json"
now = datetime.now(TZ)


def load(path, default):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return default


def save(path, obj):
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=20).read()


def price(coin):
    return float(json.loads(get(f"https://api.binance.com/api/v3/ticker/price?symbol={coin}USDT"))["price"])


def telegram(ch):
    html = get(f"https://t.me/s/{ch}").decode("utf-8", "replace")
    for block in html.split('data-post="')[1:]:
        post = block.split('"', 1)[0]
        text = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', block, re.S)
        when = re.search(r'<time datetime="([^"]+)"', block)
        if text and when:
            plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text.group(1))).strip()
            yield f"https://t.me/{post}", plain, datetime.fromisoformat(when.group(1))


def headlines(seen):
    out = []
    for ch in TELEGRAM:
        try:
            for link, text, t in telegram(ch):
                if link not in seen and now - t <= timedelta(minutes=FRESH_MIN):
                    out.append({"link": link, "title": f"[{ch}] " + __import__("html").unescape(text)[:200],
                                "t": t.astimezone(TZ).isoformat(timespec="minutes"), "desc": ""})
        except Exception as e:
            print("telegram failed", ch, type(e).__name__)
    for url in FEEDS:
        try:
            root = ET.fromstring(get(url))
        except Exception as e:
            print("feed failed", url, type(e).__name__)
            continue
        for it in root.iter("item"):
            link, title = (it.findtext("link") or "").strip(), (it.findtext("title") or "").strip()
            try:
                t = parsedate_to_datetime(it.findtext("pubDate") or "")
            except (TypeError, ValueError):
                continue
            if link and link not in seen and now - t <= timedelta(minutes=FRESH_MIN):
                out.append({"link": link, "title": title, "t": t.astimezone(TZ).isoformat(timespec="minutes"),
                            "desc": re.sub(r"<[^>]+>", "", it.findtext("description") or "")[:300]})
    return sorted(out, key=lambda x: x["t"], reverse=True)[:25]   # newest first: the fast ones matter most


def ask(items):
    lines = "\n".join(f"{i}. [{x['t']}] {x['title']} | {x['desc']}" for i, x in enumerate(items))
    prompt = (
        "You are a skeptical crypto news desk. For each headline below decide whether it should move one of these "
        f"coins in the next few hours: {', '.join(COINS)}. Most news is noise or already priced: skip unless the "
        "headline is new, specific and material (listings, hacks, ETF/regulatory decisions, big flows, outages).\n"
        'Reply with ONLY a JSON array, one object per headline: {"i": <number>, "coin": "<coin or NONE>", '
        '"side": "long|short|skip", "conf": <0-100>, "why": "<max 15 words, Thai>"}\n\n' + lines)
    for model in MODELS:
        try:
            r = subprocess.run(["agy", "--model", model, "-p", prompt, "--print-timeout", "180s"],
                               capture_output=True, text=True, timeout=240, stdin=subprocess.DEVNULL)
            m = re.search(r"\[.*\]", r.stdout, re.S)
            if m:
                return model, json.loads(m.group(0))
            print(model, "no JSON:", (r.stdout + r.stderr).strip()[-200:])
        except (subprocess.TimeoutExpired, ValueError) as e:
            print(model, "failed:", type(e).__name__)
    return None, None


def account(path):
    return load(path, {"label": ACCOUNTS[path], "start_thb": THB, "start_usd": THB / RATE, "cash": THB / RATE, "pos": {}, "log": []})


def open_pos(s, coin, side, px, why):
    if coin in s["pos"]:
        return False
    usd = s["start_usd"] * SIZE
    if s["cash"] < usd * (1 + COST):
        return False
    qty = usd / px * (1 if side == "long" else -1)
    s["cash"] += -usd if side == "long" else usd      # a short books the sale proceeds: value = cash + qty*last stays right
    s["cash"] -= usd * COST
    s["pos"][coin] = {"side": side, "qty": qty, "entry": px, "last": px, "usd": usd, "t": now.isoformat(), "why": why}
    s["log"].append({"kind": "buy", "t": now.isoformat(), "coin": coin, "side": side, "px": px, "usd": usd, "why": why})
    return True


def exits(s, prices):
    for coin, p in list(s["pos"].items()):
        px = prices.get(coin)
        if px is None:
            continue                                    # no price this run: hold, decide next run
        p["last"] = px
        ret = (px / p["entry"] - 1) * (1 if p["side"] == "long" else -1)
        age = (now - datetime.fromisoformat(p["t"])).total_seconds() / 3600
        why = "TP" if ret >= TP else "SL" if ret <= -SL else "หมดเวลา" if age >= MAX_H else None
        if not why:
            continue
        s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
        pnl = p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST
        s["log"].append({"kind": "sell", "t": now.isoformat(), "coin": coin, "side": p["side"], "px": px, "usd": p["usd"],
                         "pnl": pnl, "cost_side": COST, "why": why})
        del s["pos"][coin]


def main():
    accts = {f: account(f) for f in ACCOUNTS}
    held = {c for s in accts.values() for c in s["pos"]}
    prices = {}
    for c in held:
        try:
            prices[c] = price(c)
        except Exception as e:
            print("price failed", c, type(e).__name__)
    for s in accts.values():
        exits(s, prices)

    seen = load(SEEN, [])
    items = headlines(set(seen))
    log = load(LOG, [])
    if items:
        model, calls = ask(items)
        if calls is None:
            print("model failed: no trades this run")   # headlines stay unseen and get one more try while fresh
        else:
            for c in calls:
                if not isinstance(c, dict) or not isinstance(c.get("i"), int) or not 0 <= c["i"] < len(items):
                    continue
                x, coin, side = items[c["i"]], str(c.get("coin", "")).upper(), c.get("side")
                acted = ""
                if coin in COINS and side in ("long", "short") and (c.get("conf") or 0) >= MIN_CONF:
                    try:
                        if open_pos(accts["state_gnews.json"], coin, side, price(coin), x["title"][:120]):
                            acted = "เปิด"
                            rc, rs = random.choice(COINS), random.choice(["long", "short"])
                            open_pos(accts["state_gnews_twin.json"], rc, rs, price(rc), "สุ่ม คู่กับ " + coin)
                    except Exception as e:
                        acted = "ราคาไม่มา"
                        print("price failed", coin, type(e).__name__)
                log.append({"t": now.isoformat(timespec="minutes"), "news_t": x["t"], "title": x["title"], "link": x["link"],
                            "coin": coin, "side": side, "conf": c.get("conf"), "why": c.get("why", ""), "model": model, "acted": acted})
            seen += [x["link"] for x in items]
    for f, s in accts.items():
        save(f, s)
    save(SEEN, seen[-2000:])
    save(LOG, log[-300:])
    print(f"{now:%H:%M} headlines={len(items)} open={ {f: list(s['pos']) for f, s in accts.items()} }")


if __name__ == "__main__":
    main()
