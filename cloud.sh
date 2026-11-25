#!/bin/bash
# GitHub Actions entry (every ~5 min). Paper money only: no wallet, no keys that can trade, no orders anywhere.
cd "$(dirname "$0")" || exit 1
PY=python3
T0=$(date +%s)
M=$((10#$(date +%M)))
$PY zoo.py watch 900 & WATCH=$!   # 20-second exit checks for the zoo's FAST accounts while the rest of this run works
$PY zoo.py watch 900 5 & WATCH5=$!   # 5-second checks for recipes with WATCH_S=5 (same rules as a 20 s twin, faster stops)
# fast multi-agent account (laya DEBATE), moved from the Mac 14 Nov; its scan saves the ranking the recipes/zoo read
$PY agents.py scan || $PY rankfetch.py || echo "rank fetch failed (GMGN demo key may be rate-limited)"
$PY agents.py run
for p in hype runner nolaya apple; do $PY hype.py --profile $p mirror; $PY hype.py --profile $p run; done   # mirror accounts
# v2 + ghost tracker (was the Mac's auto.sh): exits every run, ghost ~every 15 min, rule scan + laya judge once an hour
[ "$($PY -c "import json;print(len(json.load(open('state_grok_v2.json'))['pos']))" 2>/dev/null || echo 0)" -gt 0 ] && $PY grok.py run
[ $((M % 15)) -lt 5 ] && $PY grok.py ghost
HOUR=$(date -u +%FT%H)
if [ "$M" -lt 15 ] && [ "$(cat data/last_v2scan 2>/dev/null)" != "$HOUR" ]; then
  echo "$HOUR" > data/last_v2scan
  out=$($PY grok.py scan 2>&1); echo "$out" | grep -E "กรรมการ|ผ่านทุกข้อ|ข้าม"
  for m in $(echo "$out" | grep -o ' mint [A-Za-z0-9]*' | awk '{print $2}'); do $PY grok.py buy "$m" "auto: ผ่านกฎ+กรรมการ laya"; done
fi
for r in insider grad smart4; do $PY recipes.py $r scan; $PY recipes.py $r run; done
$PY wallets.py poll; $PY wallets.py run
[ -f state_wallets_fomo.json ] || WALLET_LIST=fomo $PY wallets.py init 500 >/dev/null; WALLET_LIST=fomo $PY wallets.py poll; WALLET_LIST=fomo $PY wallets.py run   # Fomo 30d leaderboard wallets (22 Nov)
[ -f state_wallets_fomo_mirror.json ] || WALLET_LIST=fomo_mirror $PY wallets.py init 500 >/dev/null; WALLET_LIST=fomo_mirror $PY wallets.py poll; WALLET_LIST=fomo_mirror $PY wallets.py run   # savipww copy rules: exit when the leader sells
$PY curve.py run || echo "curve run failed"   # pump.fun curve child of wallets.py: acts on the skips wallets.py just logged
$PY zoo.py init 500 >/dev/null; $PY zoo.py tick       # init only creates new accounts (X recipes added by the routine); strategy zoo: ~20 one-rule accounts on the same ranking
$PY nightly.py tick    # nightly sessions: fresh 500 THB at 21:00, settle at 09:00
$PY funding.py init 10000 >/dev/null; $PY funding.py run || echo "funding run failed (Hyperliquid API)"   # funding carry: steps once a day, no network otherwise
$PY daytrade.py init 500 >/dev/null; $PY daytrade.py run || echo "daytrade run failed"   # one-day accounts on big coins: grid, dip, funding spike
$PY byttrade.py run || echo "byttrade run failed"   # SOL/ETH/BTC 4h byttrade st4h_ema50_1d + twin (23 Nov), acts once per closed 4h bar
$PY pullback.py || echo "pullback run failed"   # trend_pullback_champion BTC/ETH/SOL 4h + twin (23 Nov, weak backtest, opened to try)
$PY twocandle.py || echo "twocandle run failed"   # RohOnChain 2-candle forward (lost in backtest, opened to try)
$PY dxai.py || echo "dxai run failed"   # arXiv 2609.05663 DXAI: top-3 24h gainer chase + 2%/4% bracket 1h + random twin (23 Nov, backtest lost, opened to try)
for f in fwd_*.py; do [ -f "$f" ] && { timeout 90 $PY "$f" || echo "$f failed"; }; done   # live accounts the scout writes itself (RESEARCH.md)
$PY crash.py init 500 >/dev/null; $PY crash.py run || echo "crash run failed"   # Fable perp accounts (19 Nov): crash-day bounce, night crash short, new-listing short
$PY grokwatch.py || echo "grokwatch failed"   # 19-20 Nov: 5-min DexScreener log of every mint the Grok Bot routines mention, 24 h each
$PY polymarket.py run || echo "polymarket run failed"   # copy top Polymarket wallets + random twin (23 Nov)
$PY poly_arb.py run || echo "poly_arb run failed"   # Polymarket YES+NO pair under 1 after fees (jbfly46 idea, 23 Nov), ~11 s
$PY poly_weather.py run || echo "poly_weather run failed"   # daily temperature buckets vs Open-Meteo + random-bucket twin (23 Nov); buy scan every 3 h (~30 s), settle every run
$PY poly_fav.py run || echo "poly_fav run failed"   # favourite-longshot bias: fav 0.85-0.97 / long 0.03-0.10 ending within 48 h + random-side twin (23 Nov), ~12 s
$PY poly_fav_twin2.py || echo "poly_fav_twin2 failed"   # second random-side control for poly_fav (first twin ran out of cash 25 Nov)
$PY poly_fav_mid.py run || echo "poly_fav_mid run failed"   # mid favourites 0.60-0.85 / mid dogs 0.15-0.40 + twin (23 Nov), ~12 s
$PY poly_fav_sport.py run || echo "poly_fav_sport run failed"   # same as mid, sports feeType only + dog + twin (24 Nov)
$PY poly_fav_exact.py run || echo "poly_fav_exact run failed"   # exact-score No 0.85-0.97 + Yes control + twin (24 Nov), ~12 s
$PY poly_fav_sure.py run || echo "poly_fav_sure run failed"   # near-certain outcomes ask 0.985-0.995 + 0.005-0.015 control + twin (24 Nov), ~12 s
$PY poly_fav_weather.py run || echo "poly_fav_weather run failed"   # temperature buckets, side 0.60-0.93 + 0.15-0.40 control + twin (24 Nov), ~12 s
$PY poly_fav_mention.py run || echo "poly_fav_mention run failed"   # mention markets, side 0.70-0.95 + 0.05-0.30 control + twin (24 Nov), ~12 s
$PY poly_updown.py run || echo "poly_updown run failed"   # crypto Up or Down vs a Binance random-walk model + twin (23 Nov), ~5 s
$PY kalshi_fav.py run || echo "kalshi_fav run failed"   # Kalshi favourites 0.85-0.97 / longshots 0.03-0.10 + twin (23 Nov), ~10 s
left=$((T0 + 230 - $(date +%s))); [ "$left" -gt 0 ] && sleep "$left"   # watcher keeps checking here instead of the chain step idling
$PY zoo.py stopwatch; wait $WATCH $WATCH5
TODAY=$(TZ=Asia/Bangkok date +%F); H=$((10#$(TZ=Asia/Bangkok date +%H)))
if [ "$H" -ge 8 ] && [ "$(cat data/last_daily 2>/dev/null)" != "$TODAY" ]; then
  $PY paper.py run; $PY dca.py run; $PY stock.py run; $PY majors.py run; echo "$TODAY" > data/last_daily
fi
$PY tools/review.py . --json > data/board.json.tmp && mv data/board.json.tmp data/board.json && $PY tools/board_extra.py || { rm -f data/board.json.tmp; echo "board failed"; }   # status board for the live page (+ weekly DCA, 100k trend)
