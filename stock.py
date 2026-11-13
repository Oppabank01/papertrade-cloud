#!/usr/bin/env python3
"""Paper account 4: plain weekly DCA into an S&P 500 ETF (VOO), priced in THB.
The approach with the strongest evidence for small retail money (reports/ท่าเทรดที่ได้ผลจริงสำหรับรายย่อย.md).
Rules are in RULES_STOCK.md.

  python3 stock.py init 10000 250     # paper budget 10,000 THB, 250 THB a week
  python3 stock.py run                # buys once per ISO week, safe to run daily
  python3 stock.py status
Standard library only. Price from Yahoo chart API, USD/THB from Binance TH USDTTHB.
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SYM = "VOO"
COST = 0.005            # per buy: broker fee + FX spread (Dime/Webull style), assumed, conservative
STATE = Path(__file__).with_name("state_stock.json")
TH = timezone(timedelta(hours=7))


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def price_thb():
    usd = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{SYM}?range=1d&interval=1d")["chart"]["result"][0]["meta"]["regularMarketPrice"]
    fx = float(get("https://api.binance.th/api/v1/ticker/price?symbol=USDTTHB")["price"])
    return float(usd) * fx, float(usd), fx


def load():
    if not STATE.exists():
        sys.exit("ยังไม่มีบัญชี รัน: python3 stock.py init 10000 250")
    return json.loads(STATE.read_text())


def save(st):
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1))


def init(budget, base):
    if STATE.exists():
        sys.exit("มี state_stock.json อยู่แล้ว ลบเองถ้าจะเริ่มใหม่")
    save(dict(cash=budget, start=budget, base=base, units=0.0, spent=0.0, week="",
              start_day=datetime.now(TH).strftime("%Y-%m-%d"), buys=[]))
    print(f"บัญชีจำลองหุ้นดัชนี {SYM}: งบ {budget:,.0f} บาท ซื้อสัปดาห์ละ {base:,.0f} บาท")
    run()


def run():
    st = load()
    y, w, _ = datetime.now(TH).isocalendar()
    week = f"{y}-W{w:02d}"
    if st["week"] == week:
        print(f"สัปดาห์ {week} ซื้อไปแล้ว")
        return status(st)
    amt = min(st["base"], st["cash"])
    if amt <= 0:
        print("งบหมดแล้ว")
        return status(st)
    px, usd, fx = price_thb()
    units = amt * (1 - COST) / px
    st.update(cash=st["cash"] - amt, units=st["units"] + units, spent=st["spent"] + amt, week=week)
    st["buys"].append(dict(week=week, thb=amt, usd_px=usd, fx=fx, units=units))
    save(st)
    print(f"สัปดาห์ {week}: ซื้อ {SYM} {amt:,.0f} บาท ที่ ${usd:,.2f} (USDTHB {fx})")
    status(st)


def status(st=None):
    st = st or load()
    px, usd, _ = price_thb()
    value = st["units"] * px
    pnl = value / st["spent"] - 1 if st["spent"] else 0
    print(f"ลงไป {st['spent']:,.0f} จาก {st['start']:,.0f} บาท มูลค่า {value:,.0f} ({pnl:+.2%}) "
          f"{SYM} ตอนนี้ ${usd:,.2f}, ซื้อมาแล้ว {len(st['buys'])} สัปดาห์ เงินสดเหลือ {st['cash']:,.0f}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["init"] and len(a) == 3:
        init(float(a[1]), float(a[2]))
    elif a[:1] in (["run"], ["status"]):
        {"run": run, "status": status}[a[0]]()
    else:
        sys.exit(__doc__)
