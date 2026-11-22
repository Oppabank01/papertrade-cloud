#!/usr/bin/env python3
"""Resolve a rebase conflict on data/research_feed.json: upstream feed + the items the commit being replayed added.
Used by research.sh when the main thread edited the feed while the scout ran."""
import json, subprocess, sys

def show(rev):
    try:
        return json.loads(subprocess.check_output(["git", "show", f"{rev}:data/research_feed.json"], stderr=subprocess.DEVNULL))
    except Exception:
        return []

head = subprocess.check_output(["git", "rev-parse", "REBASE_HEAD"]).decode().strip()
up, mine, parent = show("HEAD"), show(head), show(head + "^")
old = {(x.get("title"), x.get("url")) for x in parent}
new = [x for x in mine if (x.get("title"), x.get("url")) not in old]
json.dump((up + new)[-300:], open("data/research_feed.json", "w"), ensure_ascii=False, indent=1)
print(f"feed merged: {len(up)} upstream + {len(new)} new")
