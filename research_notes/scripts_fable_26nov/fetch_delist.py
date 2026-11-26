import json, urllib.request, time, pickle, re
H = {"User-Agent": "Mozilla/5.0", "clienttype": "web"}
def get(u):
    for i in range(4):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=25).read())
        except Exception as e: err = e; time.sleep(5)
    raise err
arts = []
for p in range(1, 12):
    d = get(f"https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&catalogId=161&pageNo={p}&pageSize=50")
    a = d["data"]["catalogs"][0]["articles"]
    if not a: break
    arts += a; time.sleep(1.5)
    if a[-1]["releaseDate"] < 1748736000000: break   # before Jun 2025
print("articles", len(arts))
out = []
for a in arts:
    t = a["title"]
    if a["releaseDate"] < 1751328000000: continue
    kind = None
    if re.search(r"Binance Futures Will Delist", t): kind = "fut"
    elif re.match(r"Binance Will Delist ", t) and "Trading Pair" not in t: kind = "spot"
    if not kind: continue
    body = ""
    if kind == "fut" and "Multiple" in t:
        try:
            d = get(f"https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode={a['code']}")
            body = json.dumps(d["data"].get("body") or d["data"])[:20000]
        except Exception as e: print("detail err", e)
        time.sleep(1.5)
    out.append(dict(t=a["releaseDate"], title=t, kind=kind, body=body))
pickle.dump(out, open("delist.pkl", "wb"))
for x in out: print(time.strftime("%Y-%m-%d %H:%M", time.gmtime(x["t"] / 1000)), x["kind"], x["title"][:120], "| body syms:", sorted(set(re.findall(r"\b[A-Z0-9]{2,15}USDT\b", x["body"])))[:12])
