#!/bin/bash
# GitHub Actions entry (every ~5 min). Paper money only: no wallet, no keys that can trade, no orders anywhere.
cd "$(dirname "$0")" || exit 1
PY=python3
T0=$(date +%s)
M=$((10#$(date +%M)))
$PY zoo.py watch 900 & WATCH=$!   # 20-second exit checks for the zoo's FAST accounts while the rest of this run works
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
$PY zoo.py init 500 >/dev/null; $PY zoo.py tick       # init only creates new accounts (X recipes added by the routine); strategy zoo: ~20 one-rule accounts on the same ranking
$PY nightly.py tick    # nightly sessions: fresh 500 THB at 21:00, settle at 09:00
$PY funding.py run || echo "funding run failed (Hyperliquid API)"   # funding carry: steps once a day, no network otherwise
left=$((T0 + 230 - $(date +%s))); [ "$left" -gt 0 ] && sleep "$left"   # watcher keeps checking here instead of the chain step idling
$PY zoo.py stopwatch; wait $WATCH
TODAY=$(TZ=Asia/Bangkok date +%F); H=$((10#$(TZ=Asia/Bangkok date +%H)))
if [ "$H" -ge 8 ] && [ "$(cat data/last_daily 2>/dev/null)" != "$TODAY" ]; then
  $PY paper.py run; $PY dca.py run; $PY stock.py run; $PY majors.py run; echo "$TODAY" > data/last_daily
fi
