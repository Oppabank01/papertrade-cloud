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
from datetime import datetime, timedelta
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


def chat_text(start=None, js=TEXT_JS, size=3000):
    """Reload the background Grok Bot tab (it stops receiving messages otherwise) and return its text, or None."""
    import time
    import urllib.request
    if LOCK.exists():
        return None                     # a backfill is scrolling the tab; a reload would undo it
    tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5))
    tab = next((t for t in tabs if t.get("type") == "page" and CHAT in t.get("url", "")), None)
    if not tab:
        return None
    run = lambda method, params: subprocess.run(["/opt/homebrew/bin/node", "-e", CDP, tab["webSocketDebuggerUrl"], method, json.dumps(params)],
                                                capture_output=True, text=True, timeout=40)
    run("Page.reload", {})
    last = None
    for _ in range(12):                 # the chat pane loads well after the page; poll up to ~75 s, until it stops growing
        time.sleep(6)
        r = run("Runtime.evaluate", {"expression": js, "returnByValue": True})
        if r.returncode == 0 and (start or START) in r.stdout and len(r.stdout) > size:
            if r.stdout == last:
                return r.stdout
            last = r.stdout
    return last


# X keeps only the last ~25 min of the bot chat in the page (scrolling does not load older messages, checked 19 Nov),
# so the setup message drops out and anything not read in time is lost: every read is merged into an archive file.
PANE_JS = ("(()=>{const a=[];const w=r=>{for(const e of r.querySelectorAll('*')){a.push(e);if(e.shadowRoot)w(e.shadowRoot)}};w(document);"
           "const s=a.filter(e=>e.scrollHeight>e.clientHeight+200&&/(auto|scroll)/.test(getComputedStyle(e).overflowY))"
           ".sort((x,y)=>y.scrollHeight-x.scrollHeight)[0];return s?s.textContent:''})()")
ARCHIVE, LOCK = HERE / "data" / "grok_chat_archive.txt", HERE / ".grok_backfill.lock"   # same path for launchd and the shell
REC = re.compile(r"(?=LEDGER S\d|LTRADE S\d|RESULT S\d|VETO c\d|SEEN S\d|NO DATA \d)")


def merge(old, new):
    """Append the records after their overlap with the archive tail; records can repeat (e.g. two equal RESULT lines), so no set."""
    for k in range(min(len(old), len(new)), 0, -1):
        if old[-k:] == new[:k]:
            return old + new[k:]
    return old + (["GAP (reader missed messages here)"] if old else []) + new


START_DAY = datetime(2026, 11, 19)     # the archive began 19 Nov 2026 about 21:00


def by_day(text):
    """[(date, records)] split where LEDGER clock times wrap past midnight (records carry HH:MM only)."""
    day, seg, out, prev = START_DAY, [], [], None
    for line in text.splitlines():
        m = re.match(r"LEDGER S\d (\d\d):(\d\d)", line)
        if m:
            t = int(m[1]) * 60 + int(m[2])
            if prev is not None and t < prev - 720:
                out.append((day, "\n".join(seg)))
                seg, day = [], day + timedelta(days=1)
            prev = t
        seg.append(line)
    return out + [(day, "\n".join(seg))]


PANE = ("const a=[];const w=r=>{for(const e of r.querySelectorAll('*')){a.push(e);if(e.shadowRoot)w(e.shadowRoot)}};w(document);"
        "const s=a.filter(e=>e.scrollHeight>e.clientHeight+200&&/(auto|scroll)/.test(getComputedStyle(e).overflowY)&&e.textContent.includes('LEDGER S'))"
        ".sort((x,y)=>y.scrollHeight-x.scrollHeight)[0];")


def backfill(marker="Created routine “Meme 1h test v2”", limit=400):
    """Rebuild the archive from the chat history: wheel the message pane up until `marker` loads (older messages
    load only on a real scroll over the pane), then step down to the bottom merging each view. Moves the visible tab."""
    LOCK.touch()
    try:
        _backfill(marker, limit)
    finally:
        LOCK.unlink()


def _backfill(marker, limit):
    import time
    import urllib.request
    tab = next(t for t in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5))
               if t.get("type") == "page" and CHAT in t.get("url", ""))
    run = lambda m, p: subprocess.run(["/opt/homebrew/bin/node", "-e", CDP, tab["webSocketDebuggerUrl"], m, json.dumps(p)],
                                      capture_output=True, text=True, timeout=40).stdout
    ev = lambda js: json.loads(run("Runtime.evaluate", {"expression": "(()=>{" + PANE + js + "})()", "returnByValue": True}) or "null")
    for _ in range(15):                 # the pane appears well after the page loads
        xy = ev("if(!s)return 'null';const r=s.getBoundingClientRect();return JSON.stringify([r.x+r.width/2,r.y+r.height/2])")
        if xy:
            break
        time.sleep(5)
    else:
        return print("backfill: message pane not found")
    x, y = xy
    for _ in range(limit):              # older messages load on a wheel that scrolls up into the top, not at top=0 already
        ev("s.scrollTop=400;return '1'")
        for _ in range(3):
            run("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": -1500})
            time.sleep(0.7)
        time.sleep(2)
        top, text = ev("return JSON.stringify([s.scrollTop,s.textContent])")
        print("up", top, re.findall(r"LEDGER S\d (\d\d:\d\d)", text)[:1], flush=True)
        if marker in text and top == 0:
            break
    else:
        return print("backfill: marker never loaded")
    out = []
    while True:
        top, bottom, text = ev("const t=s.textContent,p=s.scrollTop;s.scrollTop=p+s.clientHeight*0.5;"
                               "return JSON.stringify([p,p+s.clientHeight>=s.scrollHeight-5,t])")
        if marker in text:
            text = text[text.rindex(marker):]
        out = merge(out, [r.strip() for r in REC.split(text)[1:] if r.strip()])
        if bottom:
            break
        time.sleep(1.5)
    ARCHIVE.write_text("\n".join(out) + "\n")
    print(f"backfill: {len(out)} records, {sum(r.startswith('GAP') for r in out)} gaps")


def records():
    """Read the message pane, merge it into the archive, return the archive text (one record per line), or None."""
    text = chat_text("LEDGER S", PANE_JS, 1500)
    if text is None:
        return None
    new = [x.strip() for x in REC.split(text)[1:] if x.strip()]
    old = ARCHIVE.read_text().splitlines() if ARCHIVE.exists() else []
    out = merge(old, new)
    ARCHIVE.write_text("\n".join(out) + "\n")
    return "\n".join(out)


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


if __name__ == "__main__" and "--backfill" in sys.argv:
    backfill()
elif __name__ == "__main__":
    main("--dry" in sys.argv)
