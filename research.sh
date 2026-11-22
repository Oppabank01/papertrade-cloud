#!/bin/bash
# Mac-only scout (launchd com.oppabank.scout, every 3 h): headless Claude runs RESEARCH.md, then this wrapper pushes.
# Claude never sees the GitHub token; it only commits locally.
# Runs in its own git worktree (../PaperTrade-scout) so the 2-minute news job's pulls never touch its files.
cd "$(dirname "$0")/../PaperTrade-scout" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin" CLAUDE_CONFIG_DIR="$HOME/.claude-thanabank"
git fetch -q origin && git checkout -q -B scout origin/main && git clean -qfd -- data x_recipes.json || { echo "worktree reset failed"; exit 1; }
[ -f data/research_feed.json ] || echo "[]" > data/research_feed.json
perl -e 'alarm 3000; exec @ARGV' claude -p "$(cat RESEARCH.md) Today (Bangkok): $(TZ=Asia/Bangkok date '+%F %H:%M')." \
  --model claude-opus-5-5 --effort high --max-turns 80 \
  --allowedTools "Read,Edit,Write,Glob,Grep,WebSearch,WebFetch,Bash(python3:*),Bash(node:*),Bash(gh api:*),Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git add:*),Bash(git checkout:*),Bash(git -c:*),Bash(ls:*),Bash(cat:*),Bash(head:*),Bash(tail:*),Bash(wc:*),Bash(jq:*),Bash(date:*)" \
  --disallowedTools "Bash(curl:*),Bash(npm:*),Bash(pip:*),Bash(git push:*),Bash(git clone:*)" | tail -5
git log origin/main..HEAD --oneline | grep -q . || exit 0
URL="https://x-access-token:$(gh auth token -u Oppabank01)@github.com/Oppabank01/papertrade-cloud.git"
for i in 1 2 3; do git pull -q --rebase origin main && git push -q "$URL" HEAD:main 2>/dev/null && exit 0; echo "push failed ($i)"; sleep 5; done
