Memecoin rule hunt, 26-27 Nov 2026 (Fable, paper research only)

VERDICT
Nothing passes. 240 settings were tried across 5 angles. No rule clears the bar (n >= 50, mean > +1% per trade
after costs, beats random, positive in both halves, not carried by a few trades) once an out-of-sample check is
included. Three perp rows clear the bar inside the main sample and then fail out of sample.

DATA USED
- data/grok_watch.csv: 308 Grok-mentioned coins, 5-min DexScreener snapshots, 19-22 Nov 2026.
- data/rank_hist: 3,626 GMGN top-50 snapshots, 13-26 Nov 2026, 23,513 mints. Exits scored on 5-min bars from
  Jupiter's public chart API (datapi.jup.ag), 1,049 mints with liquidity >= $30k, so dead coins still count.
- Binance USDT-M perps, 1h bars + funding, 63 memecoin symbols incl. 12 delisted, Jul 2025 - Nov 2026 (main),
  Jan - Jun 2025 (out of sample), plus 150 random non-meme alts.
- Hyperliquid: 31 memecoin perps, 1h candles + funding, about May - Nov 2026.
Costs: DEX 2%/side (0.5% when liquidity >= $1M and age > 30 d), perps 0.15%/side plus funding. Stops first.

A) DEX long, Grok-mentioned coins (48 settings): every signal -2% to -4.6% per trade; control -3.2%.
   Best: G7 first sight big pool 1h -1.97 (n 65), G5 volume surge flat price -2.45 (n 393).
B) DEX long, GMGN trending (40 settings): every signal -2.1% to -4.6%; control -4.4 to -4.9.
   Best: R4 big aged dip 4h trail -2.11 (n 126, first half -4.15), R7 very big calm -2.89 (n 1707).
   24h: R1 -5.85 vs control -11.93.
C) Binance memecoin perps (46 settings): mostly within +-1%. In-sample passers:
   P1 short after 7d run-up >= +100%, 72h sl25: n 111 +4.58
   P3 short after funding >= 0.10%, 72h sl15: n 447 +1.20
   C3c funding >= 0.10% and 24h > 0: n 323 +2.28
D) Robustness (88 settings): all three fail.
   P1: neighbours +75%/+150% negative, out of sample ex5 -3.45. Noise.
   P3: neighbours and 6 quarters positive, but Jan-Jun 2025 n 65 -4.94 (control -0.94/-2.18), non-meme alts -1.15,
       pooled about +0.4%. Mostly small Binance memes not on Hyperliquid.
   C3c: out of sample n 50 -4.11.
E) Hyperliquid memecoin perps (6 settings): funding shorts -0.7 to -1.1. "Short every meme weekly" +1.43 but random
   times make +0.84 to +1.44, day-clustered t +0.7, BTC-hedged -0.68: it is just "memes fell May-Nov".
F) LP in Grok-mentioned pools (12 settings): median -4.8%, fees about 0.1%/day vs 4-5% price bleed.

WHAT THE DATA SAYS
1. Grok-style selection (big calm pools, buy pressure) beats random by 1.3-1.8 points at 1 h and about 6 points at
   24 h, but gross edge is about +1% against a 4% round trip.
2. The money is on the sell side (early holders, insiders). Those trending coins have no perps, so we cannot short.
3. Where shorting is possible (meme perps), hype is already priced. Funding-spike short is the only one with a
   mechanism and it lost 4.9% per trade in H1 2025.

CLOSEST CANDIDATES (not an edge)
1. Funding >= 0.10% short on Binance meme perps, 72h / stop +15%: about +0.4% pooled, ~0.9 trades/day, needs fapi
   (451 on GitHub runners); Hyperliquid version negative.
2. R4 big aged dip: about +0.8% only if real cost is 0.5%/side.
3. R2/R7 very big calm pools with buy pressure: best selector, still below costs.

240 settings tried. DEX windows are short (2.2 and 14 days). Scripts and .out files in this folder.
