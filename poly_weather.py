#!/usr/bin/env python3
"""Polymarket daily temperature buckets vs a free Open-Meteo forecast (idea from SkyEdge, a weather-market terminal: a sales
post with no rules, opened 23 Nov 2026 to try). Fake money only: public read-only APIs, no login, no keys, no wallet, no orders.

  state_poly_weather.json       every SCAN_H hours, for each "Highest/Lowest temperature in <city> on <date>?" event whose
                                rules text parses (station ICAO, date, unit C or F, METAR source, whole-degree rounding) and whose
                                observation date has not started at the station: model probability per bucket from a normal
                                N(mean, sigma). mean = Open-Meteo forecast daily max/min (best_match, hourly models) at the
                                station's lat/lon. sigma = sqrt(sd^2 + SIGMA_C^2): sd = spread of the Open-Meteo ensembles
                                (ECMWF IFS 0.25 deg 51 members + NOAA GEFS 0.25 deg 31 members pooled), SIGMA_C 1.0 C for
                                station vs grid cell. (Ensembles are not the mean: they are 3-hourly, so their daily max
                                misses the peak and runs low.)
                                Buys the YES of the bucket with the largest (model probability - cost per share incl. taker fee
                                and SLIP) if that edge is at least EDGE_MIN, 5% of the start per buy, one buy per event, held
                                to resolution. Marked to the best bid.
  state_poly_weather_twin.json  control: at the same moment, the same size on a random bucket of the same event.
  data/poly_weather_log.jsonl   every event evaluated per scan (best bucket, model p, cost, edge), last LOG_KEEP lines.

Dead / pass (AGENT_RULES, written before any result): dead at 20 closed buys if the average per buy is not above the twin's;
pass at 50 closed buys, positive after costs, above the twin, and still positive with the best buy removed.
Why it may fail: the market sees the same free models plus the METAR so far and better station-level forecasts; a big model
edge on a 2-cent bucket is more likely our grid-cell bias than the market's mistake.

Events whose rules do not parse (e.g. Hong Kong Observatory, no ICAO station) are skipped. Nothing is guessed: a missing
station, forecast day, member set or book means no action for that event.

Endpoints (each checked 23 Nov 2026, all public, no key):
  Gamma GET /events?tag_slug=daily-temperature&closed=false&end_date_min&end_date_max&limit=50 (limit > 50 needs gzip)
                                       docs.polymarket.com/api-spec/gamma-openapi.yaml
  CLOB POST /books                     docs.polymarket.com/api-spec/clob-openapi.yaml
  Fees fee = C x rate x p(1-p) (weather 0.01)  docs.polymarket.com/trading/fees.md
  Data API GET /v2/resolutions         docs.polymarket.com/migrate/data-api-v1-to-v2.md
  AWC GET aviationweather.gov/api/data/stationinfo?ids=&format=json (station lat/lon)  aviationweather.gov/data/api/
  Open-Meteo GET api.open-meteo.com/v1/forecast?latitude=a,b&longitude=a,b&daily=temperature_2m_max,temperature_2m_min
      &timezone=auto  open-meteo.com/en/docs
  Open-Meteo GET ensemble-api.open-meteo.com/v1/ensemble?...same...&models=ecmwf_ifs025,gfs025  open-meteo.com/en/docs/ensemble-api
      Free non-commercial < 10,000 calls per day, open-meteo.com/en/terms (a scan is ~4 requests for ~55 stations; SCAN_H 3)

  python3 poly_weather.py run      # cloud.sh, every 5 min: settle + mark every run, scan for buys every SCAN_H hours
  python3 poly_weather.py status
"""
import json, math, random, re, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polymarket as P

HERE = Path(__file__).parent
MAIN, TWIN = str(HERE / "state_poly_weather.json"), str(HERE / "state_poly_weather_twin.json")
LABELS = {MAIN: "Polymarket อุณหภูมิรายวัน: ซื้อช่องที่พยากรณ์ Open-Meteo ให้ความน่าจะเป็นเกินราคา 8 จุดขึ้นไป ไม้ละ 5% ถือจนตัดสินผล",
          TWIN: "Polymarket อุณหภูมิรายวัน ตัวควบคุม: สุ่มช่องในตลาดเดียวกัน เวลาเดียวกัน ขนาดเดียวกัน"}
LOG = HERE / "data" / "poly_weather_log.jsonl"
STATIONS = HERE / "data" / "poly_weather_stations.json"
GAMMA, AWC = P.GAMMA, "https://aviationweather.gov/api/data"
OM, OME = "https://api.open-meteo.com/v1/forecast", "https://ensemble-api.open-meteo.com/v1/ensemble"
MODELS = "ecmwf_ifs025,gfs025"
SIGMA_C = 1.0        # deg C, added to the ensemble spread in quadrature (station vs grid cell, model error)
EDGE_MIN = 0.08      # model p - cost per share (ask walk + taker fee + slip)
MIN_MEMBERS = 10     # per model, else that model is dropped
MAX_LEAD_DAYS = 3    # observation date at most this many days after the station's local today
SCAN_H = 3
LOG_KEEP = 2000
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


# ---- parsing (rules text and bucket titles; anything unexpected -> None) ----
def parse_bucket(title, unit):
    """'7°C' -> (7, 7); '40-41°F' -> (40, 41); '-6°C or below' -> (-inf, -6); '58°F or higher' -> (58, inf)."""
    t = (title or "").strip().replace("−", "-")
    u = re.escape("°" + unit)
    for pat, f in ((rf"^(-?\d+){u} or (?:below|lower)$", lambda a: (-math.inf, a)), (rf"^(-?\d+){u} or (?:higher|above)$", lambda a: (a, math.inf)),
                   (rf"^(-?\d+){u}$", lambda a: (a, a))):
        m = re.match(pat, t)
        if m:
            return f(int(m.group(1)))
    m = re.match(rf"^(-?\d+)\s*-\s*(-?\d+){u}$", t)
    if m and int(m.group(1)) <= int(m.group(2)):
        return int(m.group(1)), int(m.group(2))
    return None


def parse_event(e):
    """-> (info, None) or (None, reason). info: kind max|min, icao, date YYYY-MM-DD, unit C|F, buckets [(lo, hi, market, yes_token)]."""
    d = (e.get("description") or "").replace("−", "-")
    m = re.search(r"contains the (highest|lowest) temperature (?:reported|recorded) at (.+?) \(([A-Z0-9]{4})\) on (\d{1,2}) ([A-Za-z]{3}) '(\d{2})\.", d)
    if not m:
        return None, "no station/date sentence"
    kind, site, icao, day, mon, yy = m.groups()
    if mon.lower() not in MONTHS:
        return None, "month"
    date = f"20{yy}-{MONTHS[mon.lower()]:02d}-{int(day):02d}"
    u = re.search(r"states its range in whole degrees (Celsius|Fahrenheit)\.", d)
    if not u:
        return None, "no unit sentence"
    unit = u.group(1)[0]
    if "rounded to the nearest whole degree" not in d or (unit == "F" and "°F = °C × 9/5 + 32" not in d):
        return None, "rounding rule not as expected"
    srcs = set(re.findall(r"aviationweather\.gov/api/data/metar\?ids=([A-Z0-9]{4})", d))
    if srcs != {icao}:
        return None, f"METAR source {srcs} != {icao}"
    title = e.get("title") or ""
    tm = re.match(r"^(Highest|Lowest) temperature in .+ on ([A-Z][a-z]+) (\d{1,2})\?$", title)
    if not tm or tm.group(1).lower() != kind or MONTHS.get(tm.group(2)[:3].lower()) != MONTHS[mon.lower()] or int(tm.group(3)) != int(day):
        return None, "title does not match rules"
    buckets = []
    for mk in e.get("markets") or []:
        try:
            outs, toks = json.loads(mk["outcomes"]), json.loads(mk["clobTokenIds"])
        except (KeyError, ValueError, TypeError):
            return None, "market outcomes"
        b = parse_bucket(mk.get("groupItemTitle"), unit)
        if outs != ["Yes", "No"] or len(toks) != 2 or not b:
            return None, f"bucket {mk.get('groupItemTitle')!r}"
        if (mk.get("groupItemTitle") or "").replace("−", "-") not in (mk.get("question") or "").replace("−", "-"):
            return None, "bucket not in question"
        src = re.findall(r"metar\?ids=([A-Z0-9]{4})", mk.get("resolutionSource") or "")
        if src and src != [icao]:
            return None, "market source station differs"
        buckets.append((b[0], b[1], mk, toks[0]))
    buckets.sort(key=lambda x: x[0])
    if len(buckets) < 3 or buckets[0][0] != -math.inf or buckets[-1][1] != math.inf or \
            any(buckets[i][1] + 1 != buckets[i + 1][0] for i in range(len(buckets) - 1)):
        return None, "buckets are not a partition"
    return dict(kind="max" if kind == "highest" else "min", icao=icao, site=site, date=date, unit=unit, buckets=buckets), None


# ---- model probability ----
def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def to_c(x, unit):
    return x if unit == "C" or math.isinf(x) else (x - 32) * 5 / 9


def bucket_probs(mean, sigma, buckets, unit):
    """N(mean, sigma) in deg C; bucket [lo, hi] whole degrees in `unit`, a value rounds into it if in [lo-0.5, hi+0.5)."""
    out = []
    for lo, hi, *_ in buckets:
        a, b = to_c(lo - 0.5, unit), to_c(hi + 0.5, unit)
        out.append((1 if b == math.inf else phi((b - mean) / sigma)) - (0 if a == -math.inf else phi((a - mean) / sigma)))
    return out


def model(fc, ens, kind, date):
    """(mean C, sigma C, members) for one station day, or None. mean from the forecast API, spread from the ensembles."""
    dl = (fc or {}).get("daily") or {}
    if (fc.get("daily_units") or {}).get(f"temperature_2m_{kind}") != "°C" or date not in (dl.get("time") or []):
        return None
    mean = dl[f"temperature_2m_{kind}"][dl["time"].index(date)]
    ms = members(ens or {}, kind, date)
    if mean is None or not ms:
        return None
    pool = [v for m in ms for v in m]
    mu = sum(pool) / len(pool)
    sd = math.sqrt(sum((v - mu) ** 2 for v in pool) / len(pool))
    return float(mean), math.sqrt(sd ** 2 + SIGMA_C ** 2), len(pool)


def members(loc, kind, date):
    """Member values for one daily date from an Open-Meteo ensemble location: [[values per model]] (deg C) or None."""
    dl = loc.get("daily") or {}
    if date not in (dl.get("time") or []):
        return None
    i, units = dl["time"].index(date), loc.get("daily_units") or {}
    by = {}
    for k, v in dl.items():
        m = re.match(rf"^temperature_2m_{kind}(?:_member\d+)?(?:_(.+))?$", k)
        if m and units.get(k) == "°C" and isinstance(v, list) and v[i] is not None:
            by.setdefault(m.group(1) or "", []).append(float(v[i]))
    ms = [v for v in by.values() if len(v) >= MIN_MEMBERS]
    return ms or None


# ---- fetchers ----
def events(now):
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for off in range(0, 500, 50):
        rows = P.get(f"{GAMMA}/events", dict(tag_slug="daily-temperature", closed="false", limit=50, offset=off,
                                               end_date_min=iso(now), end_date_max=iso(now + (MAX_LEAD_DAYS + 1) * 86400)))
        out += rows
        if len(rows) < 50:
            break
    return out


def stations(icaos):
    """lat/lon per ICAO from AWC stationinfo, cached in data/ (stations do not move)."""
    try:
        cache = json.loads(STATIONS.read_text())
    except (OSError, ValueError):
        cache = {}
    miss = sorted(set(icaos) - set(cache))
    for i in range(0, len(miss), 40):
        for r in P.get(f"{AWC}/stationinfo", dict(ids=",".join(miss[i:i + 40]), format="json")):
            if r.get("icaoId") and r.get("lat") is not None and r.get("lon") is not None:
                cache[r["icaoId"]] = [float(r["lat"]), float(r["lon"]), r.get("site")]
    if miss:
        STATIONS.parent.mkdir(exist_ok=True)
        STATIONS.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True))
    return cache


def forecasts(coords):
    """{icao: (forecast location, ensemble location)} for [(icao, lat, lon)], 50 locations per request."""
    out = {}
    for i in range(0, len(coords), 50):
        ch = coords[i:i + 50]
        base = dict(latitude=",".join(f"{c[1]:.4f}" for c in ch), longitude=",".join(f"{c[2]:.4f}" for c in ch),
                    daily="temperature_2m_max,temperature_2m_min", timezone="auto", forecast_days=MAX_LEAD_DAYS + 2)
        f, e = P.get(OM, base), P.get(OME, dict(base, models=MODELS))
        f, e = (f if isinstance(f, list) else [f]), (e if isinstance(e, list) else [e])
        if len(f) != len(ch) or len(e) != len(ch):
            raise ValueError("open-meteo location count")
        out.update({c[0]: (x, y) for c, x, y in zip(ch, f, e)})
    return out


def books(tokens, n=100):
    out, tokens = {}, list(dict.fromkeys(tokens))
    for i in range(0, len(tokens), n):
        for b in P.post(f"{P.CLOB}/books", [dict(token_id=t) for t in tokens[i:i + n]]):
            out[b["asset_id"]] = b
    return out


# ---- accounting ----
def load(f):
    try:
        return json.load(open(f))
    except (OSError, ValueError):
        s = P.new_state(LABELS.get(f, "poly weather"))
        s.update(last_scan=0, done={})
        return s


def quote(book, m, usd):
    """(cost per share all-in, average fill price) for spending usd on this YES book, or None."""
    f = P.fill_buy(P.levels(book, "asks"), usd, P.fee_info(m))
    return (usd / f[0], f[1] / f[0]) if f else None


def lead_ok(loc, date, now):
    """Observation date has not started at the station (local midnight still ahead) and is within MAX_LEAD_DAYS."""
    off = loc.get("utc_offset_seconds")
    if off is None:
        return False
    start = datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp() - off
    return now < start <= now + MAX_LEAD_DAYS * 86400


def evaluate(info, loc, bk, usd, now):
    """loc = (forecast, ensemble) for the station. -> dict with probs, chosen bucket and edge, or a reason string."""
    fc, ens = loc
    if not lead_ok(fc, info["date"], now):
        return "date started or too far"
    md = model(fc, ens, info["kind"], info["date"])
    if not md:
        return "no forecast"
    mean_c, sigma, n = md
    probs = bucket_probs(mean_c, sigma, info["buckets"], info["unit"])
    rows = []
    for (lo, hi, m, tok), p in zip(info["buckets"], probs):
        q = quote(bk.get(tok), m, usd) if m.get("acceptingOrders") and not m.get("closed") else None
        if q and P.PX_MIN <= q[1] <= P.PX_MAX:
            rows.append(dict(tok=tok, m=m, p=p, cost=q[0], px=q[1], edge=p - q[0], title=m.get("groupItemTitle")))
    if not rows:
        return "no buyable bucket"
    mean = mean_c if info["unit"] == "C" else mean_c * 9 / 5 + 32
    return dict(best=max(rows, key=lambda r: r["edge"]), rows=rows, probs=probs, mean=mean, sigma=sigma, n=n)


def settle_and_mark(s):
    if not s["pos"]:
        return
    conds = [q["cond"] for q in s["pos"].values()]
    try:
        res, mk, bk = P.resolutions(conds), P.markets(conds), books(list(s["pos"]))
    except Exception as e:
        print(f"weather settle/mark fetch: {type(e).__name__}")
        return
    for t, q in list(s["pos"].items()):
        pay, why = P.resolved_payout(res.get(q["cond"]), mk.get(q["cond"]), q["oi"])
        if pay is not None:
            P.settle(s, t, pay, why)
            print(f"  RESOLVED {q['coin'][:60]} -> {pay}")
        elif why:
            print(f"  {q['coin'][:40]}: {why}")
        elif P.levels(bk.get(t), "bids"):
            q["last"] = P.levels(bk[t], "bids")[0][0]


def scan(s, tw, now, rng, log):
    evs = events(now)
    parsed, skipped = [], {}
    for e in evs:
        info, why = parse_event(e)
        if info:
            parsed.append((e, info))
        else:
            skipped[why] = skipped.get(why, 0) + 1
    todo = [(e, i) for e, i in parsed if str(e["id"]) not in s["done"]]
    st = stations({i["icao"] for _, i in todo})
    coords = sorted({(i["icao"], *st[i["icao"]][:2]) for _, i in todo if i["icao"] in st})
    fc = forecasts(coords) if coords else {}
    usd = s["start_usd"] * P.SIZE
    live = [(e, i) for e, i in todo if i["icao"] in fc and lead_ok(fc[i["icao"]][0], i["date"], now)]
    bk = books([b[3] for _, i in live for b in i["buckets"]]) if live else {}
    rows, bought, evals = [], 0, []
    for e, info in live:
        ev = evaluate(info, fc[info["icao"]], bk, usd, now)
        if isinstance(ev, str):
            rows.append(dict(t=int(now), ev=e.get("slug", "")[:60], icao=info["icao"], skip=ev))
        else:
            evals.append((e, info, ev))
    evals.sort(key=lambda x: -x[2]["best"]["edge"])          # cash is limited: biggest edge first
    for e, info, ev in evals:
        b = ev["best"]
        row = dict(t=int(now), ev=e.get("slug", "")[:60], icao=info["icao"], date=info["date"], k=info["kind"], u=info["unit"],
                   mean=round(ev["mean"], 2), sd=round(ev["sigma"], 2), n=ev["n"], bk=b["title"], p=round(b["p"], 4), cost=round(b["cost"], 4), edge=round(b["edge"], 4))
        if b["edge"] >= EDGE_MIN:
            pair = f"{e['id']}-{int(now)}"
            why = (f"{info['icao']} {info['date']} {info['kind']} พยากรณ์ {ev['mean']:.1f}°{info['unit']} sigma {ev['sigma']:.2f}°C ({ev['n']} members) "
                   f"ช่อง {b['title']} p {b['p']:.3f} ทุน {b['cost']:.3f} edge {b['edge']:+.3f}")
            r = P.buy(s, b["tok"], b["m"], 0, bk.get(b["tok"]), why, event=str(e["id"]), p_model=round(b["p"], 4), edge=round(b["edge"], 4), pair=pair)
            row["bought"] = r is None
            if r is None:
                s["done"][str(e["id"])] = int(now)
                bought += 1
                opts = ev["rows"][:]
                rng.shuffle(opts)
                tr = "no buyable bucket"
                for o in opts:
                    tr = P.buy(tw, o["tok"], o["m"], 0, bk.get(o["tok"]), f"สุ่มช่อง {o['title']} คู่กับ {pair} (p โมเดล {o['p']:.3f})",
                               event=str(e["id"]), p_model=round(o["p"], 4), pair=pair)
                    if tr is None:
                        break
                if tr is not None:
                    tw["log"].append(dict(kind="skip", t=P.now_iso(), pair=pair, why=tr))
                print(f"  BUY {e.get('title', '')[:50]} {b['title']} p {b['p']:.3f} cost {b['cost']:.3f} | twin {'bought' if tr is None else tr}")
            else:
                row["why"] = r
        rows.append(row)
    if rows:
        log.parent.mkdir(exist_ok=True)
        with open(log, "a") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        try:
            lines = log.read_text().splitlines()
            if len(lines) > LOG_KEEP:
                log.write_text("\n".join(lines[-LOG_KEEP:]) + "\n")
        except OSError:
            pass
    edges = [r["edge"] for r in rows if "edge" in r]
    print(f"poly weather scan: {len(evs)} events, {len(parsed)} parsed (skipped {skipped}), {len(live)} not started yet, "
          f"{len(edges)} priced, best edge {max(edges, default=float('nan')):+.3f}, bought {bought}")


def cmd_run(main=None, twin=None, log=None, force=False):
    main, twin, log = main or MAIN, twin or TWIN, Path(log or LOG)
    s, tw = load(main), load(twin)
    now, t0 = time.time(), time.time()
    if force or now - s.get("last_scan", 0) >= SCAN_H * 3600:
        try:
            scan(s, tw, now, random.Random(), log)
            s["last_scan"] = int(now)
        except Exception as e:
            print(f"poly weather scan fetch: {type(e).__name__}: {str(e)[:80]}")
    s["done"] = {k: v for k, v in s["done"].items() if v > now - 10 * 86400}
    for x in (s, tw):
        settle_and_mark(x)
    P.save(main, s)
    P.save(twin, tw)
    print(f"poly weather {P.value(s) / s['start_usd'] - 1:+.1%} open {len(s['pos'])} | twin {P.value(tw) / tw['start_usd'] - 1:+.1%} "
          f"open {len(tw['pos'])} ({time.time() - t0:.1f}s)")


def cmd_status():
    for f in (MAIN, TWIN):
        s = load(f)
        sells = [x for x in s["log"] if x["kind"] == "sell"]
        avg = sum(x["pnl"] / (x["usd"] - x["pnl"]) for x in sells) / len(sells) if sells else 0
        print(f"{Path(f).name[6:-5]:<18} {P.value(s) / s['start_usd'] - 1:+.1%}  เปิด {len(s['pos'])}  ปิด {len(sells)} "
              f"(ชนะ {sum(x['pnl'] > 0 for x in sells)})  เฉลี่ยต่อไม้ {avg:+.1%}")


if __name__ == "__main__":
    cmds = {"run": cmd_run, "status": cmd_status, "scan": lambda: cmd_run(force=True)}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]]()
