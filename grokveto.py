#!/usr/bin/env python3
"""Mac-only reader for two Grok Bot routines (19-20 Nov 2026), paper money only, nothing is bought here.

"Meme veto": every 5 min Grok reads data/veto_queue.json (the v_rule account's candidates, public on GitHub), checks X news
and the chart, and posts "VETO <id> APPROVE|REJECT <mint> reason=...". Approvals become orders for the v_grok account
(data/orders_v_grok.json, bought by the cloud within 30 min of the candidate); data/veto_stats.json holds the running
approve rate that v_rand copies at random.

"Meme expert": Grok trades its own $50 fake ledger freely (news + charts, no fixed rules) and posts LEDGER S8 / LTRADE S8
lines; every trade price is checked against GeckoTerminal candles (grok_check.py) into data/grok_expert_log.md.

  python3 grokveto.py          read both, write files, commit and push
  python3 grokveto.py --dry    print only
"""
import io
import json
import re
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))           # run with python -I from agents.sh
import grok_check  # noqa: E402
from grokscout import chat_text  # noqa: E402

VETO, EXPERT = "Created routine “Meme veto”", "Created routine “Meme expert”"
QUEUE, ORDERS, STATS = HERE / "data" / "veto_queue.json", HERE / "data" / "orders_v_grok.json", HERE / "data" / "veto_stats.json"
EXPLOG = HERE / "data" / "grok_expert_log.md"
LINE = re.compile(r"VETO (c\d+) (APPROVE|REJECT) (\S+) reason=(.{0,160}?)(?=VETO |LEDGER|LTRADE|$)")


def after(text, marker):
    return text[text.rindex(marker):] if marker in text else ""


def veto_files(text):
    """(orders, stats) rebuilt from every VETO line; an approval is an order dated at the candidate's queue time."""
    q = {x["id"]: x for x in (json.loads(QUEUE.read_text()) if QUEUE.exists() else [])}
    old = {o["id"]: o for o in (json.loads(ORDERS.read_text()) if ORDERS.exists() else [])}
    dec = {}
    for m in LINE.finditer(after(text, VETO)):
        dec.setdefault(m[1], m)                 # first decision per candidate counts
    for i, m in dec.items():
        c = q.get(i)
        if m[2] == "APPROVE" and c and c["mint"] == m[3] and i not in old:
            old[i] = dict(id=i, mint=c["mint"], sym=c.get("sym"), size=0.2, why=f"Grok: {m[4].strip()}"[:200], t=c["t"])
    ok = [m for i, m in dec.items() if i in q]          # decisions on candidates that really were in the queue
    stats = dict(approve=sum(m[2] == "APPROVE" for m in ok), reject=sum(m[2] == "REJECT" for m in ok))
    return list(old.values()), stats


def expert_log(text):
    t = after(text, EXPERT)
    led = re.findall(r"LEDGER S8 (\d\d:\d\d) cash=([\d.]+) equity=([\d.]+)", t)
    day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = []
    for tr in grok_check.parse(t, day, 7):
        with redirect_stdout(io.StringIO()):
            v, why = grok_check.check(tr, 5, 3)
        rows.append(f"- {v} {tr['hm']} {tr['side']} {tr['sym']} px={tr['px']:.6g} | {why}")
    eq = f"{float(led[-1][2]) / 50 - 1:+.1%} (equity ${led[-1][2]} at {led[-1][0]})" if led else "ยังไม่มีรายงาน"
    return (f"# Grok Bot คุมเองทั้งหมด (19-20 พ.ย. 69, เงินปลอม $50, Grok ตัดสินใจเองจากข่าว X และกราฟ)\n\n"
            f"ผลตามที่ Grok รายงาน: {eq} | รอบที่รายงาน {len(led)} | ไม้ที่ราคาตรวจไม่ผ่าน {sum(not r.startswith('- OK') for r in rows)} จาก {len(rows)}\n\n"
            "## ไม้ทั้งหมด พร้อมผลตรวจราคา GeckoTerminal\n\n" + "\n".join(rows) + "\n")


def main(dry):
    text = chat_text(VETO)
    if text is None:
        return print("grokveto: Grok Bot tab not open or routine message not loaded")
    orders, stats = veto_files(text)
    log = expert_log(text)
    if dry:
        return print(json.dumps(stats), len(orders), "orders\n" + log)
    ORDERS.write_text(json.dumps(orders, ensure_ascii=False, indent=0))
    STATS.write_text(json.dumps(stats))
    EXPLOG.write_text(log)
    g = ["git", "-C", str(HERE)]
    subprocess.run(g + ["add", str(ORDERS), str(STATS), str(EXPLOG)], check=True)
    if subprocess.run(g + ["diff", "--cached", "--quiet"]).returncode == 0:
        return
    subprocess.run(g + ["-c", "user.name=papertrade-bot", "-c", "user.email=papertrade-bot@users.noreply.github.com",
                        "commit", "-qm", f"grok veto {stats} + expert ledger from the Grok Bot chat"], check=True)
    subprocess.run(g + ["pull", "-q", "--rebase"], check=True)
    subprocess.run(g + ["push", "-q"], check=True)


if __name__ == "__main__":
    main("--dry" in sys.argv)
