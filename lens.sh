#!/bin/bash
# Mac-only runner for lens.py (launchd com.oppabank.lens, every hour). Pushes only the lens files,
# as papertrade-bot with the Oppabank01 token, so the cloud page can show them.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin"
FILES="state_lens_rule.json state_lens_neon.json state_lens_rand.json data/lens_seen.json data/lens_log.jsonl"
git pull -q --rebase --autostash origin main || echo "pull failed"
/usr/bin/python3 lens.py
for f in $FILES; do [ -e "$f" ] && git add -A -- "$f"; done   # a missing path would make git add skip everything
git diff --cached --quiet && exit 0
git -c user.name=papertrade-bot -c user.email=papertrade-bot@users.noreply.github.com commit -q -m "lens $(date -u +%FT%TZ)"
URL="https://x-access-token:$(gh auth token -u Oppabank01)@github.com/Oppabank01/papertrade-cloud.git"
for i in 1 2 3; do git pull -q --rebase --autostash origin main && git push -q "$URL" HEAD:main 2>/dev/null && exit 0; echo "push failed ($i)"; sleep 5; done
