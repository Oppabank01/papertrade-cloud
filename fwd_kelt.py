#!/usr/bin/env python3
"""Forward paper test of the Keltner Channel breakout (jellaasteecyi-tech/aiprove-i7-eth-pnl, GitHub 14 Nov 2026: AIProve
eth-pnl-fixed bounty, ETH 4h, best set B: EMA20 + 2.5 x ATR10 band, stop 2 ATR, target 3 ATR, exit on a close back below
the mid-line; +13.4% on 6 trades in 90 days) on BTC, ETH, SOL, BNB, XRP (opened 27 Nov 2026 by the scout; backtest in
LABEL, opened at any p because the user asked to try weak ideas too). Fake money only.

On closed 4h Binance bars, long only: EMA(N) of close seeded with the first close, Wilder ATR(AN) seeded with the mean of
the first AN true ranges. BUY when flat and the bar closes above EMA + K x ATR (from bar WARM on); fill at the next real
open, stop = entry - SM x ATR and target = entry + TM x ATR with the ATR of the signal bar. From the fill bar on, each
closed bar: stop first (fills at the stop, or the open if it gapped below), then target (the stop's mirror), then a close
below the EMA sells at the next open. One position per coin, one fifth of the start per coin, 0.35% per side.
  state_fwd_kelt.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_kelt_twin.json  control: random entry bars (TWIN_P per free bar), same stop, target and mid-line exit
  python3 fwd_kelt.py"""
import random
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: the five majors the other 4h accounts use
N, AN, K, SM, TM = 20, 10, 2.5, 2.0, 3.0   # the repo's set B
WARM = 60                      # the repo's 60 warm-up candles
TWIN_P = 1 / 45                # my choice: the backtest twin's rate (2 x 224 BTC trades / 20,314 4h bars)
# also mine: Wilder ATR (the repo does not say which), fills at the next open (the repo fills at the signal close),
# long only (the repo also shorts the mirror), coins beyond ETH, size one fifth of the start per coin
LABEL = ("Keltner breakout 4 ชม. (aiprove-i7-eth-pnl ชุด B) BTC ETH SOL BNB XRP: ซื้อเมื่อปิดเหนือ EMA20 + 2.5 ATR10 "
         "stop 2 ATR เป้า 3 ATR หรือออกเมื่อปิดใต้ EMA20 (backtest Binance 4 ชม. 2017 ถึง 26 พ.ย. 69 หลังหัก 0.35%/ข้าง "
         "BTC 224 ไม้ +0.25% ต่อไม้ มัธยฐาน -0.25% ชนะ 49% ETH 223 ไม้ +0.49% SOL 133 ไม้ +1.09% BNB 213 ไม้ -0.89% "
         "XRP 186 ไม้ -0.00% ตัวแฝดเข้าสุ่มออกแบบเดียวกัน -0.51 ถึง -0.77% แพ้กฎ 4 ใน 5 เหรียญ ตั้งแต่ 2025 -1.26 ถึง +0.00% "
         "ต่อไม้ permutation 200 รอบบน 6,000 แท่งล่าสุด กริด 3 แบบ p 0.443/0.109/0.104/0.567/0.005)")
ACCOUNTS = {"state_fwd_kelt.json": ("rule", LABEL),
            "state_fwd_kelt_twin.json": ("random", "Keltner breakout 4 ชม. ตัวควบคุม: เข้าแท่งสุ่ม stop 2 ATR เป้า 3 ATR ออกใต้ EMA20 แบบเดียวกัน")}


def lines(b):
    """EMA(N) of close and Wilder ATR(AN) per bar (None until AN bars)"""
    a = 2 / (N + 1)
    ema, atr, trs, E, A = None, None, [], [], []
    for i, x in enumerate(b):
        ema = x["c"] if ema is None else a * x["c"] + (1 - a) * ema
        tr = x["h"] - x["l"] if i == 0 else max(x["h"], b[i - 1]["c"]) - min(x["l"], b[i - 1]["c"])
        trs.append(tr)
        if atr is None and len(trs) == AN:
            atr = sum(trs) / AN
        elif atr is not None:
            atr = (atr * (AN - 1) + tr) / AN
        E.append(ema); A.append(atr)
    return E, A


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
    E, A = lines(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p:
            if x["t"] >= p["entry_t"]:
                if x["o"] <= p["stop"] or x["l"] <= p["stop"]:
                    close(s, sym, min(x["o"], p["stop"]), x["t"], "หลุด stop 2 ATR")
                elif x["o"] >= p["target"] or x["h"] >= p["target"]:
                    close(s, sym, max(x["o"], p["target"]), x["t"], "ถึงเป้า 3 ATR")
                elif x["c"] < E[i]:
                    close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "ปิดใต้ EMA20")
            continue
        if i < WARM:
            continue
        ok = x["c"] > E[i] + K * A[i] if mode == "rule" else rng.random() < TWIN_P
        if not ok:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "ปิดเหนือ EMA20 + 2.5 ATR" if mode == "rule" else "สุ่มแท่ง"
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / en, entry=en, last=en, usd=usd, entry_t=et, t=iso(et), why=why,
                             stop=en - SM * A[i], target=en + TM * A[i])
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=en, usd=usd, why=why,
                             stop_set=en - SM * A[i]))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_kelt fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
