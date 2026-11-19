#!/usr/bin/env python3
"""Mac-only reader for the Grok Bot "Meme 1h test" routine (19 Nov 2026, every 5 min, one strategy per clock hour S1..S7).
Grok keeps its own $15 fake ledger and posts LEDGER / LTRADE / RESULT lines. Paper money only, nothing is bought here.
This script reads the open Grok Bot tab (CDP 9222, no messages sent) and rewrites data/grok1h_log.md with every
RESULT line, the trades of each strategy and how many runs said NO DATA, then commits and pushes if it changed.

  python3 grok1h.py           read, write the log, commit and push
  python3 grok1h.py --dry     print the log only
"""
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))           # run with python -I from agents.sh
from grokscout import chat_text  # noqa: E402  (same tab reader)

START = "Created routine “Meme 1h test”"
LOG = HERE / "data" / "grok1h_log.md"
NAMES = {1: "ช้อนย่อ 1 ชม. -15 ถึง -35% (savipww)", 2: "pool 200k+ ขึ้น 1 ชม. 10-50%", 3: "เด้งหลังร่วง ถือไม่เกิน 50 นาที",
         4: "คู่ใหม่ไม่เกิน 6 ชม. TP15 SL15", 5: "TP +60% SL -25%", 6: "เพิ่งย้ายจาก pump.fun TP35 SL15", 7: "วอลุ่ม 5 นาทีสูงสุด trail 15"}


def summary(text):
    """Markdown summary of the routine's replies after the setup message."""
    text = text[text.index(START):]
    res = {int(m[1]): m for m in re.finditer(r"RESULT S(\d) start=([\d.]+) end=([\d.]+) trades=(\d+) wins=(\d+)", text)}
    trades = re.findall(r"LTRADE S(\d) (BUY|SELL) (\S+) \S+ price=(\S+) reason=(.{0,60}?)(?=LTRADE|LEDGER|RESULT|NO DATA|$)", text)
    out = ["# Grok Bot ทดสอบท่าเหรียญมีมท่าละ 1 ชม. (19 พ.ย. 69, เงินปลอม $15 ต่อท่า, Grok คิดเองทั้งหมด)", "",
           f"รอบที่ Grok ตอบ NO DATA: {text.count('NO DATA')}", "", "| ท่า | ผล | ไม้ | ชนะ |", "|---|---|---|---|"]
    for k, name in NAMES.items():
        m = res.get(k)
        out.append(f"| S{k} {name} | {float(m[3]) / float(m[2]) - 1:+.1%} | {m[4]} | {m[5]} |" if m else f"| S{k} {name} | ยังไม่จบ | - | - |")
    out += ["", "## รายการซื้อขายที่ Grok รายงาน (ยังไม่ได้ตรวจราคาย้อนหลัง)", ""]
    out += [f"- S{s} {side} {sym} @ {px} {why.strip()}" for s, side, sym, px, why in trades]
    return "\n".join(out) + "\n"


def main(dry):
    text = chat_text(START)
    if text is None:
        return print("grok1h: Grok Bot tab not open or routine message not loaded")
    s = summary(text)
    if dry:
        return print(s)
    if LOG.exists() and LOG.read_text() == s:
        return
    LOG.write_text(s)
    g = ["git", "-C", str(HERE)]
    subprocess.run(g + ["add", str(LOG)], check=True)
    subprocess.run(g + ["-c", "user.name=papertrade-bot", "-c", "user.email=papertrade-bot@users.noreply.github.com",
                        "commit", "-qm", "grok 1h test: results from the Grok Bot chat"], check=True)
    subprocess.run(g + ["pull", "-q", "--rebase"], check=True)
    subprocess.run(g + ["push", "-q"], check=True)


if __name__ == "__main__":
    main("--dry" in sys.argv)
