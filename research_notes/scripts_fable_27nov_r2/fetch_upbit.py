"""All Upbit 'trade' notices (about 165 pages). Resumable, 7 s apart, long back-off on 429. Saves r2/upbit_notices.json"""
import json, time, os, r2lib as L
fn = f"{L.R2}/upbit_notices.json"
ns = json.load(open(fn)) if os.path.exists(fn) else []
seen = {x["id"] for x in ns}; p = len(ns) // 20 + 1; fails = 0
while True:
    try: j = json.loads(L.raw(f"https://api-manager.upbit.com/api/v1/announcements?os=web&page={p}&per_page=20&category=trade", tries=1))
    except Exception as e:
        fails += 1; print("ERR page", p, e, flush=True)
        if fails > 8: break
        time.sleep(60); continue
    x = j["data"]["notices"]; ns += [y for y in x if y["id"] not in seen]; seen |= {y["id"] for y in x}
    json.dump(ns, open(fn, "w"))
    if p % 10 == 0: print("page", p, len(ns), flush=True)
    if not x or p >= j["data"]["total_pages"]: break
    p += 1; time.sleep(7)
print("saved", len(ns), ns[-1]["listed_at"] if ns else None)
