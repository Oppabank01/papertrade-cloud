#!/usr/bin/env python3
"""Mirror accounts (fake money): copy another account's entries, change one thing, compare.

  python3 hype.py [--profile NAME] init 500
  python3 hype.py [--profile NAME] mirror   # copy new entries from the source accounts
  python3 hype.py [--profile NAME] run      # exits
  python3 hype.py [--profile NAME] status

Profiles (13 Nov 2026):
  hype    "สายโม้": every buy of the fast-agents, Grok copy-wallet and Grok team accounts, sized like the X posts
          (40% of equity, compounding, @immortalhowwl) with winners left to run (stop -8%, trail 20% once +20%,
          @Loofyb0i "trail 20/15", 24h cap).
  runner  fast-agents buys, same 20% size as fast-agents, hype exits. Isolates "let it run" from "big size".
  apple   @crbpite8 12 Nov "$15 -> $3,171 paid my Apple Card": 60% of free cash per buy, compounding, 2 positions,
          lock profit with a 12% trail, -18% stop. Picks = every buy of the other paper accounts and recipes.
  nolaya  every coin that passed the fast-agents seats (logged as "debate"), bought whatever laya said,
          fast-agents size and exits. Isolates the laya DEBATE seat. Misses candidates seen while fast-agents was full.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import agents  # noqa: E402

HERE = Path(__file__).parent
PROFILES = {
    "hype": dict(state="state_hype.json", label="สายโม้ (ไม้ใหญ่ ปล่อยกำไรวิ่ง)", kinds=("buy",),
                 sources=("state_agents.json", "state_grokbot.json", "state_grokteam.json"),
                 PER_TRADE=0.40, MAX_POS=2, TRAIL_ON=0.20, TRAIL=0.20, MAX_HOLD_H=24),
    "runner": dict(state="state_runner.json", label="เร็ว ปล่อยกำไรวิ่ง (ไม้ 20%)", kinds=("buy",),
                   sources=("state_agents.json",), PER_TRADE=0.20, MAX_POS=4, TRAIL_ON=0.20, TRAIL=0.20, MAX_HOLD_H=24),
    "apple": dict(state="state_apple.json", label="สูตร crbpite8 Apple Card (ไม้ 60%)", kinds=("buy",),
                  sources=("state_agents.json", "state_grokbot.json", "state_grokteam.json", "../PaperTrade-cloud/state_recipe_insider.json",
                           "../PaperTrade-cloud/state_recipe_grad.json", "../PaperTrade-cloud/state_recipe_smart4.json"),
                  PER_TRADE=0.60, MAX_POS=2, TRAIL_ON=0.12, TRAIL=0.12, MAX_HOLD_H=24, STOP=-0.18),
    "nolaya": dict(state="state_nolaya.json", label="เร็ว ไม่มี laya", kinds=("debate",),
                   sources=("state_agents.json",), PER_TRADE=0.20, MAX_POS=4, TRAIL_ON=0.15, TRAIL=0.15, MAX_HOLD_H=3),
}
NAME = "hype"
if "--profile" in sys.argv:
    i = sys.argv.index("--profile")
    NAME = sys.argv[i + 1]
    del sys.argv[i:i + 2]
P = PROFILES[NAME]
agents.STATE = HERE / P["state"]
for k in ("PER_TRADE", "MAX_POS", "TRAIL_ON", "TRAIL", "MAX_HOLD_H", "STOP"):
    if k in P:
        setattr(agents, k, P[k])
SOURCES = P["sources"]


def _src(f):
    """Source file here, or (cloud copy, 14 Nov) the same name in this folder; keys keep the original string."""
    return HERE / f if (HERE / f).exists() else HERE / Path(f).name


def _entries():
    for f in SOURCES:
        if _src(f).exists():
            for x in json.loads(_src(f).read_text())["log"]:
                if x["kind"] in P["kinds"] and x.get("mint"):
                    yield f, x


def cmd_init(thb):
    agents.cmd_init(thb)
    s = agents.load()
    s["label"] = P["label"]
    s["mirrored"] = [f"{f}:{x['t']}:{x['mint']}" for f, x in _entries()]   # start from now, no back-filling
    agents.save(s)


def cmd_mirror():
    s = agents.load()
    done = set(s.get("mirrored", []))
    for f, x in _entries():
        key = f"{f}:{x['t']}:{x['mint']}"
        if key in done:
            continue
        done.add(key)
        why = agents.paper_buy(s, x["mint"], x.get("sym"), source=f.replace("state_", "").replace(".json", ""))
        print(f"mirror {x.get('sym')} from {f}: {'bought' if why is None else why}")
    s["mirrored"] = sorted(done)
    agents.save(s)


if __name__ == "__main__":
    a = sys.argv[1:]
    cmds = {"init": lambda: cmd_init(a[1]), "mirror": cmd_mirror, "run": agents.cmd_run, "status": agents.cmd_status}
    if not a or a[0] not in cmds:
        sys.exit(__doc__)
    cmds[a[0]]()
