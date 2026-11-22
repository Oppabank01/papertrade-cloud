#!/bin/bash
# Mac-only runner for gnews.py (launchd com.oppabank.gnews, every 15 min). Pushes only the Gemini news files,
# as papertrade-bot with the Oppabank01 token, so the cloud page can show them.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin"
FILES="state_gnews.json state_gnews_twin.json data/gnews_log.json data/gnews_seen.json data/gnews_decisions.jsonl data/gnews_raw"
git pull -q --rebase --autostash || echo "pull failed"
/usr/bin/python3 gnews.py
for f in $FILES; do [ -e "$f" ] && git add -A -- "$f"; done   # a missing path would make git add skip everything
git diff --cached --quiet && exit 0
git -c user.name=papertrade-bot -c user.email=papertrade-bot@users.noreply.github.com commit -q -m "gnews $(date -u +%FT%TZ)"
URL="https://x-access-token:$(gh auth token -u Oppabank01)@github.com/Oppabank01/papertrade-cloud.git"
for i in 1 2 3; do git pull -q --rebase --autostash && git push -q "$URL" HEAD:main 2>/dev/null && exit 0; echo "push failed ($i)"; sleep 5; done
