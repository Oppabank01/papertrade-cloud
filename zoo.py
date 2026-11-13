#!/usr/bin/env python3
"""Strategy zoo (14 Nov 2026), fake money only: many small 500 THB accounts, each one entry rule x one exit rule,
all fed by the same GMGN 5m ranking (data/rank5m_latest.json) so they are directly comparable. Includes a random
pick control: a rule only means something if it beats "rand" with the same exits.
Every scan also saves a slim copy of the ranking to data/rank_hist/ so later rules can be backtested offline.

  python3 zoo.py init 500      # creates any missing zoo account (never resets a running one)
  python3 zoo.py tick          # scan the newest ranking + exits, every account
  python3 zoo.py report        # one line per account, sorted by result
"""
import gzip
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import agents  # noqa: E402
import recipes  # noqa: E402

HERE = Path(__file__).parent
RANK, HIST = HERE / "data" / "rank5m_latest.json", HERE / "data" / "rank_hist"
KEEP = ("address", "symbol", "price", "liquidity", "market_cap", "volume", "holder_count", "open_timestamp", "buys", "sells",
        "price_change_percent1m", "price_change_percent5m", "price_change_percent1h", "smart_degen_count", "renowned_count",
        "top_10_holder_rate", "dev_team_hold_rate", "bundler_rate", "rug_ratio", "sniper_count", "bot_degen_rate", "hot_level",
        "cto_flag", "launchpad_status", "migrated_pool_exchange", "dexscr_boost_fee", "is_wash_trading")

f = lambda t, k: float(t.get(k) or 0)
age_h = lambda t: recipes.age_min(t) / 60
ok = recipes.base_guard          # honeypot, mint/freeze renounced, no sell tax, liq >= $10k
safe = lambda t: (f(t, "top_10_holder_rate") <= 0.20 and f(t, "dev_team_hold_rate") <= 0.02 and f(t, "bundler_rate") <= 0.15
                  and f(t, "rug_ratio") <= 0.1 and not t.get("is_wash_trading") and f(t, "holder_count") >= 500)
up = recipes.up_with_buyers      # buys > sells and 0 < 5m change <= 100%

STD = dict(STOP=-0.08, TP_ALL=None, HALF_AT=None, TRAIL_ON=0.15, TRAIL=0.15, MAX_HOLD_H=3, PER_TRADE=0.20, MAX_POS=4, COOLDOWN_H=24)


def score(t):
    """0-100 'Analyst' score for the savipww 5-bot recipe (the post gives no formula; this one is ours, fixed in advance)."""
    b, sl = f(t, "buys"), f(t, "sells")
    return (20 * safe(t) + 2 * min(f(t, "smart_degen_count"), 10) + 4 * min(f(t, "renowned_count"), 5)
            + (15 if b > 1.5 * sl else 8 if b > sl else 0) + 15 * (5 <= f(t, "price_change_percent5m") <= 60)
            + 10 * (f(t, "holder_count") >= 1000))


vl = lambda t: f(t, "volume") / max(f(t, "liquidity"), 1)     # gmgn-vl-radar ranks by volume / liquidity
RUN = dict(STOP=-0.15, TP_ALL=None, TRAIL_ON=0.30, TRAIL=0.25, MAX_HOLD_H=24)
ZOO = {   # name: (label, entry rule, exit/sizing overrides). "pick" = one token per ranking chosen from those that pass.
    "rand":     ("สุ่ม 1 ตัว (ตัวควบคุม)", ok, {}),
    "top1":     ("วอลุ่มอันดับ 1", ok, {}),
    "mom5":     ("โมเมนตัม 5 นาที +10 ถึง +50%", lambda t: up(t) and 10 <= f(t, "price_change_percent5m") <= 50, {}),
    "mom1h":    ("พุ่งแรง 1 ชม. เกิน +100%", lambda t: f(t, "price_change_percent1h") >= 100 and up(t), {}),
    "dip":      ("ช้อนย่อ 5 นาที -15% ในขาขึ้น 1 ชม.", lambda t: f(t, "price_change_percent5m") <= -15 and f(t, "price_change_percent1h") > 20, {}),
    "fresh":    ("เหรียญเกิดใหม่ไม่เกิน 10 นาที", lambda t: recipes.age_min(t) <= 10, {}),
    "aged":     ("เหรียญอายุเกิน 1 วัน ยังมีคนเล่น", lambda t: age_h(t) >= 24 and f(t, "liquidity") >= 50_000 and up(t), {}),
    "bigliq":   ("สภาพคล่อง 200k+ มาร์เก็ตแคป 2M+", lambda t: f(t, "liquidity") >= 200_000 and f(t, "market_cap") >= 2e6 and up(t), {}),
    "holders":  ("คนถือ 3,000 ขึ้นไป", lambda t: f(t, "holder_count") >= 3000 and up(t), {}),
    "safe":     ("ผ่านเช็กความปลอดภัยเข้ม", lambda t: safe(t) and up(t), {}),
    "kol2":     ("KOL เข้า 2 คนขึ้นไป", lambda t: f(t, "renowned_count") >= 2 and up(t), {}),
    "smart10":  ("smart wallet 10 ขึ้นไป", lambda t: f(t, "smart_degen_count") >= 10 and up(t), {}),
    "cto":      ("community takeover", lambda t: t.get("cto_flag") and up(t), {}),
    "boosted":  ("จ่ายโฆษณา DexScreener", lambda t: f(t, "dexscr_boost_fee") > 0 and up(t), {}),
    "scalp":    ("เก็บสั้น +10% ตัด -5% 30 นาที", lambda t: safe(t) and up(t), dict(STOP=-0.05, TP_ALL=0.10, MAX_HOLD_H=0.5, TRAIL_ON=9)),
    "hodl":     ("ไม่ตั้ง stop ถือ 24 ชม.", lambda t: safe(t) and up(t), dict(STOP=-1.0, TRAIL_ON=9, MAX_HOLD_H=24)),
    "moon":     ("ถือยาวรอ x2 (stop -50%)", lambda t: safe(t) and up(t), dict(STOP=-0.5, TP_ALL=1.0, TRAIL_ON=9, MAX_HOLD_H=48)),
    "runwide":  ("ปล่อยวิ่ง trail 30/25 ถือ 24 ชม.", lambda t: safe(t) and up(t), RUN),
    "randrun":  ("สุ่ม 1 ตัว ปล่อยวิ่ง (ตัวควบคุม)", ok, RUN),
    "allin":    ("ทุ่มหมดหน้าตัก ไม้ละ 100%", lambda t: safe(t) and up(t), dict(PER_TRADE=1.0, MAX_POS=1)),
    # X posts added 14 Nov (claims are the posts', unverified)
    "trench":   ("crbpite8 รอบ 2: ปลอดภัย + smart 3 + V/L สูงสุด 3 ตัว",   # $134 -> $3,452, "3 questions, 3 free repos"
                 lambda t: (safe(t) and f(t, "smart_degen_count") >= 3 and f(t, "holder_count") >= 200 and recipes.age_min(t) >= 30
                            and f(t, "market_cap") >= 100_000),
                 dict(rank_by=vl, take=3, MAX_POS=5, STOP=-0.10, TRAIL_ON=0.30, TRAIL=0.20, MAX_HOLD_H=12)),
    "savip":    ("savipww 5 บอท: คะแนน 80+ ทุ่มหมด ขายครึ่ง +30% stop -6%",   # $36 -> $3,125, rebuys allowed
                 lambda t: f(t, "liquidity") >= 20_000 and score(t) >= 70,
                 dict(rank_by=score, take=1, size=lambda t: 1.0 if score(t) >= 80 else 0.25, MAX_POS=3, STOP=-0.06,
                      HALF_AT=0.30, TRAIL_ON=0.30, TRAIL=0.20, MAX_HOLD_H=12, COOLDOWN_H=0)),
    "tomcruise": ("tomcruise 6 เอเจนต์: scanner rug check sizer ตามสภาพคล่อง",   # $60 -> $9,684, post gives no rules
                  lambda t: safe(t) and up(t),
                  dict(size=lambda t: 0.40 if f(t, "liquidity") >= 200_000 else 0.25 if f(t, "liquidity") >= 50_000 else 0.10)),
}
ONE_PICK = {"rand", "randrun", "top1"}   # these take a single token per ranking; the rest buy every match (up to MAX_POS)


def use(name):
    for k, v in {**STD, **ZOO[name][2]}.items():
        if k.isupper():
            setattr(agents, k, v)
    agents.STATE = HERE / f"state_zoo_{name}.json"


def save_hist(d):
    """Slim copy of each new ranking: one small gzip file per scan, so git only ever adds files."""
    ts = time.gmtime(d["t"])
    out = HIST / time.strftime("%Y-%m-%d", ts) / time.strftime("%H%M%S.json.gz", ts)
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(gzip.compress(json.dumps(dict(t=d["t"], rank=[{k: x.get(k) for k in KEEP} for x in d["rank"]])).encode()))


def picks(name, rank):
    rule = ZOO[name][1]
    hits = [t for t in rank if ok(t) and rule(t)]
    if name in ("rand", "randrun"):
        return random.sample(hits, 1) if hits else []
    if name == "top1":
        return hits[:1]                   # the ranking is sorted by 5m volume
    ov = ZOO[name][2]
    if "rank_by" in ov:
        hits = sorted(hits, key=ov["rank_by"], reverse=True)[:ov["take"]]
    return hits


def cmd_init(thb):
    for name, (label, _, _) in ZOO.items():
        use(name)
        if not agents.STATE.exists():
            agents.cmd_init(thb)
            s = agents.load()
            s["label"] = f"สวนสัตว์: {label}"
            agents.save(s)
            print(f"init {name}")


def cmd_tick():
    d = json.loads(RANK.read_text()) if RANK.exists() else None
    if d:
        save_hist(d)
    for name in ZOO:
        use(name)
        if not agents.STATE.exists():
            continue
        s = agents.load()
        if d and d["t"] > s.get("rank_t", 0):
            s["rank_t"] = d["t"]
            for t in picks(name, d["rank"]):
                if "size" in ZOO[name][2]:
                    agents.PER_TRADE = ZOO[name][2]["size"](t)
                agents.paper_buy(s, t["address"], t.get("symbol"), zoo=name, smart=t.get("smart_degen_count"), kol=t.get("renowned_count"))
            agents.save(s)
        agents.cmd_run()


def cmd_report():
    rows = []
    for name in ZOO:
        use(name)
        if agents.STATE.exists():
            s = agents.load()
            sells = [x["pnl"] for x in s["log"] if x["kind"] == "sell"]
            rows.append((agents.equity(s) / s["start_usd"] - 1, name, s.get("label", name), len(sells), sum(p > 0 for p in sells)))
    for r, name, label, n, w in sorted(rows, reverse=True):
        print(f"{r:+7.1%}  {name:8s} ไม้ {n:3d} ชนะ {w:3d}  {label}")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmds = {"init": lambda: cmd_init(a[1]), "tick": cmd_tick, "report": cmd_report}
    if not a or a[0] not in cmds:
        sys.exit(__doc__)
    cmds[a[0]]()
