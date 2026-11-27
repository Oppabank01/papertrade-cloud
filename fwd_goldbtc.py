#!/usr/bin/env python3
"""Forward paper test of Quantpedia's "Dual Momentum Allocation Between Physical Gold and Bitcoin (Digital Gold)"
(Cyril Dujava, 6 May 2026, https://quantpedia.com/?p=45559; GLD vs IBIT, weekly at the Wednesday close, the page's
headline 8-week lookback). Opened 28 Nov 2026 by the scout; backtest in LABEL. Fake money only.

On closed 4h Binance bars, PAXG for GLD and BTCUSDT for IBIT (my choice: both trade on Binance):
  at the bar that opens Wednesday 20:00 UTC (its close is the Wednesday daily close; my choice of the UTC day), take each
  coin's return since the same bar 8 weeks before. Hold BTC if its return beats PAXG's and is above 0, PAXG if its return
  beats BTC's and is above 0, else cash. A change -> sell at the next open, buy the new one at the same open.
One position at a time with the whole account (the page holds 100% of one asset), 0.35% per side, no leverage, no
volatility cap (the page's second variant; my choice: the plain one).
  state_fwd_goldbtc.json       BTC or PAXG or cash
  state_fwd_goldbtc_twin.json  control: every Wednesday a random pick of BTC, PAXG or cash, the same timing and costs
  python3 fwd_goldbtc.py"""
import random
from datetime import datetime, timezone
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "PAXGUSDT"]
WEEKS = 8                              # the page's headline lookback
WEEK = 7 * B.DAY
LABEL = ("หมุนทองกับ BTC รายสัปดาห์ (Quantpedia dual momentum 8 สัปดาห์) ถือตัวที่ขึ้นมากกว่าและบวก ไม่งั้นถือเงินสด "
         "(backtest Binance 4 ชม. PAXG กับ BTC 28 ส.ค. 63 ถึง 28 พ.ย. 69 หลังหัก 0.35%/ข้าง 31 ไม้ +17.6% ต่อไม้ "
         "มัธยฐาน +1.4% ชนะ 52% CAGR +67% เงิน x22.8 เทียบถือ BTC x5.2 ถือ PAXG x1.9 ปี 2025+ 6 ไม้ +9.2% "
         "ตัวแฝดสุ่มเลือกทุกพุธ CAGR มัธยฐาน -6.8% กริด 10 ช่วง (1 ถึง 28 สัปดาห์) ดีสุดคือ 8 สัปดาห์ "
         "permutation 200 รอบทั้งกริด ก่อนหัก p 0.005 แต่ 8 สัปดาห์ถูกเลือกจากข้อมูลช่วงเดียวกันโดยผู้เขียน)")
ACCOUNTS = {"state_fwd_goldbtc.json": ("rule", LABEL),
            "state_fwd_goldbtc_twin.json": ("random", "หมุนทองกับ BTC ตัวควบคุม: ทุกพุธสุ่มเลือก BTC PAXG หรือเงินสด")}


def is_wed_close(t):
    d = datetime.fromtimestamp(t / 1000, timezone.utc)
    return d.weekday() == 2 and d.hour == 20


def pick(ca, cg, t):
    """The coin to hold after the Wednesday bar t, None for cash; False when the 8-week-old bar is missing."""
    t0 = t - WEEKS * WEEK
    if t0 not in ca or t0 not in cg:
        return False
    ra, rg = ca[t]["c"] / ca[t0]["c"] - 1, cg[t]["c"] / cg[t0]["c"] - 1
    return "BTCUSDT" if ra > rg and ra > 0 else "PAXGUSDT" if rg > ra and rg > 0 else None


def trades(bb):
    """The backtest (the scout's /tmp/scout_0619/dm.py): list of dict(sym, t, e, x), oldest first."""
    nb = {s: {x["t"]: x for x in bb[s]} for s in SYMS}
    ts = sorted(set(nb["BTCUSDT"]) & set(nb["PAXGUSDT"]))
    out, p = [], None
    for j, t in enumerate(ts[:-1]):
        if not is_wed_close(t):
            continue
        want = pick(nb["BTCUSDT"], nb["PAXGUSDT"], t)
        if want is False:
            continue
        nt = ts[j + 1]
        if p and p["sym"] != want:
            out.append(dict(sym=p["sym"], t=p["t"], e=p["e"], x=nb[p["sym"]][nt]["o"]))
            p = None
        if not p and want:
            p = dict(sym=want, t=nt, e=nb[want][nt]["o"])
    return out


def close(s, sym, px, t, why):   # as pullback.close, long only
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px * (1 - COST)
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, bb, mode, rng):
    """bb: {sym: bars}; walks the closed bars common to both coins after s["seen"]["DM"]."""
    nb = {sym: {x["t"]: x for x in bb[sym]} for sym in SYMS}
    ts = sorted(set(nb["BTCUSDT"]) & set(nb["PAXGUSDT"]))
    closed = {t for t in ts if nb["BTCUSDT"][t]["closed"] and nb["PAXGUSDT"][t]["closed"]}
    seen = s.setdefault("seen", {})
    if "DM" not in seen:
        seen["DM"] = max(closed)
        return
    for j, t in enumerate(ts[:-1]):
        if t <= seen["DM"] or t not in closed:
            continue
        seen["DM"] = t
        if not is_wed_close(t):
            continue
        want = pick(nb["BTCUSDT"], nb["PAXGUSDT"], t)
        if want is False:
            continue
        if mode != "rule":
            want = rng.choice(("BTCUSDT", "PAXGUSDT", None))
        nt = ts[j + 1]
        held = next(iter(s["pos"]), None)
        if held and held != want:
            close(s, held, nb[held][nt]["o"], nt, "สลับตัวถือตามโมเมนตัม 8 สัปดาห์" if mode == "rule" else "สุ่มสลับ")
        if s["pos"] or not want:
            continue
        e, usd = nb[want][nt]["o"], s["cash"] / (1 + COST)
        if usd <= 0:
            continue
        s["cash"] -= usd * (1 + COST)
        why = f"{want[:-4]} ขึ้นมากกว่าใน 8 สัปดาห์และบวก" if mode == "rule" else "สุ่มเลือกตัวถือ"
        s["pos"][want] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=nt, t=iso(nt), why=why)
        s["log"].append(dict(kind="buy", t=iso(nt), coin=want[:-4], side="long", px=e, usd=usd, why=why))
    for sym, p in s["pos"].items():
        p["last"] = bb[sym][-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_goldbtc fetch failed", sym, type(e).__name__)
    if len(cache) < len(SYMS):
        return   # the rule needs both coins; a missing one is not guessed
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        step(s, cache, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
