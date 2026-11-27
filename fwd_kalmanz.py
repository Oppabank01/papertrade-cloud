#!/usr/bin/env python3
"""Forward paper test of "KalmanZScoreReversion" (Abu-Ishak/systematic-regime-backtesting,
strategies/freqtrade/kalman_zscore_reversion.py, Freqtrade 15m, README: OOS CAGR -8.75% Sharpe -0.67 on a simulated
4h series), opened 28 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak
ideas too. Fake money only.

On closed 15m bars: a 1D Kalman filter (process var 1e-4, obs var 1e-2) tracks the close, z = (close - filter) / the
48-bar std of that spread, ADX14 (Wilder, as talib). z < -2 and ADX < 25 -> long, z > 2 and ADX < 25 -> short, at the
next open. Exit: a close with z >= -0.1 (long) or <= 0.1 (short) closes at the next open; inside each bar a -2.5% stop
(checked first) and a take profit of +3% in the first 60 min, +1.5% after (minimal_roi); gap through the stop fills at
the open. One position per coin, 1/6 of the start per coin, 0.35% per side.
  state_fwd_kalmanz.json       BTC ETH SOL AVAX LINK BNB (the repo's pairs)
  state_fwd_kalmanz_twin.json  control: random entry times (1 in 120 free bars), random side, same exits
  python3 fwd_kalmanz.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                 # per side, as every account here
M15, HOUR = 15 * 60 * 1000, 3600 * 1000
KQ, KR, SN, AN = 1e-4, 1e-2, 48, 14                  # from the strategy file (kalman_filter_1d defaults, rolling 48, ADX 14)
ZIN, ZOUT, AMAX = 2.0, 0.1, 25.0                     # from the strategy file (entry |z| > 2, exit z back to -0.1 / 0.1, ADX < 25)
STOP, ROI0, ROI60 = 0.025, 0.03, 0.015               # from the strategy file (stoploss -0.025, minimal_roi 0: 3%, 60: 1.5%)
WARM = 300                    # my choice: no signal before bar 300 of the fetched window so the filter and ADX have settled
TWIN_P = 1 / 120              # my choice: about as often as the rule fires per coin (backtest 551 to 610 trades a year)
# my choices: Binance spot instead of a futures exchange, taker fills at the next 15m open, no leverage, the ROI step
# measured from the entry bar's open time, stop and ROI checked against bar high and low, stop before ROI
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT", "BNBUSDT"]
LABEL = ("Kalman z-score สวนกลับ 15 นาที (Abu-Ishak) 6 เหรียญ: ราคาห่างเส้น Kalman เกิน 2 SD และ ADX ต่ำกว่า 25 "
         "สวนกลับ ออกเมื่อ z กลับใกล้ 0 stop -2.5% เป้า 3% แล้ว 1.5% หลัง 1 ชม. (backtest Binance 15 นาที 365 วัน "
         "หลังหัก 0.35%/ข้าง 546 ถึง 610 ไม้ต่อเหรียญ -0.69% ถึง -0.79% ต่อไม้ ก่อนหัก -0.09% ถึง +0.01% ชนะ 64 ถึง 67% "
         "ตัวแฝดเข้าสุ่ม -0.64 ถึง -0.72% permutation 200 รอบ BTC ETH SOL p 0.40 0.82 0.56 ไม่ผ่าน)")
ACCOUNTS = {"state_fwd_kalmanz.json": ("rule", LABEL),
            "state_fwd_kalmanz_twin.json": ("random", "Kalman z-score ตัวควบคุม: เข้าสุ่มเวลา สุ่มฝั่ง ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="15m"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ind(b):   # same as the scout's /tmp/scout_0101/kz.py ind()
    n, c = len(b), [x["c"] for x in b]
    kf, xh, p = [0.0] * n, c[0], 1.0
    for i in range(n):
        pp = p + KQ
        g = pp / (pp + KR)
        xh += g * (c[i] - xh)
        p = (1 - g) * pp
        kf[i] = xh
    sp = [c[i] - kf[i] for i in range(n)]
    z = [None] * n
    for i in range(SN - 1, n):
        w = sp[i - SN + 1:i + 1]
        m = sum(w) / SN
        sd = (sum((v - m) ** 2 for v in w) / (SN - 1)) ** 0.5   # pandas rolling std, ddof 1
        z[i] = sp[i] / sd if sd > 0 else None
    adx, trs, pdm, mdm, dxs, a = [None] * n, 0.0, 0.0, 0.0, [], None
    for i in range(1, n):
        h, l, pc = b[i]["h"], b[i]["l"], c[i - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up, dn = h - b[i - 1]["h"], b[i - 1]["l"] - l
        pd, md = (up if up > dn and up > 0 else 0.0), (dn if dn > up and dn > 0 else 0.0)
        if i <= AN:
            trs += tr; pdm += pd; mdm += md
            if i < AN:
                continue
        else:
            trs += tr - trs / AN; pdm += pd - pdm / AN; mdm += md - mdm / AN
        pdi, mdi = (100 * pdm / trs, 100 * mdm / trs) if trs else (0, 0)
        dx = 100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else 0
        if a is None:
            dxs.append(dx)
            if len(dxs) == AN:
                a = sum(dxs) / AN
        else:
            a = (a * (AN - 1) + dx) / AN
        adx[i] = a
    return z, adx


def signal(i, I):
    z, adx = I
    if i < WARM or z[i] is None or adx[i] is None or adx[i] >= AMAX:
        return 0
    return 1 if z[i] < -ZIN else -1 if z[i] > ZIN else 0


def exit_px(b, j, I, d, e, entry_t):
    """price and reason if the position (direction d, entry e at the open of the bar starting entry_t) closes in bar j."""
    z, x = I[0], b[j]
    if x["t"] > entry_t and z[j - 1] is not None and (z[j - 1] >= -ZOUT if d > 0 else z[j - 1] <= ZOUT):
        return x["o"], "z กลับสู่สมดุล"
    roi = ROI0 if x["t"] - entry_t < HOUR else ROI60
    sl, tg = e * (1 - d * STOP), e * (1 + d * roi)
    if d > 0:
        if x["o"] <= sl: return x["o"], "stop"
        if x["l"] <= sl: return sl, "stop"
        if x["h"] >= tg: return max(tg, x["o"]), "ถึงเป้า ROI"
    else:
        if x["o"] >= sl: return x["o"], "stop"
        if x["h"] >= sl: return sl, "stop"
        if x["l"] <= tg: return min(tg, x["o"]), "ถึงเป้า ROI"
    return None, None


def close(s, sym, px, t, why):
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
    I = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < 1:
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            px, why = exit_px(bars, i, I, p["d"], p["entry"], p["entry_t"])
            if px is not None:
                close(s, sym, px, x["t"] + M15, why)   # the strategy may open again on the exit bar's close
        if sym in s["pos"]:
            continue
        if mode == "rule":
            d = signal(i, I)
        else:
            d = rng.choice((1, -1)) if i >= WARM and rng.random() < TWIN_P else 0
        usd = s["start_usd"] / len(SYMS)
        if not d or (d > 0 and s["cash"] < usd * (1 + COST)):
            continue
        e = bars[i + 1]["o"]
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "ห่างเส้น Kalman เกิน 2 SD ADX ต่ำ" if mode == "rule" else "สุ่มเวลา สุ่มฝั่ง"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "15m")
        except Exception as e:
            print("fwd_kalmanz fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
