#!/usr/bin/env python3
"""Independent check of Grok Bot LTRADE lines against GeckoTerminal 1-minute candles (stdlib only, read-only, no keys).

  python3 grok_check.py chat.txt [--date 2026-11-19] [--tz 7] [--win 5] [--tol 3]
  pbpaste | python3 grok_check.py -

Input: raw chat text holding LEDGER / LTRADE lines. Trade time = "t=HH:MM" inside the LTRADE line if present, else the
last "LEDGER S<n> HH:MM" seen before it, else the whole clock hour of the strategy (S1=16h .. S7=22h, weak check).
For each trade: mint -> deepest pool (DexScreener) -> candles (GeckoTerminal) -> is the reported price inside the
low..high of the +-win minute window, and how far from the candle close at that minute. Also recomputes the 1h change
and pool liquidity so the entry rule itself can be checked. Verdict: OK / OFF (outside range by > tol %) / NO_CANDLES.
"""
import json, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "Mozilla/5.0", "accept": "application/json"}
LINE = re.compile(r"(LEDGER) S(\d) (\d\d):(\d\d)|(LTRADE) S(\d) (BUY|SELL) (\S+) (\S+) price=\$?([\d.,eE+-]+)([^\n]*?)(?=LTRADE|LEDGER|RESULT|NO DATA|\n|$)")
_last = [0.0]


def get(url, gap=2.2):
    time.sleep(max(0, _last[0] + gap - time.time()))      # GeckoTerminal free tier is about 30 calls a minute
    for i in range(3):
        try:
            _last[0] = time.time()
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20))
        except Exception as e:
            err = e
            time.sleep(5 * (i + 1))
    print(f"  fetch failed {url[:90]}: {err}", file=sys.stderr)


def parse(text, day, tz):
    out, led = [], {}
    for m in LINE.finditer(text):
        if m[1]:
            led[int(m[2])] = (int(m[3]), int(m[4]))
            continue
        s, tm = int(m[6]), re.search(r"\bt=(\d\d):(\d\d)", m[11])
        hm = (int(tm[1]), int(tm[2])) if tm else led.get(s)
        exact = hm is not None
        h, mi = hm or (15 + s, 30)
        ts = int((day.replace(hour=h, minute=mi) - timedelta(hours=tz)).replace(tzinfo=timezone.utc).timestamp())
        out.append(dict(s=s, side=m[7], sym=m[8], mint=m[9], px=float(m[10].replace(",", "")), ts=ts, exact=exact, hm=f"{h:02d}:{mi:02d}"))
    return out


_pool, _candles = {}, {}


def pool(mint):
    if mint not in _pool:
        d = get(f"https://api.dexscreener.com/tokens/v1/solana/{mint}", 0.3) or []
        d = [p for p in d if p.get("baseToken", {}).get("address") == mint]
        p = max(d, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0, default=None)
        _pool[mint] = (p["pairAddress"], (p.get("liquidity") or {}).get("usd") or 0, p["baseToken"]["symbol"]) if p else None
    return _pool[mint]


def candles(addr, mint, ts):
    """{minute_ts: (o,h,l,c)} for the 3 hours ending 1 hour after ts (one call, cached per pool and hour)."""
    key = (addr, ts // 3600)
    if key not in _candles:
        end = (ts // 3600 + 2) * 3600
        d = get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{addr}/ohlcv/minute?aggregate=1&limit=180&before_timestamp={end}&token={mint}&currency=usd")
        if d is None:
            return {}                   # fetch failed (rate limit): not cached, so the next trade on this pool retries
        _candles[key] = {int(c[0]): c[1:5] for c in d.get("data", {}).get("attributes", {}).get("ohlcv_list", [])}
    return _candles[key]


def check(t, win, tol):
    p = pool(t["mint"])
    if not p:
        return "NO_POOL", "mint not on DexScreener (fabricated mint?)"
    cs = candles(p[0], t["mint"], t["ts"])
    span = win * 60 if t["exact"] else 1800
    w = {k: v for k, v in cs.items() if abs(k - t["ts"]) <= span}
    if not w:
        return "NO_CANDLES", f"pool {p[0][:6]} liq ${p[1]:,.0f}: no trades within +-{span // 60} min (illiquid or wrong time)"
    lo, hi = min(v[2] for v in w.values()), max(v[1] for v in w.values())
    near = cs[min(w, key=lambda k: abs(k - t["ts"]))][3]
    out = 0 if lo <= t["px"] <= hi else (t["px"] / hi - 1 if t["px"] > hi else t["px"] / lo - 1) * 100
    ago = [v[3] for k, v in cs.items() if 0 <= t["ts"] - 3600 - k <= 600]
    h1 = f"{(near / ago[0] - 1) * 100:+.0f}%" if ago else "?"
    sym = "" if p[2].upper() == t["sym"].upper().lstrip("$") else f" SYMBOL MISMATCH (pool says {p[2]})"
    return ("OK" if abs(out) <= tol else "OFF"), (f"range {lo:.4g}..{hi:.4g} outside by {out:+.1f}% | vs close {(t['px'] / near - 1) * 100:+.1f}% | "
                                                   f"1h change then {h1} | liq now ${p[1]:,.0f}{'' if t['exact'] else ' | no timestamp, hour-wide check'}{sym}")


def main(a):
    opt = lambda k, d: a[a.index(k) + 1] if k in a else d
    text = sys.stdin.read() if a[0] == "-" else open(a[0]).read()
    day = datetime.strptime(opt("--date", datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d")
    trades = parse(text, day, float(opt("--tz", 7)))
    bad = 0
    for t in trades:
        v, why = check(t, int(opt("--win", 5)), float(opt("--tol", 3)))
        bad += v != "OK"
        print(f"{v:10} S{t['s']} {t['hm']} {t['side']:4} {t['sym'][:10]:10} px={t['px']:.6g} | {why}")
    print(f"\n{len(trades)} trades, {bad} not verified" + (" -> treat every RESULT of this run as unverified" if bad else ""))


if __name__ == "__main__":
    main(sys.argv[1:] or ["-"])
