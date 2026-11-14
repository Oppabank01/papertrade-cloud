---
name: market-timeseries
description: Honest backtests and forecast-claim checks for price time series (BTC/crypto from Binance, US stocks/ETFs from Yahoo, Solana memecoins from GeckoTerminal). Use when testing a trading rule, comparing stop/target settings, judging a claimed win rate or "AI predicts the market" post, or deciding whether a strategy beats buy-and-hold after costs. Not for live trading.
---

# market-timeseries

Goal: tell the user whether a trading idea or forecast claim survives costs, baselines and multiple testing. Default to "not proven". Never place orders.

## What the evidence says (details and sources: references/evidence.md)

- Short-horizon returns are close to unpredictable. Most headline results disappear after costs, naive baselines and multiple-testing corrections.
- Time-series momentum (trend following) on BTC and large coins has the best support, but it earns mainly by sidestepping bear markets and lags buy-and-hold in strong bull runs. Cross-sectional crypto momentum is large before costs and weak after them.
- Time-series foundation models (Chronos, TimesFM, Moirai, Kronos) rarely beat a random walk on equity returns. Kronos's "93%" is a relative rank-correlation gain from about 0.014 to 0.027, not a hit rate.
- Daily-rebalanced long-short strategies built on any forecast model go to a negative Sharpe at 20 bps cost.
- No verified evidence covers memecoin signals, volatility targeting, short-term reversal or order flow. Treat these as untested.

## Rules for every evaluation

1. **Costs are mandatory.** Include fee and slippage per side. Defaults: Binance TH 0.25% + 0.1%, memecoin bot 1% + 1%, US broker about 0.1%.
2. **Always show the baseline next to the result.** Use buy-and-hold for rules. Use zero/random walk, persistence and always-guess-the-majority-direction for forecasts.
3. **Count trials.** Report how many configurations were tried, including earlier sessions (`mts.py` keeps `~/.cache/market-timeseries/trials.jsonl`), plus the Deflated Sharpe Ratio and PBO. If PBO is above 0.05, the in-sample winner is not reliable.
4. **Walk forward and touch the holdout once.** Choose on the early part, then test on the later part. A holdout reused across many tries stops being out of sample.
5. **Report the tails honestly.** Give the mean, median, the mean without the best 1%, the win rate and a CI. If the mean is positive but the median is negative, a few lucky trades are carrying the result.
6. **Use path, not just endpoints.** Exits use bar high and low. When one bar touches both the stop and the target, count it as the stop. When price gaps through the stop, fill at the open. Mark to market every bar.
7. **Watch for survivorship.** Coins or stocks picked because they are listed or trending today make the past look better. Say so whenever the universe was picked today.
8. **Check regimes.** Break results down by year or by bull and bear market. One regime is not evidence.
9. **Never tune numbers on a live paper experiment.** A changed rule set is a new version with a fresh count.

## Commands (`scripts/mts.py`, standard library only)

```bash
S=.claude/skills/market-timeseries/scripts
python3 $S/mts.py data binance BTCUSDT 1d                 # cache bars (binance | binanceth | yahoo | gecko)
python3 $S/mts.py trend binance BTCUSDT                   # tsmom/sma/breakout x 5 lookbacks vs B&H, DSR, PBO, walk-forward, by year
python3 $S/mts.py trend yahoo SPY --cost 0.001
python3 $S/mts.py bracket gecko MINT1,MINT2 --stops -0.08,-0.25 --targets 0.2,1.0   # stop/target grid on 15m candles
python3 $S/mts.py forecast preds.csv                      # columns actual,pred: MAE vs baselines, Diebold-Mariano, hit rate vs base rate
python3 $S/test_mts.py                                    # offline self-check
```

For a custom rule, import `stats.py` (`psr`, `dsr`, `pbo`, `trade_summary`, `dm_test`, `max_drawdown`) and `mts.bars` / `mts.strat_returns`. Do not write a new metric when one exists here.

## Checking a claim from a post or video

1. Restate the claim as a testable number: what was traded, over what period, after what costs, compared with what.
2. Ask for or find the evidence: a broker statement, a public wallet or on-chain trades, a repo with a backtest. Screenshots and "no screenshots to verify" are not evidence.
3. Run the closest version with `mts.py`, using random or naive entries as the baseline. If a random entry with the same stop/target gets close, the claimed edge comes from luck or selection.
4. Give a verdict: **supported**, **not proven**, or **contradicted**, with the numbers.

## Report shape

The baseline goes next to every figure. Then: trials and DSR/PBO, out-of-sample result, the year or regime table, and a one-line verdict. Keep the user's language. No hype words.
