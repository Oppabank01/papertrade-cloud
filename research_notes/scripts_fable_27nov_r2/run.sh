#!/bin/bash
# usage: ./run.sh <seconds> script.py [args]  -> 1.5 GB RAM cap (ramguard) + hard timeout (no coreutils timeout on this Mac)
S=$1; shift
exec ~/.claude/scripts/ramguard.sh 1.5 perl -e 'alarm shift; exec @ARGV' "$S" python3 "$@"
