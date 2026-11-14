# PaperTrade cloud (fake money only)

Paper-trading experiments that test claims from X posts about AI memecoin bots, plus plain DCA and trend-following baselines.
**No real money, no wallet, no private keys, no orders.** Every "buy" and "sell" is a JSON entry priced from public APIs
(DexScreener, GMGN read-only demo key, Helius RPC, Binance TH, Yahoo).

Runs on GitHub Actions every ~5 minutes (`cloud.sh`), committing the state files back.

| Account | File | Rules |
|---|---|---|
| X-post recipes (insider, grad, smart4) | `state_recipe_*.json` | `recipes.py`, `RULES_AGENTS.md` |
| Copy 10 smart wallets via Helius | `state_wallets.json` | `wallets.py` |
| Same wallets, tokens still on the pump.fun bonding curve (priced from the curve account) | `state_curve.json` | `curve.py`, `RULES_AGENTS.md` |
| Nightly sessions (safe, runner, apple): fresh 500 THB every 21:00, settle 09:00, one result per night | `state_night_*.json` | `nightly.py` (`python3 nightly.py report`) |
| Trend following, 5 coins | `state.json` | `paper.py`, `RULES.md` |
| Weekly DCA BTC / VOO | `state_dca.json`, `state_stock.json` | `dca.py`, `stock.py` |

Nothing here is financial advice. So far every memecoin recipe is losing after fees.
