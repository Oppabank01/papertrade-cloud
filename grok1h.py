#!/usr/bin/env python3
"""Mac-only reader for the Grok Bot "Meme 1h test v2" routine (19 Nov 2026 16:10-22:55, every 5 min). Paper money only.
Design by the Fable review: 7 ledgers ($15 each, reset every clock hour) run side by side on the same universe, S1 is a
random pick from that universe (the same-hour baseline) and S7 is a known loser (harness check). Grok posts LEDGER /
LTRADE / RESULT lines; this script reads the open Grok Bot tab (CDP 9222, no messages sent), checks every LTRADE price
against GeckoTerminal 1-minute candles (grok_check.py), and rewrites data/grok1h_log.md, then commits and pushes if it
changed. Grok's own RESULT numbers are shown but only trusted for hours where every trade checked OK.

  python3 grok1h.py           read, check, write the log, commit and push
  python3 grok1h.py --dry     print the log only
"""
import io
import re
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))           # run with python -I from agents.sh
import grok_check  # noqa: E402
from grokscout import ARCHIVE, by_day, records  # noqa: E402  (same tab reader + archive)

START = "Created routine “Meme 1h test v2”"
LOG = HERE / "data" / "grok1h_log.md"
NAMES = {1: "สุ่ม 1 ตัวจากกลุ่มเดียวกัน (ตัวเทียบ)", 2: "ร่วง 1 ชม. -15% ซื้อทันที", 3: "ร่วง -15% สองรอบติด และ 5 นาทีไม่ลบ",
         4: "S3 และ 6 ชม. ไม่บวก (ร่วงจริง)", 5: "S3 และ 6 ชม. บวก 20%+ (คาดว่าแพ้)", 6: "S3 ใน pool 200k+",
         7: "คู่ใหม่ TP15 SL15 (ท่าที่รู้ว่าแพ้ ใช้เช็ก Grok)"}
RES = re.compile(r"RESULT S(\d) start=([\d.]+) end=([\d.]+) trades=(\d+) wins=(\d+)")


def summary(text, checks):
    res = {}
    for m in RES.finditer(text):
        res.setdefault(int(m[1]), []).append(float(m[3]) / float(m[2]) - 1)
    base = res.get(1, [])
    out = ["# Grok Bot ทดสอบท่าเหรียญมีม 7 บัญชีพร้อมกัน (19 พ.ย. 69 16:10-22:55, เงินปลอม $15 ต่อบัญชีต่อชั่วโมง)", "",
           f"อัปเดต {datetime.now():%H:%M} | รอบที่ Grok ตอบ NO DATA: {len(re.findall(r'NO DATA \d\d:\d\d', text))} | "
           f"ไม้ที่ราคาตรวจไม่ผ่าน: {sum(v != 'OK' for v, _ in checks)} จาก {len(checks)}", "",
           "| ท่า | ชั่วโมงที่จบ | เฉลี่ยต่อชั่วโมง | เทียบสุ่ม S1 |", "|---|---|---|---|"]
    for k, name in NAMES.items():
        r = res.get(k, [])
        avg = sum(r) / len(r) if r else None
        diff = f"{avg - sum(base) / len(base):+.1%}" if r and base and k != 1 else "-"
        out.append(f"| S{k} {name} | {len(r)} | {f'{avg:+.1%}' if r else '-'} | {diff} |")
    out += ["", "## ไม้ที่ Grok รายงาน พร้อมผลตรวจราคา GeckoTerminal", ""] + [f"- {v} {line}" for v, line in checks]
    return "\n".join(out) + "\n"


def check_all(text):
    """grok_check.py on every LTRADE line of the v2 routine (S1-S7; S8 is the expert routine) -> [(verdict, line)]."""
    out = []
    for t in [t for day, seg in by_day(text) for t in grok_check.parse(seg, day, 7) if t["s"] <= 7]:
        with redirect_stdout(io.StringIO()):
            v, why = grok_check.check(t, 5, 3)
        out.append((v, f"S{t['s']} {t['hm']} {t['side']} {t['sym']} px={t['px']:.6g} | {why}"))
    return out


def main(dry):
    text = records()
    if text is None:
        return print("grok1h: Grok Bot tab not open or routine message not loaded")
    s = summary(text, check_all(text))
    if dry:
        return print(s)
    strip = lambda x: re.sub(r"อัปเดต \d\d:\d\d", "", x)
    if LOG.exists() and strip(LOG.read_text()) == strip(s):
        return                                  # only the update time changed
    LOG.write_text(s)
    g = ["git", "-C", str(HERE)]
    subprocess.run(g + ["add", str(LOG), str(ARCHIVE)], check=True)
    subprocess.run(g + ["-c", "user.name=papertrade-bot", "-c", "user.email=papertrade-bot@users.noreply.github.com",
                        "commit", "-qm", "grok 1h test v2: results from the Grok Bot chat"], check=True)
    subprocess.run(g + ["pull", "-q", "--rebase", "--autostash"], check=True)
    subprocess.run(g + ["push", "-q"], check=True)


if __name__ == "__main__":
    main("--dry" in sys.argv)
