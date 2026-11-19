#!/usr/bin/env python3
"""Mac-only reader for the Grok Bot "Hourly strategy scout" routine (19-20 Nov 2026). Paper money only.
Every hour Grok Bot posts one line "RECIPE: {json}" (a strategy it found on X, in x_recipes.json terms) or "RECIPE: none".
This script reads the open Grok Bot tab in Canary (CDP 9222, no messages sent), turns each new valid RECIPE into a
500 THB zoo account g_scout_<n>, logs every reply to data/grokscout_log.md and pushes, so the cloud opens the account.

  python3 grokscout.py          read, add, log, commit and push
  python3 grokscout.py --dry    read and print what would be added
"""
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))           # run with python -I from agents.sh
import zoo  # noqa: E402

CHAT = "chat/bots/5a365ff7-2a25-4cef-8a5f-42368835267a"
START = "Created routine “Hourly strategy scout”"     # only replies after the setup message count
LOG, SEEN = HERE / "data" / "grokscout_log.md", HERE / "data" / "grokscout_seen.json"
TEXT_JS = "(()=>{let o='';const w=r=>{for(const e of r.querySelectorAll('*')){if(e.shadowRoot){o+=e.shadowRoot.textContent+'\\n';w(e.shadowRoot)}}};w(document);return o})()"
CDP = ("const ws=new WebSocket(process.argv[1]);ws.onopen=()=>ws.send(JSON.stringify({id:1,method:process.argv[2],"
       "params:JSON.parse(process.argv[3])}));ws.onmessage=e=>{const m=JSON.parse(e.data);"
       "if(m.id===1){process.stdout.write(String(m.result?.result?.value??''));process.exit(0)}};setTimeout(()=>process.exit(2),20000)")


def chat_text():
    """Reload the background Grok Bot tab (it stops receiving messages otherwise) and return its text, or None."""
    import time
    import urllib.request
    tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5))
    tab = next((t for t in tabs if t.get("type") == "page" and CHAT in t.get("url", "")), None)
    if not tab:
        return None
    run = lambda method, params: subprocess.run(["/opt/homebrew/bin/node", "-e", CDP, tab["webSocketDebuggerUrl"], method, json.dumps(params)],
                                                capture_output=True, text=True, timeout=40)
    run("Page.reload", {})
    time.sleep(15)
    r = run("Runtime.evaluate", {"expression": TEXT_JS, "returnByValue": True})
    return r.stdout if r.returncode == 0 and START in r.stdout else None


def replies(text):
    """Every RECIPE reply after the setup message, in order: a dict, or "none", or "bad: <why>"."""
    text = text[text.index(START):]
    out, dec = [], json.JSONDecoder()
    for m in re.finditer(r"RECIPE:\s*", text):
        rest = text[m.end():]
        if rest.lower().startswith("none"):
            out.append("none")
            continue
        try:
            obj, _ = dec.raw_decode(rest)
            out.append(obj if isinstance(obj, dict) else "bad: not an object")
        except ValueError as err:
            out.append(f"bad: {err}"[:80])
    return out


def to_spec(obj, n):
    """Grok's recipe -> an x_recipes.json entry, or raises with the reason. Never fills in numbers Grok did not give."""
    assert str(obj.get("source", "")).startswith("http"), "no source url"
    assert obj.get("label") and not str(obj["label"]).startswith("<"), "no label"
    e = obj.get("entry") or {}
    entry = {k: e[k] for k in ("min", "max") if e.get(k)} | {k: True for k in ("safe", "up", "rugcheck") if e.get(k) is True}
    x = dict(obj.get("exit") or {})
    if x.get("PER_TRADE") is not None:
        x["PER_TRADE"] = min(float(x["PER_TRADE"]), 0.5)   # shortcut: Grok was told max 0.5; clamp instead of rejecting
    assert entry.get("min") or entry.get("max"), "no numeric entry rule"
    spec = dict(name=f"g_scout_{n}", label=f"Grok Bot หาเอง: {str(obj['label'])[:80]}", source=obj["source"],
                claim=str(obj.get("claim", ""))[:200], added=datetime.now().date().isoformat(), active=True, horizon="week",
                entry=entry, exit=x, note="from the Grok Bot hourly strategy scout routine; rules translated by Grok, not by us")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump([spec], fh)
    before = set(zoo.ZOO)
    zoo.load_specs(Path(fh.name))                       # same checks as the cloud: unknown keys, types, name
    assert spec["name"] in zoo.ZOO and spec["name"] not in before, "rejected by zoo.load_specs (see message above)"
    return spec


def main(dry):
    text = chat_text()
    if text is None:
        return print("grokscout: Grok Bot tab not open or routine message not loaded")
    seen = json.loads(SEEN.read_text()) if SEEN.exists() else 0
    new = replies(text)[seen:]
    if not new:
        return print("grokscout: nothing new")
    specs = json.loads(zoo.SPECS.read_text())
    sources = {s.get("source") for s in specs}
    n = sum(s["name"].startswith("g_scout_") for s in specs)
    lines = []
    for r in new:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        if isinstance(r, str):
            lines.append(f"- {now} {r}")
            continue
        try:
            assert r.get("source") not in sources, "same post as an earlier recipe"
            spec = to_spec(r, n + 1)
        except Exception as err:
            lines.append(f"- {now} skipped ({err}) {r.get('source', '')}")
            continue
        n += 1
        specs.append(spec)
        sources.add(spec["source"])
        lines.append(f"- {now} {spec['name']} {spec['label']} | claim: {spec['claim']} | {spec['source']}")
    print("\n".join(lines))
    if dry:
        return
    zoo.SPECS.write_text(json.dumps(specs, ensure_ascii=False, indent=1) + "\n")
    LOG.write_text((LOG.read_text() if LOG.exists() else "# Grok Bot hourly strategy scout (19-20 Nov 2026)\n\n") + "\n".join(lines) + "\n")
    SEEN.write_text(json.dumps(seen + len(new)))
    g = ["git", "-C", str(HERE)]
    subprocess.run(g + ["add", "x_recipes.json", str(LOG), str(SEEN)], check=True)
    subprocess.run(g + ["-c", "user.name=papertrade-bot", "-c", "user.email=papertrade-bot@users.noreply.github.com",
                        "commit", "-qm", f"grok scout: {len(new)} new replies"], check=True)
    subprocess.run(g + ["pull", "-q", "--rebase"], check=True)
    subprocess.run(g + ["push", "-q"], check=True)


if __name__ == "__main__":
    main("--dry" in sys.argv)
