#!/bin/bash
# GitHub Actions entry (every ~5 min). Paper money only: no wallet, no keys that can trade, no orders anywhere.
cd "$(dirname "$0")" || exit 1
PY=python3
$PY rankfetch.py || echo "rank fetch failed (GMGN demo key may be rate-limited)"
for r in insider grad smart4; do $PY recipes.py $r scan; $PY recipes.py $r run; done
$PY wallets.py poll; $PY wallets.py run
$PY zoo.py tick       # strategy zoo: ~20 one-rule accounts on the same ranking
$PY nightly.py tick    # nightly sessions: fresh 500 THB at 21:00, settle at 09:00
TODAY=$(TZ=Asia/Bangkok date +%F); H=$((10#$(TZ=Asia/Bangkok date +%H)))
if [ "$H" -ge 8 ] && [ "$(cat data/last_daily 2>/dev/null)" != "$TODAY" ]; then
  $PY paper.py run; $PY dca.py run; $PY stock.py run; $PY majors.py run; echo "$TODAY" > data/last_daily
fi
