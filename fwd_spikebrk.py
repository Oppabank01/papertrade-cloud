#!/usr/bin/env python3
"""Forward paper test of "volatile_breakout" (jfsantiago/autotrading), opened 29 Nov 2026 by the scout. Fake money only.
Repo rule: 1h bars, close up >= 5% over 5 bars and volume z-score (20 bars) >= 2 -> long, mirror -> short, stop 3%,
target 6% (12%/24% of margin at 4x), opposite signal closes. byttrade.fetch serves 4h bars without volume, so this
account runs on 4h bars and uses the z-score of the bar range (h-l)/c instead of volume. Backtest of this exact version
(Binance 4h to 28 Nov 2026, 0.35%/side): 1,185 trades -0.48% per trade, median -3.70%, win 36%, 2025 +0.14%;
permutation 200 (before costs) PEPE p 0.070 WIF 0.075 INJ 0.567 ARB 0.124 WLD 0.050. The volume version: -0.44%,
p 0.005 to 0.398. Not a pass; opened because the user wants weak ideas tried.

On each closed 4h bar: signal as above -> enter at the next open. Stop/target checked on closed bars from the entry
bar on; a gap through fills at the open; a bar touching both = stop. Opposite signal -> out at the next open, no new
entry from the exit bar. One position per coin, one fifth of the start per coin, 0.35% per side.
  state_fwd_spikebrk.json       PEPE, WIF, INJ, ARB, WLD
  state_fwd_spikebrk_twin.json  control: random entry times (TWIN_P of free bars), random side, same exits
  python3 fwd_spikebrk.py"""
import math, random
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                        # per side, as every account here
SYMS = ["PEPEUSDT", "WIFUSDT", "INJUSDT", "ARBUSDT", "WLDUSDT"]   # the repo's volatile list
W, TH, ZW, Z = 5, 0.05, 20, 2.0      # repo numbers: 5 bars, 5%, 20-bar z-score, z >= 2
STOP, TGT = 0.03, 0.06               # repo: 12% / 24% of margin at 4x leverage = 3% / 6% of price
TWIN_P = 1 / 30                      # my choice: about the rule's rate (1,185 trades in ~42,000 coin-bars)
LABEL = ("ทะลุแรง 4 ชม. เหรียญผันผวน PEPE WIF INJ ARB WLD: 5 แท่งขึ้น 5%+ และแท่งกว้างผิดปกติ (z 2+) เข้า long ลงกลับกัน short "
         "stop 3% เป้า 6% (backtest 1,185 ไม้ หลังหัก -0.48% ต่อไม้ มัธยฐาน -3.70% p 0.05 ถึง 0.57 ยังไม่ผ่าน)")
ACCOUNTS = {"state_fwd_spikebrk.json": ("rule", LABEL),
            "state_fwd_spikebrk_twin.json": ("random", "ทะลุแรง ตัวควบคุม: เข้าสุ่มเวลา ทิศสุ่ม ออกแบบเดียวกัน")}


def signals(b):
    """+1 / -1 / 0 per bar from that bar's close (range z-score includes the bar itself, ddof 0, as the repo)."""
    out = [0] * len(b)
    for i in range(max(W, ZW - 1), len(b)):
        v = [(x["h"] - x["l"]) / x["c"] for x in b[i - ZW + 1:i + 1]]
        m = sum(v) / ZW
        sd = math.sqrt(sum((a - m) ** 2 for a in v) / ZW)
        if sd <= 0 or (v[-1] - m) / sd < Z:
            continue
        ch = b[i]["c"] / b[i - W]["c"] - 1
        out[i] = 1 if ch >= TH else -1 if ch <= -TH else 0
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    sg = signals(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            o, h, l, d = x["o"], x["h"], x["l"], p["d"]
            hit = (o if o <= p["stop"] else p["stop"] if l <= p["stop"] else max(p["tgt"], o) if h >= p["tgt"] else None) if d > 0 else \
                  (o if o >= p["stop"] else p["stop"] if h >= p["stop"] else min(p["tgt"], o) if l <= p["tgt"] else None)
            if hit is not None:
                close(s, sym, hit, x["t"] + H4, "stop 3%" if (hit - p["entry"]) * d < 0 else "ถึงเป้า 6%")
                exited = True
            elif sg[i] == -d:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "สัญญาณกลับทิศ")
                exited = True
        if sym in s["pos"] or exited:
            continue
        if mode == "rule":
            d = sg[i]
        else:
            d = rng.choice((1, -1)) if rng.random() < TWIN_P else 0
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 5
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = f"ทะลุแรง{'ขึ้น' if d > 0 else 'ลง'} 5 แท่ง 5%+ แท่งกว้าง z 2+" if mode == "rule" else "สุ่มเวลา สุ่มทิศ"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=e * (1 - d * STOP), tgt=e * (1 + d * TGT), entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_spikebrk fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
