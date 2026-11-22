#!/usr/bin/env python3
"""Adds the weekly DCA (BTC, VOO) and the 100k trend account to data/board.json. Their state files use their own
schema, so review.py skips them. A failed price leaves the row in with no result (never a guessed value)."""
import json, os, sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.getcwd())
import paper, stock   # noqa: E402  (repo scripts: Binance TH and Yahoo price helpers)

TZ = timezone(timedelta(hours=7))
now = datetime.now(TZ)


def hours_since(dt):
    return (now - dt).total_seconds() / 3600 if dt else None


def row(file, label, verdict, pnl, n, last, why):
    return dict(file=file, label=label, verdict=verdict, pnl=pnl, closed=n, wins="-", open=0, idle_h=hours_since(last),
                per_day=0, why=why, halted=None, dead=None)


def dca():
    s = json.load(open("state_dca.json"))
    last = datetime.strptime(s["log"][-1][:16], "%Y-%m-%d %H:%M").replace(tzinfo=TZ) if s.get("log") else None
    try:
        value = s["coins"] * paper.price("BTCTHB")
        pnl, why = value / s["spent"] - 1, f"ลงไปแล้ว {s['spent']:,.0f} บาท ถือ {s['coins']:.5f} BTC มูลค่า {value:,.0f} บาท"
    except Exception as e:
        pnl, why = None, f"ดึงราคา BTC ไม่ได้ ({type(e).__name__})"
    return row("state_dca.json", f"DCA BTC ฉลาด: สัปดาห์ละ {s['base']:,.0f} บาท ซื้อหนักขึ้นตอนราคาถูก", "ออมรายสัปดาห์",
               pnl, len(s.get("buys", [])), last, why + " (ผล = เทียบเงินที่ลงไป)")


def voo():
    s = json.load(open("state_stock.json"))
    last = datetime.strptime(s["week"] + "-1", "%G-W%V-%u").replace(tzinfo=TZ) if s.get("week") else None
    try:
        px, _, _ = stock.price_thb()
        value = s["units"] * px
        pnl, why = value / s["spent"] - 1, f"ลงไปแล้ว {s['spent']:,.0f} บาท ถือ {s['units']:.4f} หน่วย มูลค่า {value:,.0f} บาท"
    except Exception as e:
        pnl, why = None, f"ดึงราคา VOO ไม่ได้ ({type(e).__name__})"
    return row("state_stock.json", f"DCA หุ้น VOO (S&P 500): สัปดาห์ละ {s['base']:,.0f} บาท", "ออมรายสัปดาห์",
               pnl, len(s.get("buys", [])), last, why + " (ผล = เทียบเงินที่ลงไป)")


def trend():
    s = json.load(open("state.json"))
    try:
        value = s["cash"] + sum(p["qty"] * paper.price(sym) for sym, p in s.get("positions", {}).items())
        pnl = value / s["start"] - 1
    except Exception as e:
        pnl = None
        print("trend price failed", type(e).__name__)
    n = len(s.get("trades", []))
    why = f"ถืออยู่ {len(s.get('positions', {}))} ตัว" if n or s.get("positions") else f"ยังไม่มีสัญญาณ เริ่ม {s['start_day']} (ซื้อเมื่อทะลุจุดสูง 20 วันขณะ BTC เหนือ MA200)"
    return row("state.json", f"ตามเทรนด์เหรียญใหญ่ {s['start']:,.0f} บาท (breakout + MA50)", "รอข้อมูล", pnl, n, None, why)


def main():
    path = "data/board.json"
    b = json.load(open(path))
    b["rows"] = [r for r in b["rows"] if r["file"] not in ("state_dca.json", "state_stock.json", "state.json")]
    for f in (dca, voo, trend):
        try:
            b["rows"].append(f())
        except Exception as e:                      # one broken account must not drop the others from the page
            print("board_extra", f.__name__, "failed:", repr(e)[:150])
    tmp = path + ".tmp"
    json.dump(b, open(tmp, "w"), ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, path)


if __name__ == "__main__":
    main()
