#!/usr/bin/env python3
"""Forward test of the "AI Agent Lens" idea (Mac only: needs a logged-in agy; launchd every hour). Paper money only.

When a 4h bar of BTC, ETH or SOL closes with a long or short score of 80+ (5 factors, same as
Projects/PaperTrade/backtests/llm_lens_replay.py), three accounts act at the next bar's open:
  state_lens_rule.json  takes every signal in the score's direction
  state_lens_neon.json  takes it only if Gemini 4 Neon (high), shown a blind panel with no date, coin or price level, says so
  state_lens_rand.json  takes every signal with a random side (control)
Stop 1.5 ATR, target 1.5R, closed after 48 h, 0.1% per side. Prices from Binance; a failed fetch means no action.
"""
import json, os, random, re, subprocess, sys, urllib.request
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=7))
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
THB, RATE, SIZE, COST, MIN_SCORE, MAX_H = 500.0, 33.9, 0.20, 0.001, 80, 48
MODEL = "gemini-4-neon-high"
ACCOUNTS = {"state_lens_rule.json": "Lens 4 ชม. กฎอย่างเดียว: คะแนน 80+ เข้าทุกสัญญาณ BTC ETH SOL stop 1.5 ATR เป้า 1.5R ถือไม่เกิน 48 ชม.",
            "state_lens_neon.json": "Lens 4 ชม. + Neon high ตัดสินแบบปิดวันที่และชื่อเหรียญ กฎออกเดียวกัน",
            "state_lens_rand.json": "Lens 4 ชม. ตัวควบคุม: สัญญาณเดียวกันแต่สุ่มฝั่ง"}
SEEN, LOG = "data/lens_seen.json", "data/lens_log.jsonl"
now = datetime.now(TZ)


def get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())


def klines(sym, interval, limit):
    return [dict(t=k[0], o=float(k[1]), h=float(k[2]), l=float(k[3]), c=float(k[4]), v=float(k[5]), closed=k[6] < now.timestamp() * 1000)
            for k in get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}")]


def ema(x, n):
    k, out = 2 / (n + 1), []
    for i, v in enumerate(x):
        out.append(v if i == 0 else v * k + out[-1] * (1 - k))
    return out


def rsi(c, n=14):
    g = l = 0.0
    out = [None] * len(c)
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        g, l = ((g * (n - 1) + max(d, 0)) / n, (l * (n - 1) + max(-d, 0)) / n) if i > n else (g + max(d, 0) / n, l + max(-d, 0) / n)
        if i >= n:
            out[i] = 100 - 100 / (1 + g / l) if l else 100
    return out


def score(b):
    """Scores of the last bar in b (all closed): same five factors as the replay."""
    c, h, l, v = [x["c"] for x in b], [x["h"] for x in b], [x["l"] for x in b], [x["v"] for x in b]
    e20, e50, r, i = ema(c, 20), ema(c, 50), rsi(c), len(b) - 1
    tr = [max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1])) for j in range(1, len(c))]
    atr = sum(tr[-14:]) / 14
    f = {"trend": (c[i] > e50[i]) - (c[i] < e50[i]), "ema_cross": (e20[i] > e50[i]) - (e20[i] < e50[i]),
         "rsi": (r[i] > 55) - (r[i] < 45), "breakout": (c[i] > max(h[i - 20:i])) - (c[i] < min(l[i - 20:i])),
         "volume": 1 if v[i] > 1.5 * sum(v[i - 20:i]) / 20 else 0}
    up = sum(20 for k, x in f.items() if x > 0 or (k == "volume" and x and c[i] > b[i]["o"]))
    dn = sum(20 for k, x in f.items() if x < 0 or (k == "volume" and x and c[i] < b[i]["o"]))
    return dict(long=up, short=dn, factors=f, atr=atr, close=c[i], rsi=round(r[i], 1),
                path=[round((x / c[i] - 1) * 100, 2) for x in c[-12:]])


def ask_neon(cands):
    lines = "\n".join(f"{k}. a large crypto asset, 4h bars: last 12 closes as % from the latest close {s['path']}, RSI {s['rsi']}, "
                      f"ATR {s['atr'] / s['close'] * 100:.2f}% of price, long score {s['long']}/100, short score {s['short']}/100, "
                      f"factors {s['factors']}" for k, s in enumerate(cands))
    prompt = ("You are a disciplined crypto swing trader reading an indicator panel. For each closed 4h bar decide TAKE_LONG, "
              "TAKE_SHORT or WAIT. A taken trade enters at the next bar's open with a stop 1.5 ATR away and a target 1.5R away, "
              "held at most 48 hours, costs 0.1% per side. Take only setups you expect to be profitable; WAIT is fine.\n"
              'Reply with ONLY a JSON array: [{"k": <number>, "decision": "TAKE_LONG|TAKE_SHORT|WAIT"}]\n\n' + lines)
    r = subprocess.run(["agy", "--model", MODEL, "-p", prompt, "--print-timeout", "240s"], capture_output=True, text=True,
                       timeout=300, stdin=subprocess.DEVNULL)
    m = re.search(r"\[.*\]", r.stdout, re.S)
    return json.loads(m.group(0)) if m else None


def load(path, default):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return default


def save(path, obj):
    json.dump(obj, open(path + ".tmp", "w"), ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


def open_pos(s, sym, side, px, atr, why):
    if sym in s["pos"]:
        return
    usd = s["start_usd"] * SIZE
    if s["cash"] < usd * (1 + COST):
        return
    d = 1 if side == "long" else -1
    s["cash"] += -usd if d > 0 else usd                 # a short books the proceeds: value = cash + qty*last
    s["cash"] -= usd * COST
    s["pos"][sym] = dict(side=side, qty=d * usd / px, entry=px, last=px, usd=usd, stop=px - d * 1.5 * atr, tgt=px + d * 2.25 * atr,
                         t=now.isoformat(timespec="seconds"), why=why)
    s["log"].append(dict(kind="buy", t=now.isoformat(timespec="seconds"), coin=sym[:-4], side=side, px=px, usd=usd, why=why))


def close_pos(s, sym, px, why):
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * (1 if p["side"] == "long" else -1)
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=now.isoformat(timespec="seconds"), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"],
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def exits(s, hourly):
    """Walk the 1h bars since entry: the stop counts first when one bar touches both."""
    for sym, p in list(s["pos"].items()):
        bars = [x for x in hourly.get(sym, []) if x["t"] >= datetime.fromisoformat(p["t"]).timestamp() * 1000 - 3_600_000 and x["closed"]]
        long = p["side"] == "long"
        for x in bars:
            if (x["l"] <= p["stop"]) if long else (x["h"] >= p["stop"]):
                close_pos(s, sym, p["stop"], "stop")
                break
            if (x["h"] >= p["tgt"]) if long else (x["l"] <= p["tgt"]):
                close_pos(s, sym, p["tgt"], "ถึงเป้า 1.5R")
                break
        else:
            if hourly.get(sym):
                p["last"] = hourly[sym][-1]["c"]
                if now - datetime.fromisoformat(p["t"]) >= timedelta(hours=MAX_H):
                    close_pos(s, sym, p["last"], "ครบ 48 ชม.")


def main():
    accts = {f: load(f, dict(label=lbl, start_thb=THB, start_usd=THB / RATE, cash=THB / RATE, pos={}, log=[])) for f, lbl in ACCOUNTS.items()}
    hourly = {}
    for sym in SYMS:
        try:
            hourly[sym] = klines(sym, "1h", 72)
        except Exception as e:
            print("1h fetch failed", sym, type(e).__name__)
    for s in accts.values():
        exits(s, hourly)

    seen, cands = load(SEEN, {}), []
    for sym in SYMS:
        try:
            k = klines(sym, "4h", 120)
        except Exception as e:
            print("4h fetch failed", sym, type(e).__name__)
            continue
        closed = [x for x in k if x["closed"]]
        if not closed or seen.get(sym) == closed[-1]["t"]:
            continue
        seen[sym] = closed[-1]["t"]
        sc = score(closed)
        if max(sc["long"], sc["short"]) >= MIN_SCORE:
            cands.append(dict(sc, sym=sym, entry=k[-1]["o"] if not k[-1]["closed"] else closed[-1]["c"]))
    if cands:
        calls = ask_neon(cands)
        for k, c in enumerate(cands):
            rule_side = "long" if c["long"] >= c["short"] else "short"
            why = f"คะแนน long {c['long']} short {c['short']}"
            open_pos(accts["state_lens_rule.json"], c["sym"], rule_side, c["entry"], c["atr"], why)
            open_pos(accts["state_lens_rand.json"], c["sym"], random.choice(["long", "short"]), c["entry"], c["atr"], "สุ่มฝั่ง " + why)
            d = next((x.get("decision", "") for x in calls or [] if isinstance(x, dict) and x.get("k") == k), None)
            if d and d.startswith("TAKE"):
                open_pos(accts["state_lens_neon.json"], c["sym"], "long" if "LONG" in d else "short", c["entry"], c["atr"], f"Neon {d} " + why)
            with open(LOG, "a") as f:
                f.write(json.dumps(dict(t=now.isoformat(timespec="minutes"), sym=c["sym"], long=c["long"], short=c["short"],
                                        factors=c["factors"], entry=c["entry"], atr=c["atr"], neon=d if calls is not None else "failed"),
                                   ensure_ascii=False) + "\n")
    for f, s in accts.items():
        save(f, s)
    save(SEEN, seen)
    print(f"{now:%H:%M} signals={len(cands)} open={ {f[11:-5]: list(s['pos']) for f, s in accts.items()} }")


if __name__ == "__main__":
    main()
