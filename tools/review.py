#!/usr/bin/env python3
"""Copy of ~/.claude/skills/papertrade-review/scripts/review.py (cloud.sh writes data/board.json with it).
Honest review of paper-trade accounts (state_*.json with start_usd/cash/pos/log).

Flags accounts that stopped trading (halted / no trade for a long time) so their
frozen P&L is never reported as a win, compares every account with the random
controls, and applies the pass/dead rules from AGENT_RULES.md.
Standard library only. Prices of open positions use the last stored price.
"""
import argparse, glob, json, os, statistics, sys
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=7))
PASS_TRADES, DEAD_TRADES, BUST = 50, 20, 0.10
DEFAULT_COST = 0.01  # per side when a trade did not record cost_side (memecoin bot default)
GENERIC = {"state", "zoo", "w", "x", "i", "ban", "pause", "json", "500", "run", "night", "day", "d"}


def ts(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def review(path, now):
    try:
        s = json.load(open(path))
    except Exception:
        return None
    if not isinstance(s, dict) or "start_usd" not in s or "log" not in s:
        return None
    if isinstance(s.get("pos"), dict):            # memecoin schema: cash + open positions at last price
        value = s.get("cash", 0) + sum(q.get("qty", 0) * q.get("last", q.get("entry", 0)) for q in s["pos"].values())
    elif s.get("day_start"):                       # day-trade schema: value at start of today
        value = s["day_start"]
    elif s.get("history"):                         # daily schema: last recorded value
        value = s["history"][-1].get("usd", s["start_usd"])
    else:
        value = s.get("cash", s["start_usd"])
    pnl = value / s["start_usd"] - 1 if s["start_usd"] else 0
    log = [x for x in s["log"] if isinstance(x, dict)]
    sells = [x for x in log if x.get("kind") == "sell" and isinstance(x.get("pnl"), (int, float))]
    trades = [x for x in log if x.get("kind") in ("buy", "sell")]
    times = [t for t in (ts(x.get("t", "")) for x in log) if t]
    first, last = (min(times), max(ts(x["t"]) for x in trades if ts(x.get("t", "")))) if trades and times else (min(times) if times else None, None)
    days = max((now - first).total_seconds() / 86400, 1e-6) if first else None
    p = [x["pnl"] for x in sells]
    best = max(p) if p else 0
    # extra cost if fees+slippage were doubled: one more cost_side on entry and exit notional
    est = any("cost_side" not in x for x in sells)
    extra = sum(x.get("cost_side", DEFAULT_COST) * (2 * x.get("usd", 0) - x["pnl"]) for x in sells)
    idle_h = (now - last).total_seconds() / 3600 if last else None
    return dict(
        file=os.path.basename(path), label=s.get("label") or os.path.basename(path), pnl=pnl,
        start_thb=s.get("start_thb"), closed=len(sells), wins=sum(v > 0 for v in p),
        median=statistics.median(p) if p else None, mean=statistics.mean(p) if p else None,
        pnl_wo_best=(sum(p) - best) / s["start_usd"] if p else None,
        pnl_2xfee=None if any("usd" not in x for x in sells) else (value - extra) / s["start_usd"] - 1, fee_est=est,
        halted=s.get("halted") or ("ended: " + str(s["ended"]) if s.get("ended") else None), dead=s.get("dead"),
        open=len(s.get("pos") or {}), idle_h=idle_h, per_day=len(sells) / days if days else 0,
        started=first.astimezone(TZ).strftime("%d/%m %H:%M") if first else "-",
    )


def add_siblings(rows):
    """Accounts whose file names share a rule token are the same idea with nearby settings."""
    def toks(f):
        return {t for t in f[:-5].lower().split("_") if len(t) >= 4 and t not in GENERIC}
    for r in rows:
        r["siblings"] = [(o["file"][6:-5], o["pnl"]) for o in rows
                         if o is not r and toks(o["file"]) & toks(r["file"]) and not o["halted"]]


def verdict(r, rand_pnl, idle_limit, rand_key="rand"):
    if rand_key in r["file"]:
        return "ตัวควบคุม", "สุ่มซื้อ ใช้เป็นเส้นเทียบ"
    if r["pnl"] <= BUST - 1:
        return "พอร์ตแตก", f"เหลือ {100 * (1 + r['pnl']):.0f}% ของทุน"
    if r.get("dead"):                              # the runner's own death rule already stopped it: it will not trade again
        return "ตาย", "ระบบตัดสินตายแล้ว ไม่เทรดต่อ: " + str(r["dead"])[:70]
    if r["halted"]:
        return "ค้าง (หยุดซื้อ)", "ผลค้างจากก่อนหยุด ห้ามนับเป็นกำไร: " + str(r["halted"])[:70]
    if r["idle_h"] is not None and r["idle_h"] > idle_limit and r["open"] == 0:
        return "เงียบ", f"ไม่มีไม้ {r['idle_h']:.0f} ชม."
    beat = rand_pnl is None or r["pnl"] > rand_pnl
    if r["closed"] >= PASS_TRADES and r["pnl"] > 0 and beat:
        note = "ผ่านเกณฑ์"
        if r["pnl_wo_best"] is not None and r["pnl_wo_best"] <= 0:
            return "ผ่านแบบพึ่งไม้เดียว", "ตัดไม้ที่ดีที่สุดออกแล้วติดลบ"
        if r["pnl_2xfee"] is None or r["pnl_2xfee"] <= 0:
            return "ผ่านแบบเปราะ", "ค่าธรรมเนียม 2 เท่าแล้วติดลบ"
        bad = [x for x in r.get("siblings", []) if x[1] <= 0]
        if bad:
            return "ผ่านแบบเปราะ", "สูตรพี่น้องกฎใกล้กันขาดทุน: " + ", ".join(f"{n} {v:+.0%}" for n, v in bad[:3])
        return "ผ่าน", note
    if r["closed"] >= DEAD_TRADES and not (r["pnl"] > 0 and beat):
        return "ตาย", f"{r['closed']} ไม้แล้วยัง{'แพ้ตัวสุ่ม' if not beat else 'ไม่บวก'}"
    need = PASS_TRADES - r["closed"]
    eta = f"อีกราว {need / r['per_day']:.0f} วันถึง 50 ไม้" if r["per_day"] > 0 else f"ยังไม่มีไม้ที่ขายจบ เริ่ม {r['started']} รอสัญญาณ"
    return "รอข้อมูล", eta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*", default=[os.path.expanduser("/Volumes/Drive D/Code/Working Space/Projects/PaperTrade-cloud")])
    ap.add_argument("--rand", default="rand", help="substring of control account files")
    ap.add_argument("--idle", type=float, default=24, help="hours without a trade before flagging as quiet")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    now = datetime.now(TZ)
    rows = [r for d in a.dirs for f in sorted(glob.glob(os.path.join(d, "state_*.json"))) if (r := review(f, now))]
    add_siblings(rows)
    ctrl = [r for r in rows if a.rand in r["file"] and not r["halted"]]
    rand_pnl = max((r["pnl"] for r in ctrl), default=None)
    for r in rows:
        r["verdict"], r["why"] = verdict(r, rand_pnl, a.idle, a.rand)
    if a.json:
        print(json.dumps(dict(generated=now.isoformat(timespec="minutes"), rand_pnl=rand_pnl, rows=rows), ensure_ascii=False, indent=1, default=str)); return
    order = ["ผ่าน", "ผ่านแบบเปราะ", "ผ่านแบบพึ่งไม้เดียว", "รอข้อมูล", "ตัวควบคุม", "ค้าง (หยุดซื้อ)", "เงียบ", "ตาย", "พอร์ตแตก"]
    print(f"# ตรวจบัญชีเงินจำลอง {now:%d/%m %H:%M} ({len(rows)} บัญชี)\n")
    print(f"ตัวสุ่มที่ดีที่สุด (ยังซื้ออยู่): {'-' if rand_pnl is None else f'{rand_pnl:+.1%}'}\n")
    counts = {k: sum(r['verdict'] == k for r in rows) for k in order}
    print(" | ".join(f"{k} {v}" for k, v in counts.items() if v), "\n")
    print("| สถานะ | บัญชี | ผล | ค่าธรรมเนียม 2 เท่า | ไม้ปิด (ชนะ) | มัธยฐาน/ไม้ | ไม้/วัน | หมายเหตุ |\n|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: (order.index(r["verdict"]), -r["pnl"])):
        med = "-" if r["median"] is None else f"{r['median']:+.3f}$"
        f2 = "-" if r["pnl_2xfee"] is None else f"{r['pnl_2xfee']:+.1%}" + ("*" if r["fee_est"] else "")
        print(f"| {r['verdict']} | {r['label'][:46]} | {r['pnl']:+.1%} | {f2} | {r['closed']} ({r['wins']}) | {med} | {r['per_day']:.1f} | {r['why']} |")


    print("\n* ค่าธรรมเนียมบางไม้ไม่ได้บันทึก ใช้ค่าประมาณ 1% ต่อขา, - = ไม่มีขนาดไม้ คำนวณไม่ได้ (นับว่าไม่ผ่าน)")


if __name__ == "__main__":
    main()
