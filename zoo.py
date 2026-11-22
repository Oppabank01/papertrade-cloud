#!/usr/bin/env python3
"""Strategy zoo (14 Nov 2026), fake money only: many small 500 THB accounts, each one entry rule x one exit rule,
all fed by the same GMGN 5m ranking (data/rank5m_latest.json) so they are directly comparable. Includes a random
pick control: a rule only means something if it beats "rand" with the same exits.
Every scan also saves a slim copy of the ranking to data/rank_hist/ so later rules can be backtested offline.

  python3 zoo.py init 500      # creates any missing zoo account (never resets a running one)
  python3 zoo.py tick          # scan the newest ranking + exits, every account
  python3 zoo.py report        # one line per account, sorted by result
  python3 zoo.py watch 600     # exit checks every 20 s for the FAST accounts until `stopwatch` (cloud.sh runs it in the background)
  python3 zoo.py stopwatch
"""
import fcntl
import gzip
import json
import random
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import agents  # noqa: E402
import recipes  # noqa: E402
import nightly  # noqa: E402

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

STD = dict(STOP=-0.08, TP_ALL=None, HALF_AT=None, TRAIL_ON=0.15, TRAIL=0.15, MAX_HOLD_H=3, PER_TRADE=0.20, MAX_POS=4, COOLDOWN_H=24, MISS_N=2,
           FEE=0.01, SLIP=0.02, WATCH_S=20, GAP_HALT_N=15, HALT_MODE=0, PAUSE_H=1)    # FEE/SLIP per side = agents defaults; listed so a recipe override never leaks to the next account
LOCKS = Path(tempfile.gettempdir()) / "zoo_locks"     # outside data/ so git never picks them up
STOP_FILE = LOCKS / "watch.stop"


def score(t):
    """0-100 'Analyst' score for the savipww 5-bot recipe (the post gives no formula; this one is ours, fixed in advance)."""
    b, sl = f(t, "buys"), f(t, "sells")
    return (20 * safe(t) + 2 * min(f(t, "smart_degen_count"), 10) + 4 * min(f(t, "renowned_count"), 5)
            + (15 if b > 1.5 * sl else 8 if b > sl else 0) + 15 * (5 <= f(t, "price_change_percent5m") <= 60)
            + 10 * (f(t, "holder_count") >= 1000))


big = lambda t: f(t, "liquidity") >= 200_000 and f(t, "market_cap") >= 2e6 and up(t)
aged = lambda t: age_h(t) >= 24 and f(t, "liquidity") >= 50_000 and up(t)
_rc = {}


def rc_clean(t):
    """No RugCheck 'danger' flag (unlocked LP, insiders, top holders...). A failed lookup counts as not clean."""
    a = t.get("address")
    if a not in _rc:
        try:
            _rc[a] = not any(x.get("level") == "danger" for x in agents.grok.get(agents.grok.RUG.format(a)).get("risks") or [])
        except Exception:
            _rc[a] = False
    return _rc[a]


vl = lambda t: f(t, "volume") / max(f(t, "liquidity"), 1)     # gmgn-vl-radar ranks by volume / liquidity
RUN = dict(STOP=-0.15, TP_ALL=None, TRAIL_ON=0.30, TRAIL=0.25, MAX_HOLD_H=24)
ZOO = {   # name: (label, entry rule, exit/sizing overrides). "pick" = one token per ranking chosen from those that pass.
    "rand":     ("สุ่ม 1 ตัว (ตัวควบคุม)", ok, {}),
    "top1":     ("วอลุ่มอันดับ 1", ok, {}),
    "mom5":     ("โมเมนตัม 5 นาที +10 ถึง +50%", lambda t: up(t) and 10 <= f(t, "price_change_percent5m") <= 50, {}),
    "mom1h":    ("พุ่งแรง 1 ชม. เกิน +100%", lambda t: f(t, "price_change_percent1h") >= 100 and up(t), {}),
    "dip":      ("ช้อนย่อ 5 นาที -15% ในขาขึ้น 1 ชม.", lambda t: f(t, "price_change_percent5m") <= -15 and f(t, "price_change_percent1h") > 20, {}),
    "fresh":    ("เหรียญเกิดใหม่ไม่เกิน 10 นาที", lambda t: recipes.age_min(t) <= 10, {}),
    "aged":     ("เหรียญอายุเกิน 1 วัน ยังมีคนเล่น", aged, {}),
    "bigliq":   ("สภาพคล่อง 200k+ มาร์เก็ตแคป 2M+", big, {}),
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
    # 14 Nov: the two best rules so far, with exits checked every 20 s instead of every ~5 min (stops slipped to -35% avg)
    "bigliqF":  ("สภาพคล่อง 200k+ เช็กราคาทุก 20 วิ", big, dict(MISS_N=15)),
    "agedF":    ("อายุเกิน 1 วัน เช็กราคาทุก 20 วิ", aged, dict(MISS_N=15)),
    "bigliqRC": ("สภาพคล่อง 200k+ ผ่าน RugCheck เช็กราคาทุก 20 วิ", lambda t: big(t) and rc_clean(t), dict(MISS_N=15)),
}
FAST = ["bigliqF", "agedF", "bigliqRC"]   # MISS_N=15: ~5 min of missing pool before calling it a rug, same as the 5-min accounts
# 22 Nov: rerun of the rules that a price gap halted for good, with HALT_MODE=1 (the gap bans that coin, the account keeps buying)
for _n in ("bigliqF", "agedF", "bigliqRC"):
    ZOO[_n + "_b2"] = ("รุ่น 2 แบนแค่เหรียญที่ราคาไม่ตรง: " + ZOO[_n][0], ZOO[_n][1], {**ZOO[_n][2], "HALT_MODE": 1})
    FAST.append(_n + "_b2")
ONE_PICK = {"rand", "randrun", "top1"}   # these take a single token per ranking; the rest buy every match (up to MAX_POS)
SPECS = HERE / "x_recipes.json"         # X "bragging" recipes added by the daily research routine: data only, no code
FIELDS = set(KEEP) | {"age_h", "vl", "score", "breadth"}
HORIZONS = {"night": "1 คืน", "week": "1 สัปดาห์", "month": "1 เดือน"}


def val(t, k):
    return age_h(t) if k == "age_h" else vl(t) if k == "vl" else score(t) if k == "score" else f(t, k)


def spec_rule(e):
    return lambda t: (all(val(t, k) >= v for k, v in e.get("min", {}).items()) and all(val(t, k) <= v for k, v in e.get("max", {}).items())
                      and (not e.get("safe") or safe(t)) and (not e.get("up") or up(t)) and (not e.get("rugcheck") or rc_clean(t)))


def load_specs(path):
    """Each x_recipes.json entry becomes a FAST zoo account. A bad entry is skipped with a message, never stops the run."""
    try:
        specs = json.loads(path.read_text()) if path.exists() else []
    except ValueError as err:
        return print(f"x_recipes.json unreadable, no X recipes this run: {err}")
    for sp in specs:
        try:
            n, e, x, p = sp["name"], sp.get("entry", {}), sp.get("exit", {}), sp.get("pick")
            bad = [k for k in (*e.get("min", {}), *e.get("max", {}), *([p["by"]] if p else [])) if k not in FIELDS] + [k for k in x if k not in STD]
            assert not bad, f"unknown keys {bad}"
            assert all(v is None or isinstance(v, (int, float)) for v in (*x.values(), *e.get("min", {}).values(), *e.get("max", {}).values()))
            assert n.isidentifier() and n not in ZOO and sp["horizon"] in HORIZONS and sp["label"]
            off_val = dict(TRAIL_ON=9, TRAIL=0.15, STOP=-1.0, MAX_HOLD_H=1e9)   # null = "no trailing / no stop / no time limit"
            x = {k: (off_val.get(k, STD[k]) if v is None and k not in ("TP_ALL", "HALF_AT") else v) for k, v in x.items()}
            k = 20 / x.get("WATCH_S", 20)       # faster checks: scale the round counts so "rug" and "halt" still mean ~5 min
            ov = {**x, "MISS_N": round(15 * k), "GAP_HALT_N": round(15 * k), "horizon": sp["horizon"], "off": not sp.get("active", True)}
            if sp.get("orders"):
                ov["orders"] = True             # buys come only from data/orders_<name>.json (Grok chat picks), never from the rule
            if sp.get("queue"):
                ov["queue"] = True              # this rule's picks go to data/veto_queue.json for the Grok Bot veto routine
            if sp.get("veto_rand"):
                ov["veto_rand"] = True          # keeps each pick with the Grok veto routine's running approve rate
            if p:
                ov.update(rank_by=lambda t, k=p["by"]: val(t, k), take=int(p["take"]))
            ZOO[n] = (sp["label"], spec_rule(e), ov)
            FAST.append(n)
        except Exception as err:
            print(f"skip X recipe {sp.get('name') if isinstance(sp, dict) else sp}: {err!r}")


def night_book(s, night):
    """'1 night' recipes: trade only 21:00-09:00, close everything at 09:00 and book each night on its own."""
    if s.get("night") and s["night"] != night:
        if s["pos"]:
            nightly.close_all(s, "ปิดรอบเช้า")
        s.setdefault("nights", []).append(dict(night=s["night"], ret=round(agents.equity(s) / s["night_start"] - 1, 4)))
        s["night"] = None
    if night and s.get("night") != night:
        s.update(night=night, night_start=agents.equity(s))


load_specs(SPECS)


def use(name):
    for k, v in {**STD, **ZOO[name][2]}.items():
        if k.isupper():
            setattr(agents, k, v)
    agents.STATE = HERE / f"state_zoo_{name}.json"


def lock(name):
    """Per-account file lock: the background watcher and the tick write the same state files."""
    LOCKS.mkdir(exist_ok=True)
    fh = open(LOCKS / f"{name}.lock", "w")
    fcntl.flock(fh, fcntl.LOCK_EX)
    return fh                             # use as `with lock(name):`, closing releases it


def save_hist(d):
    """Slim copy of each new ranking: one small gzip file per scan, so git only ever adds files."""
    ts = time.gmtime(d["t"])
    out = HIST / time.strftime("%Y-%m-%d", ts) / time.strftime("%H%M%S.json.gz", ts)
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(gzip.compress(json.dumps(dict(t=d["t"], rank=[{k: x.get(k) for k in KEEP} for x in d["rank"]])).encode()))


def picks(name, rank):
    if ZOO[name][2].get("orders"):
        return []
    rule = ZOO[name][1]
    hits = [t for t in rank if ok(t) and rule(t)]
    if name in ("rand", "randrun"):
        return random.sample(hits, 1) if hits else []
    if name == "top1":
        return hits[:1]                   # the ranking is sorted by 5m volume
    ov = ZOO[name][2]
    if "rank_by" in ov:
        hits = sorted(hits, key=ov["rank_by"], reverse=True)[:ov["take"]]
    if ov.get("veto_rand"):
        st = json.loads(VETO_STATS.read_text()) if VETO_STATS.exists() else {}
        n = st.get("approve", 0) + st.get("reject", 0)
        rate = st["approve"] / n if n >= 5 else 0.5      # 50% until Grok has decided 5 candidates
        hits = [t for t in hits if random.random() < rate]
    return hits


VETO_QUEUE, VETO_STATS = HERE / "data" / "veto_queue.json", HERE / "data" / "veto_stats.json"


def queue_add(ps, rank_t):
    """Candidates of the veto test's rule for the Grok Bot routine: new mints only (one per 24 h), last 100 kept."""
    q = json.loads(VETO_QUEUE.read_text()) if VETO_QUEUE.exists() else []
    seen = {x["mint"] for x in q if rank_t - x["t"] < 86400}
    for t in ps:
        if t["address"] not in seen:
            q.append(dict(id=f"c{int(rank_t)}{len(q) % 1000:03d}", mint=t["address"], sym=t.get("symbol"), t=int(rank_t),
                          liq=round(f(t, "liquidity")), mcap=round(f(t, "market_cap")), h1=f(t, "price_change_percent1h"),
                          m5=f(t, "price_change_percent5m")))
            seen.add(t["address"])
    VETO_QUEUE.write_text(json.dumps(q[-100:], ensure_ascii=False, indent=0))


def cmd_init(thb):
    for name, (label, _, _) in ZOO.items():
        use(name)
        if not agents.STATE.exists():
            agents.cmd_init(thb)
            s = agents.load()
            s["label"] = f"สวนสัตว์: {label}"
            agents.save(s)
            print(f"init {name}")


DIE_N, PASS_N = 20, 50       # agent rules (14 Nov): dead at 20+ sells still below rand; passed at 50+ sells, positive after costs and above rand
CONTROLS = {"rand", "randrun"}


def trades(s):
    """Return of each closed position (all its sells, half-sells included, over its buy cost), so accounts with
    different trade sizes compare fairly. A position is closed once its coin is no longer held or was bought again."""
    open_, done = {}, []
    for x in s["log"]:
        m = x.get("mint")
        if x["kind"] == "buy":
            if m in open_:
                done.append(open_.pop(m))
            open_[m] = [x["usd"], 0.0, 0]
        elif x["kind"] == "sell" and m in open_:
            open_[m][1] += x.get("pnl", 0)
            open_[m][2] += 1
    done += [v for m, v in open_.items() if v[2] and m not in s.get("pos", {})]
    return [p / c for c, p, n in done if c and n]


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def verdict(name, s, rand_avg):
    """Marks the account dead or passed once (never un-marks) on the mean return per closed position against rand's.
    Dead accounts stop buying; exits keep running."""
    if name in CONTROLS or rand_avg is None or s.get("dead"):
        return
    tr, day = trades(s), agents.grok.now().date().isoformat()
    n, a = len(tr), mean(tr)
    if n >= DIE_N and a < rand_avg:
        s["dead"] = f"{day}: {n} ไม้ เฉลี่ยต่อไม้ {a:+.1%} แพ้ rand {rand_avg:+.1%}"
    elif n >= PASS_N and a > 0 and a > rand_avg and not s.get("passed"):
        s["passed"] = f"{day}: {n} ไม้ เฉลี่ยต่อไม้ {a:+.1%} ชนะ rand {rand_avg:+.1%} หลังหักค่าธรรมเนียม"


def apply_repairs():
    """One-off fixes shipped as data/repair_<name>.json {repair, state}: replace a bug-corrupted state once, under its lock, from the cloud run itself."""
    for fx in sorted((HERE / "data").glob("repair_*.json")):
        name, fix = fx.stem[7:], json.loads(fx.read_text())
        with lock(name):
            use(name)
            if agents.STATE.exists() and agents.load().get("repair") != fix["repair"]:
                agents.save({**fix["state"], "repair": fix["repair"]})
                print(f"repaired {name}: {fix['repair']}")


ORDER_MAX_S = 1800


def take_orders(name, s):
    """Grok chat picks pushed from the Mac: [{id, mint, sym, size, why, t}], each tried once, skipped if older than 30 min."""
    fx = HERE / "data" / f"orders_{name}.json"
    done = s.setdefault("orders_done", [])
    for o in (json.loads(fx.read_text()) if fx.exists() else []):
        if o["id"] in done:
            continue
        done.append(o["id"])
        age = time.time() - o["t"]
        agents.PER_TRADE = o["size"]
        why = f"order stale {age / 60:.0f} min" if age > ORDER_MAX_S else agents.paper_buy(s, o["mint"], o.get("sym"), zoo=name, why=o["why"][:200])
        if why:
            agents.log(s, "skip", mint=o["mint"], sym=o.get("sym"), why=why)


def cmd_tick():
    apply_repairs()
    d = json.loads(RANK.read_text()) if RANK.exists() else None
    rand_ret = None
    if "rand" in ZOO:
        use("rand")
        rand_ret = mean(trades(agents.load())) if agents.STATE.exists() else None
    if d:
        save_hist(d)
        breadth = sum(f(t, "price_change_percent1h") > 0 for t in d["rank"]) / max(len(d["rank"]), 1)
        for t in d["rank"]:
            t["breadth"] = breadth          # market-wide: share of ranked coins up over 1h, same for every coin this round
    for name in ZOO:
        try:
            tick_one(name, d, rand_ret)
        except Exception as e:                  # one bad account must not stop the round for the others
            print(f"zoo {name} error: {e!r}"[:200])


def tick_one(name, d, rand_ret):
    with lock(name):
        use(name)
        if not agents.STATE.exists():
            return
        s = agents.load()
        verdict(name, s, rand_ret)
        ov = ZOO[name][2]
        night = nightly.night_of(agents.grok.now())
        if ov.get("horizon") == "night":
            night_book(s, night)
        if d and d["t"] > s.get("rank_t", 0) and not ov.get("off") and not s.get("dead") and (night or ov.get("horizon") != "night"):
            s["rank_t"] = d["t"]
            ps = picks(name, d["rank"])
            if ov.get("queue"):
                queue_add(ps, d["t"])
            for t in ps:
                if "size" in ZOO[name][2]:
                    agents.PER_TRADE = ZOO[name][2]["size"](t)
                agents.paper_buy(s, t["address"], t.get("symbol"), zoo=name, smart=t.get("smart_degen_count"), kol=t.get("renowned_count"))
        if ov.get("orders") and not s.get("dead"):
            take_orders(name, s)
        agents.save(s)
        agents.cmd_run()


def cmd_watch(max_s, every=20, ws=20):
    """Exit checks every `every` s for the FAST accounts whose WATCH_S is `ws`, until the stop file appears or max_s passes."""
    names = [n for n in FAST if ZOO[n][2].get("WATCH_S", 20) == ws]
    LOCKS.mkdir(exist_ok=True)
    STOP_FILE.unlink(missing_ok=True)
    end = time.time() + float(max_s)
    while time.time() < end and not STOP_FILE.exists():
        try:                                    # fill the shared price pool once per round; each account then reads from it
            held = [m for n in names if (HERE / f"state_zoo_{n}.json").exists() for m in json.loads((HERE / f"state_zoo_{n}.json").read_text())["pos"]]
            agents.WATCH_S = ws
            if held:
                agents.dex_pairs(held)
                agents.jup_prices(held)
        except Exception as e:                  # a failed prefetch only means each account fetches for itself, as before
            print(f"watch prefetch error: {e!r}"[:200])
        for name in names:
            try:
                with lock(name):
                    use(name)
                    if agents.STATE.exists() and agents.load()["pos"]:
                        agents.cmd_run()
            except Exception as e:              # keep watching the other accounts
                print(f"watch {name} error: {e!r}"[:200])
        time.sleep(every)


def cmd_stopwatch():
    LOCKS.mkdir(exist_ok=True)
    STOP_FILE.touch()


def cmd_report():
    rows = []
    for name in ZOO:
        use(name)
        if agents.STATE.exists():
            s = agents.load()
            sells = [x["pnl"] for x in s["log"] if x["kind"] == "sell"]
            hz, tag = ZOO[name][2].get("horizon"), ""
            if hz == "night":
                n = s.get("nights", [])
                tag = f"  [{HORIZONS[hz]}: {len(n)} คืน บวก {sum(x['ret'] > 0 for x in n)}]"
            elif hz:
                due = datetime.fromisoformat(s["log"][0]["t"]) + timedelta(days=7 if hz == "week" else 30)
                tag = f"  [{HORIZONS[hz]}: ตัดสิน {due:%d/%m}]"
            tag += "".join(f"  [{k}: {s[k]}]" for k, k2 in (("dead", 0), ("passed", 0), ("halted", 0)) if s.get(k))
            tag += f"  [ห้ามเหรียญ: {' '.join(s['banned'].values())}]" if s.get("banned") else ""
            rows.append((agents.equity(s) / s["start_usd"] - 1, name, s.get("label", name) + tag, len(sells), sum(p > 0 for p in sells)))
    for r, name, label, n, w in sorted(rows, reverse=True):
        print(f"{r:+7.1%}  {name:8s} ไม้ {n:3d} ชนะ {w:3d}  {label}")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmds = {"init": lambda: cmd_init(a[1]), "tick": cmd_tick, "report": cmd_report, "watch": lambda: cmd_watch(a[1], float(a[2]), int(a[2])) if len(a) > 2 else cmd_watch(a[1]),
            "stopwatch": cmd_stopwatch}
    if not a or a[0] not in cmds:
        sys.exit(__doc__)
    cmds[a[0]]()
