#!/usr/bin/env python3
"""Offline check for grokwatch.py: mints come from LTRADE / VETO / SEEN lines only, deepest pool wins."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grokwatch as g
A, B = "9hjBLBrc7WZW2H8UQvBAvG5WiTZotXUv2Bdcn4f4pump", "DtcicPCKTKeAh7TDEzTym3hXeoHAoMiBdYJhMYxZpump"
txt = (f"LTRADE S8 BUY DCTY {A} price=0.02 reason=x\nVETO c17 REJECT {B} reason=y\nSEEN S8 FOO {A} liq=1 skip=z\n"
       "LEDGER S8 20:51 cash=1 open=DCTY:0.02\nVETO <id> APPROVE|REJECT <mint> reason=prompt text")
assert g.mints(txt) == [A, B], g.mints(txt)
pair = lambda liq, px: dict(baseToken=dict(address=A, symbol="DCTY"), priceUsd=px, liquidity=dict(usd=liq), txns=dict(m5=dict(buys=3, sells=1)))
r = g.deepest([pair(100, "1"), pair(900, "2"), dict(baseToken=dict(address="X"), priceUsd="9")], {A}, 5)
assert list(r) == [A] and r[A]["price"] == "2" and r[A]["buys_m5"] == 3 and r[A]["vol_h1"] is None, r
print("grokwatch ok")
