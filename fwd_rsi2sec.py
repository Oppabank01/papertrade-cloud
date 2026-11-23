#!/usr/bin/env python3
"""Forward paper test of the fwd_rsi2us rule on other US equity ETFs (DIA and four sector funds), opened 23 Nov 2026. Fake money only.

Same rule and code as fwd_rsi2us (RSI(2) of the close below 5 -> buy at the next open, sell at the next open after a close above
the 5-day average or after 10 bars), on DIA XLK XLF XLE XLV, a fifth of the start each, 0.02% per side (wider spreads).
Opened as an out-of-sample check: the rule was fixed on SPY/QQQ/IWM before these were tested. Backtest 2005-2026 against
random entry days with the same exit: XLK 565 trades +0.43% vs +0.21% (p 0.003), XLV +0.28% vs +0.11% (p 0.003), XLF +0.41%
vs +0.22% (p 0.03), DIA +0.22% vs +0.12% (p 0.03), XLE +0.30% vs +0.18% (p 0.11). Also tested and left out because they are
not US equities: EFA and EEM (no edge, p 0.4 and 0.57), GLD (p 0.06), TLT (p 0.01). About 27 trades a year per ETF.
  state_fwd_rsi2sec.json        the rule
  state_fwd_rsi2sec_twin.json   control: random entry days (1 in 9 free days), same exit rule
  python3 fwd_rsi2sec.py"""
import random
import fwd_overnight as O
import fwd_rsi2us as R
from byttrade import load, save

R.SYMS = SYMS = ["DIA", "XLK", "XLF", "XLE", "XLV"]
R.COST = 0.0002
ACCOUNTS = {"state_fwd_rsi2sec.json": ("rule", "ETF หุ้นสหรัฐกลุ่มอื่น RSI(2) ต่ำกว่า 5 (DIA XLK XLF XLE XLV) กฎเดียวกับบัญชี SPY QQQ IWM ทดสอบนอกตัวอย่าง"),
            "state_fwd_rsi2sec_twin.json": ("random", "ETF หุ้นสหรัฐกลุ่มอื่น RSI(2) ตัวควบคุม: ซื้อวันสุ่ม ออกด้วยกฎเดียวกัน")}


def main():
    rng, bars = random.Random(), {}
    for sym in SYMS:
        try:
            bars[sym] = O.fetch(sym)
        except Exception as e:
            print("fwd_rsi2sec fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        for sym, b in bars.items():
            R.step(s, sym, b, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
