# Polymarket wallets to copy (23 Nov 2026, polymarket.py)

Paper money only. Accounts: state_poly_copy.json (copy) and state_poly_twin.json (random control). polymarket.py reads the
addresses from the lines below that start with `- 0x... |`. Changing this list changes the running account's rules, so per
AGENT_RULES a new list should get a new account file instead.

## Selection rule (fixed before looking at results; `python3 polymarket.py pick` reruns it)
1. Candidates: top 1000 of the all-time PnL leaderboard (`/v2/leaderboard?time_period=all&sort_by=PNL&limit=1000`).
2. Many markets: `/v2/user-stats` field `trades` (distinct-market count, per the v1-to-v2 migration doc) at least 1,000.
3. Long history: `join_date` at least 365 days ago.
4. Still good and still active: positive PnL on the month leaderboard (`/v2/leaderboard?user=...&time_period=month`) and a
   taker trade in the last 7 days (`/v2/trades?user=...&limit=1`).
5. Keep the 8 with the highest all-time PnL. 245 of the top 1000 passed steps 2-3. Run 23 Nov 2026 01:13 Bangkok time.

Plus bosona, the wallet from the X post, added on purpose. It fails step 3 (joined 21 May 2026, 186 days) but passes the
AGENT_RULES evidence bar (more than 30 days, more than 50 trades), so it is not marked unconfirmed.

## Wallets
- 0x2005d16a84ceefa912d4e380cd32e7ff827875ea | RN1 | rank 4 all-time PnL $13,591,486, volume $1.54B, 206,934 markets, joined 2024-12-12, month PnL $644,821
- 0x2c335066fe58fe9237c3d3dc7b275c2a034a0563 | (no name) | rank 17 PnL $6,760,260, volume $1.46B, 15,198 markets, joined 2025-10-08, month PnL $2,258,605
- 0xee00ba338c59557141789b127927a55f5cc5cea1 | S-Works | rank 37 PnL $3,811,894, volume $231M, 7,885 markets, joined 2024-08-13, month PnL $389,080
- 0xd38b71f3e8ed1af71983e5c309eac3dfa9b35029 | primm | rank 41 PnL $3,653,675, volume $63.7M, 5,302 markets, joined 2025-08-23, month PnL $378,347
- 0x44c1dfe43260c94ed4f1d00de2e1f80fb113ebc1 | aenews2 | rank 58 PnL $2,623,591, volume $259M, 3,370 markets, joined 2024-01-14, month PnL $235,928
- 0x9d84ce0306f8551e02efef1680475fc0f1dc1344 | ImJustKen | rank 64 PnL $2,363,465, volume $502M, 9,901 markets, joined 2022-01-19, month PnL $80,449
- 0x83720820a8aa6c3f20ad71850e7a1a17d16c5223 | Jsram | rank 77 PnL $2,139,034, volume $74.7M, 6,033 markets, joined 2024-07-23, month PnL $59,295
- 0x0c0e270cf879583d6a0142fc817e05b768d0434e | The Spirit of Ukraine>UMA | rank 83 PnL $1,997,916, volume $148M, 1,480 markets, joined 2021-08-04, month PnL $406,742
- 0xc2ad03f79ca3f3c17d8c7de2612ce0c89b7d40ed | bosona (from the X post) | rank 467 PnL $458,350, volume $32.5M, 115,864 markets, joined 2026-05-21

What the data says about bosona (from `/v2/user-stats`, 23 Nov 01:05): realized market PnL $458,291, plus $61,743 maker
rebates, $9,061 taker rebates and $4,732 rewards, minus $54,866 fees paid; economic PnL $534,101 (the post's "+$510K" is in
between). Its last 24 h of fills were all BUYs: 81 taker fills and more than 1,000 including maker fills, almost all in BTC,
ETH, SOL and BNB "Up or Down" 5-minute to daily markets. That looks like a market maker or short-horizon bot, not a picker.
We copy only its taker buys, at our ask, at least a few minutes late; in a 5-minute market that is most of the window.

## Why this may fail (written before any result)
- Copying wallets lost twice already (lessons.md 18 Nov: curve and wallets, both because we buy later than the leader).
  Polymarket polls every 5 minutes too, so fast markets (5 to 15 minute crypto up/down, live sports) are mostly gone by
  the time we see the fill. STALE_MIN 15 and MAX_CHASE 5 cents skip the worst of it.
- Most of these wallets trade huge volume (RN1 $1.5B on $13.6M PnL, under 1% of volume). Edge that thin is likely
  spread capture, rebates or size, which a late taker copy cannot get.
- We copy taker fills only (the default of `/v2/trades`), so a wallet that mostly rests limit orders gives few signals.
  Exits use every SELL fill (`taker_only=false`), so a maker sell still closes our copy.
- The order book reports `min_order_size` 5 shares; a 5% clip (about $0.74) is below that at most prices. Paper ignores
  the minimum; a real copy would need a bigger clip.

## Pass / dead (same as AGENT_RULES)
Dead at 20 closed trades if the average per trade is not above the twin. Pass at 50 closed trades, positive after costs,
above the twin, and still positive with the best trade removed. Compare per-trade averages (`python3 polymarket.py status`),
not account totals.

## Endpoints used (all public, no auth; each checked with curl on 23 Nov 2026)
Data API spec https://data-api.polymarket.com/v2/openapi.json, v2 contract https://docs.polymarket.com/migrate/data-api-v1-to-v2.md
- `GET https://data-api.polymarket.com/v2/leaderboard` (time_period, sort_by, limit up to 1000, user): rows rank, user_id, pnl, volume, user_name
- `GET /v2/user-stats?user=` : trades (distinct markets), join_date, all_time_pnl{...}
- `GET /v2/trades?user=&start=&side=&taker_only=&condition=` : side, token_id, condition_id, size, price, timestamp, outcome, outcome_index, title, transaction_hash. Default taker_only=true
- `GET /v2/resolutions?condition=` : status "resolved", payouts [micro-USDC per share per outcome]
Gamma spec https://docs.polymarket.com/api-spec/gamma-openapi.yaml, fields https://docs.polymarket.com/market-data/market-details.md
- `GET https://gamma-api.polymarket.com/markets?condition_ids=..&closed=any` (repeat the parameter; comma-joined returned nothing): conditionId, question, outcomes, outcomePrices, clobTokenIds, closed, acceptingOrders, enableOrderBook, endDate, feesEnabled, feeSchedule{rate, exponent}, feeType, umaResolutionStatus, events, bestAsk
- `GET /markets?closed=false&end_date_min=&end_date_max=&order=volume24hr&ascending=false&limit=100&offset=` for the twin (limit is capped at 100)
- `GET /public-search?q=bosona&search_profiles=true` found bosona's wallet (one-off, not used by the script)
CLOB spec https://docs.polymarket.com/api-spec/clob-openapi.yaml
- `POST https://clob.polymarket.com/books` body `[{"token_id": ...}]` (security: [] in the spec): bids, asks, min_order_size, tick_size. Unsorted; the script sorts. The documented GET /books?token_ids= answered "Invalid payload". Closed markets have no book.
Fees https://docs.polymarket.com/trading/fees.md : fee = C x feeRate x p x (1 - p), taker only; rate by category (0.05 BTC 5/15-minute, sports, finance, tech, elections, other; 0.01 other crypto, politics, economics, culture, weather, mentions; 0 geopolitics).
Resolution https://docs.polymarket.com/concepts/resolution.md : winning tokens redeem for $1, losing $0, a 50-50 resolution pays $0.50.
Rate limits https://docs.polymarket.com/api-reference/rate-limits.md : /v2/trades 300 per 10 s, all /v2 800 per 10 s, Gamma 4,000 per 10 s.
