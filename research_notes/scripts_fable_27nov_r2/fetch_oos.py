"""Fresh universe for an out-of-sample check of the pre-XD rule: SET/mai common stocks NOT in the first list, picked by
30-day turnover from the keyless TradingView scanner (also the live source of upcoming XD dates). Yahoo daily + dividends."""
import json, os, r2lib as L
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_yahoo.py")).read().split("ok = []")[0])
body = json.dumps({"filter": [{"left": "type", "operation": "equal", "right": "stock"}, {"left": "subtype", "operation": "in_range", "right": ["common"]}],
                   "columns": ["name", "close", "average_volume_30d_calc", "dividends_yield_current", "exchange"],
                   "sort": {"sortBy": "average_volume_30d_calc", "sortOrder": "desc"}, "range": [0, 1500], "markets": ["thailand"]}).encode()
fn = f"{L.R2}/tv_universe.json"
if os.path.exists(fn): j = json.load(open(fn))
else: j = json.loads(L.raw("https://scanner.tradingview.com/thailand/scan", data=body)); json.dump(j, open(fn, "w"))
rows = [(r["d"][0], (r["d"][1] or 0) * (r["d"][2] or 0), r["d"][3] or 0) for r in j["data"] if r["d"][0] and "." not in r["d"][0]]
rows = [r for r in rows if r[0] not in set(SET) and not r[0][-2:].isdigit() and r[2] > 0]
rows.sort(key=lambda r: -r[1]); pick = [r[0] for r in rows[:260]]
print("scanner rows", len(j["data"]), "candidates", len(rows), "picked", len(pick), "turnover of the last pick (THB/day)", round(rows[min(259, len(rows) - 1)][1]))
ok = []
for s in pick:
    d = L.yahoo(s + ".BK")
    if d is not None and len(d["t"]) > 300: ok.append(s)
json.dump(ok, open(f"{L.R2}/oos_tickers.json", "w")); print("with Yahoo data", len(ok)); print(" ".join(ok))
