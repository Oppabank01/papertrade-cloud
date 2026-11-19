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


# X keeps only the last ~25 min of the bot chat in the page unless someone scrolls it, so the setup message drops out and
# anything not read in time is lost: every read is merged into an archive keyed by X's message key (t16s<seq>, in order).
PANE = ("const a=[];const w=r=>{for(const e of r.querySelectorAll('*')){a.push(e);if(e.shadowRoot)w(e.shadowRoot)}};w(document);"
        "const s=a.filter(e=>e.scrollHeight>e.clientHeight+200&&/(auto|scroll)/.test(getComputedStyle(e).overflowY)&&e.getBoundingClientRect().x>innerWidth*0.3)"
        ".sort((x,y)=>y.scrollHeight-x.scrollHeight)[0];")   # the message pane, right of the chat list
ITEMS = "JSON.stringify(s?[...s.querySelectorAll('[data-dm-item-key]')].map(e=>[e.dataset.dmItemKey,e.textContent]):[])"
ARCHIVE, LOCK = HERE / "data" / "grok_chat_archive.json", HERE / ".grok_backfill.lock"   # lock path is the same for launchd and the shell
REC = re.compile(r"(?=LEDGER S\d|LTRADE S\d|RESULT S\d|VETO c\d|SEEN S\d|NO DATA \d)")
START_DAY = datetime(2026, 11, 19)     # first archived message: 19 Nov 2026 16:10
FIRST = "Created routine “Meme 1h test v2”"


def seq(key):
    """X message key t<turn>u (our message) / t<turn>s<n> (reply n) -> sort key; separators and events -> None."""
    m = re.fullmatch(r"t(\d+)(?:u|s(\d+))", key)
    return m and (int(m[1]), -1 if m[2] is None else int(m[2]))


def as_text(msgs):
    """Archive {key: message} -> one record per line, in message order, from the v2 setup message on."""
    keys = sorted((k for k in msgs if seq(k)), key=seq)
    first = max((k for k in keys if FIRST in msgs[k]), key=seq, default=None)
    keep = [k for k in keys if (first is None or seq(k) > seq(first)) and seq(k)[1] >= 0]   # Grok's replies only, not our prompts
    return "\n".join(r.strip() for k in keep for r in REC.split(msgs[k])[1:] if r.strip())


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


def save(items):
    msgs = json.loads(ARCHIVE.read_text()) if ARCHIVE.exists() else {}
    msgs |= dict(items)
    msgs = {k: v for k, v in msgs.items() if seq(k)}
    ARCHIVE.write_text(json.dumps(dict(sorted(msgs.items(), key=lambda kv: seq(kv[0]))), ensure_ascii=False, indent=0))
    return msgs


def backfill(limit=400):
    """Fill the archive from the chat history: wheel the message pane up until the v2 setup message loads (older
    messages load only on a real scroll over the pane), then step down to the bottom saving every message. Moves the tab."""
    LOCK.touch()
    try:
        _backfill(limit)
    finally:
        LOCK.unlink()


def _backfill(limit):
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
    got, flat = {}, 0
    for _ in range(limit):              # older messages load on a wheel that scrolls up into the top, not at top=0 already
        h0 = ev("const h=s.scrollHeight;s.scrollTop=400;return String(h)")
        for _ in range(3):
            run("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": -1500})
            time.sleep(0.7)
        time.sleep(2)
        h, items = ev("return JSON.stringify([s.scrollHeight," + ITEMS + "])")
        got |= dict(json.loads(items))
        flat = flat + 1 if h == h0 else 0
        print("up", h, len(got), flush=True)
        if any(FIRST in v for v in got.values()) or flat >= 4:   # setup message loaded, or nothing older loads any more
            break
    ev("s.scrollTop=0;return '1'")
    flat = 0
    while flat < 4:                     # wheel down (not scrollTop jumps) so X loads the newer pages it dropped
        n = len(got)
        run("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": 500})
        time.sleep(1)
        bottom, items = ev("return JSON.stringify([s.scrollTop+s.clientHeight>=s.scrollHeight-5," + ITEMS + "])")
        got |= dict(json.loads(items))
        flat = flat + 1 if bottom and len(got) == n else 0
    keys = sorted((k for k in got if seq(k)), key=seq)
    miss = [b for a, b in zip(keys, keys[1:]) if seq(a)[0] == seq(b)[0] and seq(b)[1] - seq(a)[1] > 1]
    save(got.items())
    print(f"backfill: {len(got)} messages {keys[0]}..{keys[-1]}, {len(miss)} holes in the key sequence")


def records():
    """Read the messages on the page, merge them into the archive, return the archive as records text, or None."""
    text = chat_text('["t', "(()=>{" + PANE + "return " + ITEMS + "})()", 1500)
    if text is None:
        return None
    return as_text(save(json.loads(text)))


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
