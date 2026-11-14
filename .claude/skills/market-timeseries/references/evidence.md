# Deep research: time-series prediction and honest backtesting (12 Nov 2026)

workflow wf_585ba873-485, 105 agents, 22 verified claims, 3 refuted

## Summary

Twenty-two verified claims point to one conclusion. Predicting short-horizon returns is very hard, and most headline results disappear once you add costs, naive baselines and multiple-testing corrections. For BTC and large crypto, time-series momentum (trend following) is the best-supported effect. One working paper and one peer-reviewed study back it, but the effect is concentrated in rising markets. Cross-sectional crypto momentum has large gross returns (2014-2018) but weak or no support once realistic costs and daily liquidation risk are included. For US stocks, pretrained time-series foundation models (Chronos, TimesFM, Moirai, LoRA-tuned TimesFM) seldom beat a random walk, always-up or AR(1) baseline in a statistically meaningful way. High-turnover daily long-short strategies built on any forecast model go to a negative Sharpe at 20 bps cost. Kronos's '93%' is a relative RankIC gain over a very low base (about 0.027), not a hit rate. The methodology a skill should enforce is well established: record the number of trials, report the Deflated Sharpe Ratio against the expected maximum Sharpe under the null, estimate PBO with CSCV, never reuse a holdout, mark positions to market at least daily, and compare every forecast with naive baselines using a Diebold-Mariano or similar test. No verified evidence covered Solana memecoins, volatility targeting, short-term reversal, order-flow signals, purged/embargoed CV, or specific Python libraries.

## Findings

1. [medium, vote 2-1 and 3-0] In crypto, time-series momentum (TSMOM, trend following) has the strongest out-of-sample support of the effects studied. It ranked among the top predictors of BTC returns in in-sample, out-of-sample and asset-allocation tests, and it held up better than cross-sectional momentum under realistic costs on large, liquid coins. It loses money in most cases when the market falls, so the edge is regime-dependent.
   Sources: https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf https://informahealthcare.com/doi/abs/10.1080/1351847X.2020.1835685

2. [medium, vote 3-0] Cross-sectional (winner-minus-loser) crypto momentum looks large in gross, in-sample results but cannot be assumed tradable. Liu, Tsyvinski & Wu found 2.5-4.1% per week long-short spreads for 1-4 week lookbacks (1,707 coins, 2014-2018, value-weighted, rebalanced weekly). Those figures are before costs, have marginal t-stats (about 2.0), come from testing 25 factors, and are significant only among above-median-size coins.
   Sources: https://www.nber.org/papers/w25882.pdf https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf

3. [high, vote 3-0] Transaction costs and path risk flip many 'significant' strategies to unprofitable. In crypto, many momentum portfolios with statistically significant positive mean returns earn insignificant or negative profits once real fees, tick sizes, slippage estimated from trade data and daily marking to market are included. In US stocks, every daily-rebalanced long-short forecast strategy (CatBoost, linear, neural nets and TSFMs alike) has a negative Sharpe at 20 bps or more. The CatBoost benchmark's mean Sharpe goes from 6.44 at 0 bps to -3.62 at 20 bps and -13.59 at 40 bps.
   Sources: https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf https://arxiv.org/html/2511.18578v1

4. [medium, vote 3-0] Backtests must check path risk, not just period returns. Marking to market only at rebalance dates seriously underestimates liquidation risk. With daily marking, many leveraged or long-short crypto momentum portfolios are wiped out. The skill should mark positions daily or intrabar and use bar high and low to detect stop, target and liquidation hits.
   Sources: https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf

5. [high, vote 3-0 (fine-tuning sub-claim 2-1)] Time-series foundation models do not meaningfully beat naive baselines on equity returns. Zero-shot Chronos and TimesFM have negative out-of-sample R² on daily US stock excess returns (Chronos-large -1.37%, TimesFM-500M -2.80%) and trail CatBoost and LightGBM (CatBoost about -0.03%). On five large US stocks, TimeGPT, TimesFM-2.5, Moirai-2.0, Chronos and Chronos-2 gain only 'small and sparse' amounts over a random walk: a one-sided Diebold-Mariano test rejects in only 2 cases (Chronos/AMZN, Moirai-2.0/GOOG). LoRA-tuned TimesFM on NASDAQ-100 and S&P 500 lowers point error compared with zero-shot but beats none of the random-walk, persistence or AR(1) baselines and shows no directional skill above the base rate at any horizon.
   Sources: https://arxiv.org/html/2511.18578v1 https://ideas.repec.org/p/arx/papers/2606.27100.html https://arxiv.org/abs/2607.12248

6. [high, vote 3-0] Directional accuracy and model rankings can mislead, so every forecast evaluation needs a naive baseline plus a significance test. A TimesFM adapter that looked about 80% accurate was matching an always-up base rate of about 0.70, and it actually scored below that rate. Pretrained TSFMs won 8 of 10 tasks against train-from-scratch neural models (NBEATS, NHITS, PatchTST, iTransformer, KAN) yet still barely beat a random walk.
   Sources: https://arxiv.org/abs/2607.12248 https://ideas.repec.org/p/arx/papers/2606.27100.html

7. [medium, vote 3-0] Kronos's widely repeated '93%' is a relative gain in RankIC (0.0267 against 0.0138 for the best TSFM; 87% against the best non-pretrained model at 0.0143), not a 93% hit rate. In absolute terms the rank correlation is very weak. The paper's 25 baselines include no random-walk, last-value, HAR-RV or buy-and-hold baseline, and its trading simulation does not state its benchmark.
   Sources: https://arxiv.org/abs/2508.02739

8. [medium, vote 3-0] Deep learning (RNN, LSTM, CNN, Transformer) does not consistently beat classical ARIMA or Random Forest for one-day-ahead equity log-return forecasts under walk-forward evaluation. Results depend on the asset, and LSTM and the Transformer are competitive only in some settings.
   Sources: https://www.mdpi.com/1911-8074/19/3/203/html

9. [high, vote 3-0] Multiple testing has to be controlled. The best Sharpe among N trials rises with N even when the true Sharpe is zero. A backtest that does not report the number of trials (and the variance of results across them) cannot be judged. The Deflated Sharpe Ratio is the Probabilistic Sharpe Ratio measured against the expected maximum Sharpe under the null: SR0 = sqrt(V[SR]) * ((1-γ)Φ⁻¹(1-1/N) + γΦ⁻¹(1-1/(N·e))). It also accounts for sample length T, skewness and kurtosis. N should be the effective number of independent trials, for example estimated by clustering correlated variants.
   Sources: https://papers.ssrn.com/abstract=2460551

10. [high, vote 3-0] A single holdout or out-of-sample split does not prevent overfitting. Reused across about 20 trials at 95% confidence, it is expected to produce about one false positive (64% chance of at least one if the trials are independent). It also ignores how many configurations were tried, and it is too noisy below about 1,000 observations (for example under 20 years of weekly data). Walk-forward evaluation must be combined with trial counting and DSR or PBO, and the final holdout used once.
   Sources: https://papers.ssrn.com/abstract=2460551 https://papers.ssrn.com/abstract=2326253

11. [high, vote 3-0] Recipe for the probability of backtest overfitting (PBO) using CSCV. Build a T×N matrix of returns, one column per trial configuration. Split the rows into S blocks (S=16 recommended, roughly quarterly blocks for 4 years of daily data). For each of the C(16,8)=12,870 half/half in-sample and out-of-sample combinations, find the best in-sample configuration and its out-of-sample rank. PBO is the share of combinations where that configuration falls below the out-of-sample median (logit ≤ 0). The customary rule rejects a strategy if PBO > 0.05.
   Sources: https://papers.ssrn.com/abstract=2326253


## Caveats

Source access: both crypto momentum findings rest on Han, Kang & Ryu, an AUT/SSRN working paper whose full text returned 403. Only the abstract and search snippets were checked, so its exact universe, costs and holding periods are unverified. Cheah et al. was likewise abstract-only, with a pre-2020 sample. The TSFM evidence (arXiv 2511.18578, 2606.27100, 2607.12248) is all recent and not peer reviewed, and it covers US equities only, mostly at the daily horizon. Applying it to crypto or intraday data is an inference. The Kronos critique relies on the authors' own tables, and no independent replication exists. The ARIMA/RF-versus-DL result comes from one MDPI paper on 6 volatile tech stocks. Coverage gaps: no verified claim covers Solana memecoins, short-term reversal, volatility targeting, volume or order-flow signals, purged or embargoed k-fold CV, survivorship-bias magnitudes, fat-tail handling beyond DSR's skew and kurtosis terms, intrabar stop/target ordering rules, or open-source libraries. The skill should treat those parts as design choices, not evidence-backed. Refuted during verification: that crypto momentum exists only in large coins and so cannot work for memecoins (0-3); that the NBER robustness check was only a BTC short (0-3); and a blanket 'any daily equity signal is modest and survives only strict leakage controls' (1-2). Time sensitivity: crypto momentum evidence comes mainly from 2014-2024 samples dominated by bull markets, and the PBO typo (12,780 versus 12,870) also appears in secondary sources.

## Open questions

- Does time-series momentum on BTC and large coins still beat buy-and-hold after realistic Binance TH fees and slippage, out of sample after 2022, and especially through bear regimes where the evidence says it loses?

- Is there any credible out-of-sample, after-cost evidence for signals on Solana memecoins (GeckoTerminal-scale microcaps), given extreme survivorship bias, rug pulls and thin liquidity?

- Does volatility targeting or position sizing improve risk-adjusted trend-following returns in crypto after costs, and how much does it cut liquidation and path risk?

- Which plain-Python implementations (for example, packages for DSR, PBO/CSCV, purged CV and Diebold-Mariano tests) are reliable enough to use directly, and which should the skill implement itself?


## Refuted

- (0-3) The reported long-short factor returns are gross. They do not account for trading costs or whether the coins can be shorted, so they say nothing about profitability after costs. The authors' only robustness check was shorting Bitcoin instead of the short quintile.

- (0-3) Crypto momentum lives only in larger coins. Below-median-size coins show an insignificant 0.6% weekly momentum return, while above-median coins show a significant 4.2% weekly. Momentum signals are therefore unlikely to work in micro-cap or memecoin universes.

- (1-2) Any predictive signal in daily equity returns is modest, and it only holds up under strict leakage controls and realistic evaluation protocols.
