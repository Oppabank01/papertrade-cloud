#!/bin/bash
# Mac-only scout (launchd com.oppabank.scout, every 90 min): headless Claude runs RESEARCH.md, then this wrapper pushes.
# Claude never sees the GitHub token; it only commits locally.
# Runs in its own git worktree (../PaperTrade-scout) so the 2-minute news job's pulls never touch its files.
cd "$(dirname "$0")/../PaperTrade-scout" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin" CLAUDE_CONFIG_DIR="$HOME/.claude-thanabank"
git rebase --abort 2>/dev/null; git fetch -q origin; git log origin/main..HEAD --oneline 2>/dev/null | grep -q . && git branch -f "unpushed-$(date +%m%d%H%M)" HEAD; git checkout -q -B scout origin/main 2>/dev/null; git reset -q --hard origin/main || { echo "worktree reset failed"; exit 1; }   # scout worktree only
[ -f data/research_feed.json ] || echo "[]" > data/research_feed.json
perl -e 'alarm 3000; exec @ARGV' claude -p "$(cat RESEARCH.md) Today (Bangkok): $(TZ=Asia/Bangkok date '+%F %H:%M')." \
  --model claude-opus-5-5 --effort high --max-turns 80 \
  --allowedTools "Read,Edit,Write,Glob,Grep,WebSearch,WebFetch,Bash(python3:*),Bash(node:*),Bash(gh api:*),Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git add:*),Bash(git checkout:*),Bash(git -c:*),Bash(ls:*),Bash(cat:*),Bash(head:*),Bash(tail:*),Bash(wc:*),Bash(jq:*),Bash(date:*)" \
  --disallowedTools "Bash(curl:*),Bash(npm:*),Bash(pip:*),Bash(git push:*),Bash(git clone:*)" | tail -5
git log origin/main..HEAD --oneline | grep -q . || exit 0
# guard for scout-written live accounts: tests must pass, no shell/network calls, only state_fwd_* files, max 2 per run
for f in $(git diff --name-only --diff-filter=A origin/main..HEAD | grep -E '^fwd_[a-z0-9_]+\.py$'); do
  t="test_$f"; bad=""
  [ -f "$t" ] || bad="no test"
  grep -nE 'subprocess|os\.system|eval\(|exec\(|socket|urllib|__import__' "$f" "$t" 2>/dev/null | grep -q . && bad="forbidden call"
  grep -oE 'state_[a-z0-9_]+\.json' "$f" | grep -vq '^state_fwd_' && bad="touches other accounts"
  [ -z "$bad" ] && ! perl -e 'alarm 300; exec @ARGV' /usr/bin/python3 "$t" >/dev/null 2>&1 && bad="test failed"
  [ "$(git diff --name-only --diff-filter=A origin/main..HEAD | grep -cE '^fwd_')" -gt 2 ] && bad="more than 2 new"
  if [ -n "$bad" ]; then echo "dropping $f: $bad"; git rm -q -f "$f" "$t" 2>/dev/null; git -c user.name=papertrade-bot -c user.email=papertrade-bot@users.noreply.github.com commit -qm "scout guard: drop $f ($bad)"; fi
done
URL="https://x-access-token:$(gh auth token -u Oppabank01)@github.com/Oppabank01/papertrade-cloud.git"
for i in 1 2 3; do
  if ! git pull -q --rebase origin main; then   # the main thread may have edited the feed meanwhile: keep both sides
    if [ "$(git diff --name-only --diff-filter=U)" = "data/research_feed.json" ]; then
      /usr/bin/python3 tools/feed_merge.py && git add data/research_feed.json && GIT_EDITOR=true git rebase --continue || git rebase --abort
    else git rebase --abort; fi
  fi
  git push -q "$URL" HEAD:main 2>/dev/null && exit 0; echo "push failed ($i)"; sleep 5
done
