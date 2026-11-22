#!/usr/bin/env python3
"""Forward paper test of an inside-bar / NR7 breakout on 4h BTC, ETH, SOL bars (opened 23 Nov 2026 from a batch of simple
bar ideas; backtest in LABEL, opened at any p because the user asked to try everything). Fake money only.

Setup bar: KIND = "ib" (high and low inside the previous bar), "nr7" (narrowest range of the last 7 bars) or "both".
Next 4h bar only: a trade above the setup high -> long at max(open, setup high); else below the setup low -> short at
min(open, setup low) (if both broke, the long is booked and stopped, the worse case). Stop at the other side of the setup
bar, target TR x that risk, closed at the close of the HOLD-th bar. Entry bar: stop counts first, no gap fill; later bars:
gap through fills at the open, both touched = stop. One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_nr7.json       BTC, ETH, SOL
  state_fwd_nr7_twin.json  control: random entry bars (TWIN_P), random side, at the next open, risk = last bar's range
  python3 fwd_nr7.py"""
import random
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
# grid tried in-sample (bars before 2024, BTC+ETH+SOL pooled): setup ib/nr7/both x target 1R/2R x hold 3/6 bars = 12
GRID = [(k, r, h) for k in ("ib", "nr7", "both") for r in (1, 2) for h in (3, 6)]
KIND, TR, HOLD = "ib", 1, 6        # chosen: best pooled in-sample (pre-2024) mean per trade after costs
TWIN_P = 1 / 4                     # about the rule's trade rate (8,313 trades in ~35,000 free 4h coin-bars)
LABEL = ("inside bar 4 ชม. BTC ETH SOL: แท่งถัดไปทะลุกรอบแท่งในกรอบ เข้าตามทาง stop อีกฝั่ง เป้า 1R ถือสูงสุด 24 ชม. "
         "(backtest 2017-2026 หลังหัก 8,313 ไม้ เฉลี่ย -0.72% มัธยฐาน -0.95% p 0.005 แต่ยังขาดทุนหลังหัก ตก ปี 2024+ 2,854 ไม้ -0.69%)")
ACCOUNTS = {"state_fwd_nr7.json": ("rule", LABEL),
            "state_fwd_nr7_twin.json": ("random", "inside bar/NR7 ตัวควบคุม: เข้าแท่งสุ่ม ทิศสุ่ม stop เท่ากรอบแท่งล่าสุด")}


def ind(b):
    """(inside-bar flags, NR7 flags) per bar."""
    n, rg = len(b), [x["h"] - x["l"] for x in b]
    ib, nr = [False] * n, [False] * n
    for s in range(1, n):
        ib[s] = b[s]["h"] < b[s - 1]["h"] and b[s]["l"] > b[s - 1]["l"]
        nr[s] = s >= 6 and rg[s] <= min(rg[s - 6:s])
    return ib, nr


def is_setup(flags, s, kind=KIND):
    ib, nr = flags
    return ib[s] if kind == "ib" else nr[s] if kind == "nr7" else ib[s] and nr[s]


def entry_at(b, i, flags, kind=KIND, tr=TR):
    """(d, entry, stop, target) when bar i breaks setup bar i-1, else None."""
    if i < 2 or not is_setup(flags, i - 1, kind) or b[i]["t"] != b[i - 1]["t"] + H4:
        return None
    up, dn, x = b[i - 1]["h"], b[i - 1]["l"], b[i]
    if up <= dn:
        return None
    if x["h"] > up:
        e = max(x["o"], up)
        return 1, e, dn, e + tr * (e - dn)
    if x["l"] < dn:
        e = min(x["o"], dn)
        return -1, e, up, e - tr * (up - e)
    return None


def hit(x, stop, tgt, d, first=False):
    o, h, l = x["o"], x["h"], x["l"]
    if first:                      # entered inside this bar: no gap fill, stop first
        return (stop if l <= stop else tgt if h >= tgt else None) if d > 0 else (stop if h >= stop else tgt if l <= tgt else None)
    if d > 0:
        return o if o <= stop else stop if l <= stop else max(tgt, o) if h >= tgt else None
    return o if o >= stop else stop if h >= stop else min(tgt, o) if l <= tgt else None


def trades(b, kind=KIND, tr=TR, hold=HOLD, first=7, flags=None):
    """The backtest: list of dict(t, d, e, x) on closed bars, oldest first."""
    flags, out, i, n = flags or ind(b), [], first, len(b)
    while i < n:
        g = entry_at(b, i, flags, kind, tr)
        if not g:
            i += 1
            continue
        d, e, stop, tgt = g
        t0, j, px = b[i]["t"], i, None
        while j < n:
            px = hit(b[j], stop, tgt, d, j == i)
            if px is None and b[j]["t"] >= t0 + (hold - 1) * H4:
                px = b[j]["c"]
            if px is not None:
                break
            j += 1
        if px is None:
            break
        out.append(dict(t=t0, d=d, e=e, x=px))
        i = j + 1
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def manage(s, sym, x, first):
    """Exit check of the open position on one closed bar; True when it closed."""
    p = s["pos"][sym]
    px = hit(x, p["stop"], p["tgt"], p["d"], first)
    why = None if px is None else "stop" if (px - p["entry"]) * p["d"] < 0 else f"ถึงเป้า {TR}R"
    if px is None and x["t"] >= p["until"]:
        px, why = x["c"], f"ครบ {HOLD} แท่ง"
    if px is None:
        return False
    close(s, sym, px, x["t"] + H4, why)
    return True


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    flags = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["check_t"]:
            exited = manage(s, sym, x, False)
        if sym in s["pos"] or exited:
            continue
        usd = s["start_usd"] / 3
        if mode == "rule":
            g = entry_at(bars, i, flags)
            t0, chk, why = x["t"], x["t"], f"ทะลุแท่ง {KIND}"
        else:
            r = x["h"] - x["l"]
            if r <= 0 or rng.random() >= TWIN_P:
                continue
            d, e = rng.choice((1, -1)), bars[i + 1]["o"]
            g, t0, chk, why = (d, e, e - d * r, e + d * TR * r), bars[i + 1]["t"], bars[i + 1]["t"], "สุ่มแท่ง สุ่มทิศ"
        if not g:
            continue
        d, e, stop, tgt = g
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd, stop=stop,
                             tgt=tgt, until=t0 + (HOLD - 1) * H4, entry_t=t0, check_t=chk + (H4 if mode == "rule" else 0),
                             t=iso(t0), why=why)
        s["log"].append(dict(kind="buy", t=iso(t0), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
        if mode == "rule":
            manage(s, sym, x, True)
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_nr7 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
