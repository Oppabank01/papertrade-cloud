# Fable research round 1 (19 Nov 2026), Binance perp 1h data 2022-01 to 2026-11, delisted coins included

Split: in-sample 2024-01..2025-09, out-of-sample (OOS) 2025-10..2026-11, holdout 2022-23. Costs 0.15%/side majors,
0.25% alts, funding included; "x2" = costs doubled. Signal on closed bar, fill next bar open. Scripts were in the
session scratchpad (not kept in the repo).

| Rule | 2022 | 2023 | IS | OOS | OOS x2 | verdict |
|---|---|---|---|---|---|---|
| M1 crash-day alt bounce (coin 24h <= -15%, BTC 24h <= -5%), hold 24h | +3.59% (102) | +5.32% (23) | +4.42% (106) | +2.27% (47) | +1.77% | pass, ~17 crash days/yr, needs fill within the hour |
| M2 same, hold 72h | +2.18% | +7.82% | +3.89% | +6.88% (43) | +6.39% | pass, 2022 drawdown -51% |
| M3 long BTC / short top-30 alts weekly | +0.14% | -0.10% | +0.40% | +0.26% | +0.24% | weak, regime bet |
| M4 short new listings day 1-31, stop +50% | - | - | +1.09% (315) | +11.26% (111) | +10.66% | in-sample ~0 |
| M5 7d trend vol-targeted weekly | -0.03% | +0.08% | +0.18% | +0.42% | +0.31% | weak |

One night (21:00-09:00 Bangkok): 55 rules on 1,022 nights, none positive OOS at doubled cost. Hold BTC every night
OOS -0.375%/night (39% green). Nearest: N1 short top-30 coins down 10%+ in 6h at 21:00: 2022-23 +1.49%/night,
IS +1.27%, OOS -0.015%.

Opened as 500 THB paper accounts on Hyperliquid prices (crash.py): M1, M2, N1, M4. Hyperliquid's coin list and prices
differ from Binance, so these are the live check of the backtest, not a copy of it.
