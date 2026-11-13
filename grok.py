#!/usr/bin/env python3
"""Paper trading Solana memecoins with the safety rules in RULES_GROK.md.
Grok (or anyone) only proposes a token. This script runs the safety filters,
sizes the trade and enforces stop, take-profit, time exit and loss limits.

  python3 grok.py init 300                # start with 300 THB of paper money
  python3 grok.py scan                    # GMGN 1h volume ranking -> filters -> lines to give Grok
  python3 grok.py check MINT              # run the safety filters only
  python3 grok.py buy MINT "reason"       # take a proposal (refused if any filter fails)
  python3 grok.py skip MINT "reason"      # log a proposal that was turned down
  python3 grok.py run                     # apply stop / take-profit / 24h exit at current prices
  python3 grok.py sell MINT "reason"      # manual exit
  python3 grok.py status
  python3 grok.py calib                   # judge calibration: win rate per probability bucket
  python3 grok.py ghost                   # follow every scanned coin for 24h without buying (auto.sh, 15 min)
  python3 grok.py ghost report            # would the cut coins have won or lost?
Standard library only. DexScreener, RugCheck, Binance TH need no key. GMGN uses a read-only
key from $GMGN_API_KEY (falls back to GMGN's public demo key); never give it a swap/private key.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEX = "https://api.dexscreener.com/tokens/v1/solana/"
# Pools paired with anything else (e.g. tokenized stocks) misprice the coin in SOL terms.
QUOTES = {"So11111111111111111111111111111111111111112",   # SOL
          "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
          "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}  # USDT
RUG = "https://api.rugcheck.xyz/v1/tokens/{}/report"
GMGN = "https://openapi.gmgn.ai"
# Read-only key from gmgn.ai/ai (no wallet, no swap). Falls back to GMGN's public demo key.
GMGN_KEY = os.environ.get("GMGN_API_KEY") or "gmgn_solbscbaseethmonadtron"
# Manipulation limits on GMGN's token stats (fractions). Values follow the middle tiers of
# GMGN's own gmgn-contract-dd skill, used here as hard fails.
GMGN_MAX = {
    # The *_trader_percentage and *_rate stats are shares of the traders GMGN analysed, not of supply.
    "top_bundler_trader_percentage": (0.15, "เทรดเดอร์ที่เป็นบอตซื้อพร้อมกัน (bundler)"),
    "top70_sniper_hold_rate": (0.05, "sniper ถือ"),
    "top_rat_trader_percentage": (0.01, "เทรดเดอร์ที่เป็น insider (rat trader)"),
    "top_entrapment_trader_percentage": (0.50, "เทรดเดอร์ที่เป็นกระเป๋าล่อ (entrapment)"),
    "bot_degen_rate": (0.50, "เทรดเดอร์ที่เป็นบอต"),
    "fresh_wallet_rate": (0.50, "เทรดเดอร์ที่เป็นกระเป๋าใหม่"),
    "creator_hold_rate": (0.05, "ผู้สร้างถือ"),
    "dev_team_hold_rate": (0.05, "ทีม dev ถือ"),
    "top_10_holder_rate": (0.50, "10 กระเป๋าใหญ่ถือ"),
}
FX = "https://api.binance.th/api/v1/ticker/price?symbol=USDTTHB"
FEE, SLIP = 0.01, 0.01                      # per side: bot fee, assumed slippage
PER_TRADE, MAX_POS = 0.10, 3                # share of equity per trade, open positions
STOP, TP, TP_SELL, MAX_HOLD_H = -0.08, 0.20, 0.5, 24
DAY_LOSS, KILL = -0.15, -0.50               # pause for the day, end the experiment
MIN_LIQ, MIN_AGE_H, MAX_PUMP_1H = 100_000, 24, 100
# v2 (12 Nov 2026, research_notes/github-memecoin-strategies-2026-11-12.md): entry gate + loss-cutting exits.
MIN_BUY_SELL_N = 1.3                        # buys/sells count, last 1h
H1_RANGE, MIN_H24, MAX_DROP_5M = (0, 30), -20, -0.05   # % / % / fraction vs price 5 min ago
VOL_LIQ_RANGE, MIN_VOL1H_LIQ = (0.15, 12), 0.02
LIQ_EXIT = -0.30                            # sell all if pool liquidity falls 30% from entry
BE_TRIGGER, BE_STOP = 0.10, 0.04            # after +10% seen, stop moves to entry +4% (covers costs)
TRAIL = 0.15                                # after half is sold, sell rest 15% below the peak
STALL_H, STALL_MIN = 6, 0.05                # 6h without ever reaching +5%: sell
# JUDGE (idea from @x_insider4's "Jev" seat): a closed-question model answers, fixed code decides.
JUDGE_BUY, JUDGE_ORGANIC, JUDGE_LATE_MAX, JUDGE_EXIT_MAX = 0.70, 0.65, 0.50, 2.0
JUDGE_Q = {
    "organic": {"type": "noul", "instructions": "Holders and price are rising because of many independent buyers, not one wallet walking the price up."},
    "late": {"type": "noul", "instructions": "Most of the price move already happened before now."},
    "exit_risk": {"type": "score", "instructions": "How hard would it be to sell a $1 position quickly without moving the price?",
                  "criteria": ["deep liquidity, trivial to exit", "easy", "moderate", "hard", "the position would be a big part of the pool"]},
    "action": {"type": "choice", "instructions": "Decide on a short-term (24h) paper trade with -8% stop and +20% take-profit.",
               "criteria": {"buy": "clean setup with net buying, enter now", "watch": "interesting but not yet", "pass": "no"}},
}
_laya = None
# Shadow rules (log only, never block): ideas from YouTube research 12 Nov 2026, measured before adoption.
SH_MIN_AVG_TRADE, SH_MIN_LIQ_MCAP, SH_VAMP_MCAP, SH_HOLDER_DROP = 15, 0.15, 500_000, -0.10
STATE = Path(__file__).with_name("state_grok_v2.json")   # v1 archived in state_grok.json
GHOSTS = Path(__file__).with_name("ghosts_grok.json")     # coins seen by scan, followed 24h without buying
TH = timezone(timedelta(hours=7))


def get(url, tries=2):
    req = urllib.request.Request(url, headers={"User-Agent": "papertrade/1.0"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2)


def now():
    return datetime.now(TH)


def usdthb():
    return float(get(FX)["price"])


def pair(mint):
    """Deepest Solana pool for the token, or None."""
    pools = [p for p in get(DEX + mint) if p.get("chainId") == "solana"]
    return max(pools, key=lambda p: (p.get("liquidity") or {}).get("usd", 0), default=None)


def px(mint):
    p = pair(mint)
    return float(p["priceUsd"]) if p and p.get("priceUsd") else None


def gm(path, **q):
    """GMGN read-only call. Returns the payload or raises."""
    q.update(timestamp=int(time.time()), client_id=str(uuid.uuid4()))
    url = GMGN + path + "?" + urllib.parse.urlencode(q, doseq=True)
    req = urllib.request.Request(url, headers={"X-APIKEY": GMGN_KEY, "User-Agent": "papertrade/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    if d.get("code") != 0:
        raise RuntimeError(d.get("message") or d)
    return d["data"]


def gmgn_fails(mint):
    """Manipulation checks from GMGN. Any error counts as a fail, never as a pass."""
    try:
        info, sec = gm("/v1/token/info", chain="sol", address=mint), gm("/v1/token/security", chain="sol", address=mint)
    except Exception as e:
        return [f"ตรวจ GMGN ไม่ได้ ({str(e)[:60]})"], {}
    stat = info.get("stat") or {}
    fails = []
    for k, (lim, label) in GMGN_MAX.items():
        v = float(stat.get(k) or sec.get(k) or 0)
        if v > lim:
            fails.append(f"{label} {v:.1%} เกิน {lim:.0%}")
    if sec.get("is_honeypot") or sec.get("honeypot") or sec.get("can_not_sell"):
        fails.append("GMGN: ขายไม่ได้ (honeypot)")
    dev = info.get("dev") or {}
    tags = info.get("wallet_tags_stat") or {}
    notes = dict(smart=tags.get("smart_wallets"), kol=tags.get("renowned_wallets"),
                 paid_boost=bool(dev.get("dexscr_boost_fee") or dev.get("dexscr_ad")),
                 holders=info.get("holder_count"), price=info.get("price") or {})
    return fails, notes


def check(mint):
    """Return (passed, symbol, price_usd, list of failed rules, notes)."""
    p, r = pair(mint), get(RUG.format(mint))
    if not p:
        return False, "?", None, ["ไม่เจอ pool บน Solana"], {}
    fails = []
    liq = (p.get("liquidity") or {}).get("usd", 0)
    age_h = (time.time() * 1000 - (p.get("pairCreatedAt") or time.time() * 1000)) / 3.6e6
    pump = (p.get("priceChange") or {}).get("h1", 0) or 0
    danger = [x["name"] for x in r.get("risks") or [] if x.get("level") == "danger"]
    quote = (p.get("quoteToken") or {})
    if quote.get("address") not in QUOTES:
        fails.append(f"pool หลักจับคู่กับ {quote.get('symbol') or '?'} ไม่ใช่ SOL/USDC/USDT")
    if liq < MIN_LIQ:
        fails.append(f"สภาพคล่อง ${liq:,.0f} ต่ำกว่า ${MIN_LIQ:,}")
    if age_h < MIN_AGE_H:
        fails.append(f"pool อายุ {age_h:.1f} ชม. ไม่ถึง {MIN_AGE_H}")
    if pump > MAX_PUMP_1H:
        fails.append(f"พุ่ง {pump:.0f}% ใน 1 ชม.")
    if r.get("mintAuthority"):
        fails.append("ยังมีสิทธิ์ mint")
    if r.get("freezeAuthority"):
        fails.append("ยังมีสิทธิ์ freeze")
    if r.get("rugged"):
        fails.append("RugCheck ระบุว่า rugged")
    # Holder concentration, insiders and unlocked LP come from RugCheck's own danger flags:
    # raw top-10 counts unlabeled exchange wallets and rejects even BONK and WIF.
    fails += [f"RugCheck danger: {d}" for d in danger]
    gf, notes = gmgn_fails(mint)
    ef = entry_fails(p, notes.get("price"))
    if notes:
        notes["entry"] = ef   # lets the ghost log tell entry-gate cuts from safety cuts
    fails += gf + ef
    return not fails, p["baseToken"]["symbol"], float(p["priceUsd"]), fails, notes


def entry_fails(p, g):
    """v2 entry gate: real net buying, no falling knife, no chasing, pool neither dead nor wash-traded."""
    if not g:
        return ["ไม่มีข้อมูลแรงซื้อขายจาก GMGN"]
    f, num = [], lambda k: float(g.get(k) or 0)
    ch, vol, tx = p.get("priceChange") or {}, p.get("volume") or {}, (p.get("txns") or {}).get("h1") or {}
    liq = (p.get("liquidity") or {}).get("usd") or 1
    for h in ("1h", "6h"):
        if num(f"buy_volume_{h}") <= num(f"sell_volume_{h}"):
            f.append(f"แรงซื้อสุทธิ {h} ไม่เป็นบวก")
    if (tx.get("buys") or 0) < MIN_BUY_SELL_N * max(tx.get("sells") or 0, 1):
        f.append(f"ซื้อ/ขาย 1 ชม. {tx.get('buys')}/{tx.get('sells')} ต่ำกว่า {MIN_BUY_SELL_N}")
    if num("price_5m") and num("price") / num("price_5m") - 1 < MAX_DROP_5M:
        f.append("ราคาร่วงเกิน 5% ใน 5 นาที")
    if not H1_RANGE[0] <= (ch.get("h1") or 0) <= H1_RANGE[1]:
        f.append(f"ราคา 1 ชม. {ch.get('h1')}% นอกช่วง {H1_RANGE[0]} ถึง {H1_RANGE[1]}%")
    if (ch.get("h24") or 0) <= MIN_H24:
        f.append(f"ราคา 24 ชม. {ch.get('h24')}% ลงเกิน {-MIN_H24}%")
    r = (vol.get("h24") or 0) / liq
    if not VOL_LIQ_RANGE[0] <= r <= VOL_LIQ_RANGE[1]:
        f.append(f"วอลุ่ม 24 ชม./สภาพคล่อง {r:.2f} นอกช่วง {VOL_LIQ_RANGE[0]} ถึง {VOL_LIQ_RANGE[1]}")
    if (vol.get("h1") or 0) < MIN_VOL1H_LIQ * liq:
        f.append("วอลุ่ม 1 ชม. ต่ำกว่า 2% ของสภาพคล่อง")
    return f


def judge(p, g, notes):
    """Ask the local laya model the four closed questions on a facts-only dossier. Returns (passed, verdict)."""
    global _laya
    try:
        if _laya is None:
            import laya  # heavy (~17 s, 1-2 GB), so only when a coin reaches the judge
            _laya = laya.load()
        ch, tx = p.get("priceChange") or {}, (p.get("txns") or {}).get("h1") or {}
        dossier = {  # facts only; a missing field says "missing", never a guess
            "age_days": round((time.time() * 1000 - (p.get("pairCreatedAt") or 0)) / 8.64e7, 1),
            "market_cap_usd": p.get("marketCap") or "missing", "liquidity_usd": (p.get("liquidity") or {}).get("usd") or "missing",
            "price_change_pct": {k: ch.get(k, "missing") for k in ("m5", "h1", "h6", "h24")},
            "buys_sells_count_1h": f"{tx.get('buys', 'missing')}/{tx.get('sells', 'missing')}",
            "buy_vs_sell_volume_usd_1h": f"{g.get('buy_volume_1h', 'missing')}/{g.get('sell_volume_1h', 'missing')}",
            "buy_vs_sell_volume_usd_6h": f"{g.get('buy_volume_6h', 'missing')}/{g.get('sell_volume_6h', 'missing')}",
            "holders": notes.get("holders") or "missing",
            "safety_checks": "passed: mint/freeze revoked, no RugCheck danger, GMGN bundler/insider/sniper/dev limits",
        }
        a = _laya.predict(dossier, JUDGE_Q)["answers"]
    except Exception as e:  # no answer is not a yes
        return False, {"error": str(e)[:80]}
    v = dict(buy=a["action"]["probabilities"]["buy"], choice=a["action"]["choice"], organic=a["organic"]["noul"],
             late=a["late"]["noul"], exit_risk=a["exit_risk"]["score"])
    ok = (v["choice"] == "buy" and v["buy"] >= JUDGE_BUY and v["organic"] >= JUDGE_ORGANIC
          and v["late"] < JUDGE_LATE_MAX and v["exit_risk"] <= JUDGE_EXIT_MAX)
    return ok, v


def shadow_flags(p, mint):
    """Log-only checks: tiny average trade (volume bots), thin pool vs market cap, a bigger same-symbol copycat."""
    f = []
    tx, vol = (p.get("txns") or {}).get("h1") or {}, p.get("volume") or {}
    n = (tx.get("buys") or 0) + (tx.get("sells") or 0)
    if n and (vol.get("h1") or 0) / n < SH_MIN_AVG_TRADE:
        f.append(f"avg_trade ${(vol.get('h1') or 0) / n:.1f}")
    mc, liq = p.get("marketCap") or 0, (p.get("liquidity") or {}).get("usd") or 0
    if mc and liq / mc < SH_MIN_LIQ_MCAP:
        f.append(f"liq/mcap {liq / mc:.2f}")
    sym = (p.get("baseToken") or {}).get("symbol") or ""
    try:
        for o in get("https://api.dexscreener.com/latest/dex/search?q=" + urllib.parse.quote(sym)).get("pairs") or []:
            ov = o.get("volume") or {}
            if (o.get("chainId") == "solana" and (o.get("baseToken") or {}).get("symbol", "").lower() == sym.lower()
                    and o["baseToken"].get("address") != mint and (o.get("marketCap") or 0) > SH_VAMP_MCAP
                    and (ov.get("h1") or 0) * 6 > (ov.get("h6") or 0)):
                f.append(f"vamp {o['baseToken']['address'][:6]}")
                break
    except Exception:
        f.append("vamp_check_failed")
    return f


def load():
    if not STATE.exists():
        sys.exit("ยังไม่มีบัญชี รัน: python3 grok.py init 300")
    return json.loads(STATE.read_text())


def save(s):
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1))


def equity(s, prices=None):
    prices = prices or {}
    return s["cash"] + sum(q["qty"] * prices.get(m, q["last"]) for m, q in s["pos"].items())


def log(s, kind, mint, **kw):
    s["log"].append(dict(t=now().isoformat(timespec="seconds"), kind=kind, mint=mint, **kw))


def roll_day(s, eq):
    today = now().strftime("%Y-%m-%d")
    if s.get("day") != today:
        s["day"], s["day_start"] = today, eq


def close(s, mint, price, frac, why):
    q = s["pos"][mint]
    qty = q["qty"] * frac
    got = qty * price * (1 - SLIP) * (1 - FEE)
    s["cash"] += got
    q["qty"] -= qty
    pnl = got - q["cost"] * frac
    q["cost"] *= 1 - frac
    log(s, "sell", mint, sym=q["sym"], price=price, usd=round(got, 4), pnl=round(pnl, 4), why=why)
    if frac >= 1 or q["qty"] <= 0:
        del s["pos"][mint]
    return pnl


def blocked(s, eq):
    if s.get("ended"):
        return "จบการทดลองแล้ว (ทุนหายถึงเกณฑ์ -50%)"
    if eq <= s["start_usd"] * (1 + KILL):
        s["ended"] = True
        return "ทุนหายถึง -50% จบการทดลอง ห้ามเติมเงิน"
    if eq <= s["day_start"] * (1 + DAY_LOSS):
        return "ขาดทุนวันนี้เกิน 15% หยุดซื้อถึงพรุ่งนี้"
    return None


def cmd_init(thb):
    if STATE.exists():
        sys.exit(f"มีบัญชีอยู่แล้ว ลบ {STATE.name} เองถ้าจะเริ่มใหม่")
    rate = usdthb()
    usd = float(thb) / rate
    s = dict(start_thb=float(thb), start_usd=usd, cash=usd, pos={}, log=[], ended=False)
    roll_day(s, usd)
    log(s, "init", "-", thb=float(thb), usdthb=rate)
    save(s)
    print(f"เปิดบัญชีจำลอง {thb} บาท = ${usd:.2f} (USDTTHB {rate})")


def cmd_check(mint):
    ok, sym, price, fails, notes = check(mint)
    print(f"{sym} ${price}" if price else mint)
    print("ผ่านทุกข้อ" if ok else "ไม่ผ่าน:\n  " + "\n  ".join(fails))
    if notes:
        print(f"  smart money {notes['smart']} KOL {notes['kol']} holders {notes['holders']}"
              + (" | จ่ายเงินโปรโมตบน DexScreener" if notes["paid_boost"] else ""))
    return ok


def cmd_scan():
    """Candidates from GMGN's 1h volume ranking (not paid boosts), full check, one Grok-ready line each."""
    rank = gm("/v1/market/rank", chain="sol", interval="1h", limit=100, order_by="volume", direction="desc",
              filters=["renounced", "frozen", "not_wash_trading"])
    rank = (rank.get("data") or rank).get("rank", [])
    cut = time.time() - MIN_AGE_H * 3600
    pre = [t for t in rank if float(t.get("liquidity") or 0) >= MIN_LIQ and (t.get("open_timestamp") or 1e12) <= cut]
    print(f"GMGN 1h ติดอันดับ {len(rank)} ตัว ผ่านสภาพคล่อง/อายุ {len(pre)} ตัว ตรวจละเอียด...")
    lines, seen = [], []
    for t in pre:
        try:
            ok, sym, price, fails, notes = check(t["address"])
        except Exception as e:  # one flaky API call must not kill the scan; unchecked = not passed
            print(f"  ข้าม {t.get('symbol')}: ตรวจไม่ได้ ({str(e)[:50]})")
            continue
        if not ok:
            print(f"  ตัด {sym}: {fails[0]}" + (f" (+{len(fails) - 1})" if len(fails) > 1 else ""))
            stage = "entry" if notes and set(fails) <= set(notes.get("entry") or []) else "safety"
            seen.append((t["address"], sym, price, stage, fails[0]))
            continue
        p = pair(t["address"])
        print(f"  shadow {sym}: {shadow_flags(p, t['address']) or 'ไม่มีธง'}")
        jok, verdict = judge(p, notes.get("price"), notes)
        print(f"  กรรมการ {sym}: {'ผ่าน' if jok else 'ไม่ผ่าน'} {verdict}")
        seen.append((t["address"], sym, price, "pass" if jok else "judge", str(verdict)[:80]))
        if not jok:
            continue
        ch, v, tx = p.get("priceChange") or {}, p.get("volume") or {}, (p.get("txns") or {}).get("h1") or {}
        lines.append(f"{sym} mint {t['address']}: mcap ${p.get('marketCap') or 0:,.0f} liq ${p['liquidity']['usd']:,.0f} "
                     f"อายุ {(time.time() * 1000 - p['pairCreatedAt']) / 8.64e7:.0f} วัน ราคา m5 {ch.get('m5')}% h1 {ch.get('h1')}% "
                     f"h6 {ch.get('h6')}% h24 {ch.get('h24')}% vol h1 ${v.get('h1', 0):,.0f} h24 ${v.get('h24', 0):,.0f} "
                     f"txns h1 {tx.get('buys')}/{tx.get('sells')} holders {notes['holders']}"
                     + (" จ่ายโปรโมต" if notes["paid_boost"] else ""))
    print(f"\nผ่านทุกข้อ {len(lines)} ตัว:\n" + "\n\n".join(lines))
    ghost_add(seen)
    return lines


def ghost_load():
    return json.loads(GHOSTS.read_text()) if GHOSTS.exists() else []


def ghost_add(seen):
    """Remember every coin the scan judged, at its scan price, so `ghost` can see what it would have done."""
    g = ghost_load()
    open_ = {x["mint"] for x in g if not x.get("out")}
    t = time.time()
    g += [dict(mint=m, sym=sym, stage=st, why=why, t0=t, p0=p, hi=p, lo=p, last=p, out=None)
          for m, sym, p, st, why in seen if p and m not in open_]
    GHOSTS.write_text(json.dumps(g, ensure_ascii=False, indent=0))


def ghost_out(x, price, age_h):
    """Outcome under the base exits: -8% stop or +20% target, whichever is seen first, else 24h close."""
    if price is None:
        return "rug"
    r = price / x["p0"] - 1
    return "stop" if r <= STOP else "tp" if r >= TP else "end" if age_h >= MAX_HOLD_H else None


def cmd_ghost_update():
    # shortcut: prices sampled every 15 min, so a move that crosses both -8% and +20% between samples counts by
    # the sampled price; good enough to compare groups, not to measure a single coin.
    g = ghost_load()
    live = [x for x in g if not x.get("out")]
    for i in range(0, len(live), 30):  # DexScreener takes up to 30 addresses per call
        chunk = live[i:i + 30]
        try:
            pools = get(DEX + ",".join(x["mint"] for x in chunk))
        except Exception:
            continue
        best = {}
        for p in pools:
            m = (p.get("baseToken") or {}).get("address")
            if p.get("chainId") == "solana" and p.get("priceUsd") and \
                    (p.get("liquidity") or {}).get("usd", 0) >= (best.get(m, {}).get("liquidity") or {}).get("usd", -1):
                best[m] = p
        for x in chunk:
            price = float(best[x["mint"]]["priceUsd"]) if x["mint"] in best else None
            if price is None and not x.get("miss"):  # one missing reply may be DexScreener, two in a row is a rug
                x["miss"] = 1
                continue
            if price:
                x.update(last=price, hi=max(x["hi"], price), lo=min(x["lo"], price))
            x["out"] = ghost_out(x, price, (time.time() - x["t0"]) / 3600)
            if x["out"]:
                x["ret"] = -1.0 if x["out"] == "rug" else price / x["p0"] - 1
    GHOSTS.write_text(json.dumps(g, ensure_ascii=False, indent=0))


def ghost_score(x):
    """Return of one ghost trade after fees and slippage both ways."""
    gross = {"stop": STOP, "tp": TP, "rug": -1.0}.get(x["out"], x.get("ret", 0))
    return (1 + gross) * ((1 - FEE) * (1 - SLIP)) ** 2 - 1


def cmd_ghost_report():
    g = ghost_load()
    names = {"pass": "ผ่านกฎ+กรรมการ", "judge": "กรรมการตัด", "entry": "จุดเข้าตัด", "safety": "กฎความปลอดภัยตัด"}
    print(f"เหรียญที่ติดตาม {len(g)} ตัว ยังเปิดอยู่ {sum(not x.get('out') for x in g)}")
    for st, label in names.items():
        d = [x for x in g if x["stage"] == st and x.get("out")]
        if not d:
            print(f"{label}: ยังไม่มีตัวที่ครบผล")
            continue
        c = {k: sum(x["out"] == k for x in d) for k in ("tp", "stop", "end", "rug")}
        avg = sum(map(ghost_score, d)) / len(d)
        best = max(d, key=lambda x: x["hi"] / x["p0"])
        print(f"{label}: {len(d)} ตัว ถึง +20% {c['tp']} ชน stop {c['stop']} ครบ 24 ชม. {c['end']} rug {c['rug']} "
              f"เฉลี่ยต่อไม้หลังค่าธรรมเนียม {avg:+.1%} วิ่งสุด {best['sym']} {best['hi'] / best['p0'] - 1:+.0%}")


def cmd_buy(mint, why):
    s = load()
    eq = equity(s)
    roll_day(s, eq)
    stop = blocked(s, eq)
    if stop or mint in s["pos"] or len(s["pos"]) >= MAX_POS:
        save(s)
        sys.exit(stop or ("ถือเหรียญนี้อยู่แล้ว ห้ามซื้อถัว" if mint in s["pos"] else f"ถือครบ {MAX_POS} ตัวแล้ว"))
    ok, sym, price, fails, notes = check(mint)
    p0 = pair(mint) or {}
    liq0 = (p0.get("liquidity") or {}).get("usd") or 0
    if not ok:
        log(s, "refused", mint, sym=sym, why=why, fails=fails)
        save(s)
        sys.exit("ไม่ซื้อ กฎไม่ผ่าน:\n  " + "\n  ".join(fails))
    jok, verdict = judge(p0, notes.get("price"), notes)
    log(s, "judge", mint, sym=sym, price=price, ok=jok, **verdict)
    log(s, "shadow", mint, sym=sym, flags=shadow_flags(p0, mint))
    if not jok:
        save(s)
        sys.exit(f"ไม่ซื้อ กรรมการ laya ไม่ผ่าน: {verdict}")
    spend = min(eq * PER_TRADE, s["cash"])
    qty = spend * (1 - FEE) * (1 - SLIP) / price
    s["cash"] -= spend
    s["pos"][mint] = dict(sym=sym, qty=qty, entry=price, cost=spend, last=price,
                          opened=now().isoformat(timespec="seconds"), tp_done=False, liq0=liq0, peak=price, holders0=notes.get("holders") or 0)
    log(s, "buy", mint, sym=sym, price=price, usd=round(spend, 4), why=why)
    save(s)
    print(f"ซื้อ {sym} ${spend:.2f} ที่ ${price} stop ${price * (1 + STOP):.8g} ขายครึ่งที่ ${price * (1 + TP):.8g}\n"
          "ระหว่างถือต้องรัน run ทุก 15 นาที")


def cmd_skip(mint, why):
    s = load()
    log(s, "skip", mint, why=why)
    save(s)
    print("จดไว้แล้ว")


def cmd_run():
    s = load()
    for mint, q in list(s["pos"].items()):
        p = pair(mint)
        if not p or not p.get("priceUsd"):
            # shortcut: no Solana pool left counts as a rug, sold at 0; check by eye if DexScreener was just flaky
            close(s, mint, 0.0, 1, "pool หาย ถือว่า rug")
            continue
        price, liq = float(p["priceUsd"]), (p.get("liquidity") or {}).get("usd") or 0
        q["last"], q["peak"] = price, max(q.get("peak", q["entry"]), price)
        chg, peak_chg = price / q["entry"] - 1, q["peak"] / q["entry"] - 1
        held_h = (now() - datetime.fromisoformat(q["opened"])).total_seconds() / 3600
        if q.get("holders0") and not q.get("shadow_exit"):
            try:
                h = gm("/v1/token/info", chain="sol", address=mint).get("holder_count") or 0
                if h and h / q["holders0"] - 1 <= SH_HOLDER_DROP:
                    q["shadow_exit"] = True
                    log(s, "shadow_exit", mint, sym=q["sym"], price=price, holders=h, holders0=q["holders0"])
            except Exception:
                pass
        if q.get("liq0") and liq / q["liq0"] - 1 <= LIQ_EXIT:
            close(s, mint, price, 1, f"สภาพคล่องลด {liq / q['liq0'] - 1:+.0%} ({chg:+.1%})")
        elif chg <= STOP:
            close(s, mint, price, 1, f"stop {chg:+.1%}")
        elif peak_chg >= BE_TRIGGER and chg <= BE_STOP:
            close(s, mint, price, 1, f"stop ทุน หลังเคยขึ้น {peak_chg:+.1%} ({chg:+.1%})")
        elif q["tp_done"] and price <= q["peak"] * (1 - TRAIL):
            close(s, mint, price, 1, f"trailing ลง {TRAIL:.0%} จากยอด ({chg:+.1%})")
        elif held_h >= MAX_HOLD_H:
            close(s, mint, price, 1, f"ครบ {MAX_HOLD_H} ชม. ({chg:+.1%})")
        elif held_h >= STALL_H and peak_chg < STALL_MIN:
            close(s, mint, price, 1, f"ถือ {STALL_H} ชม. ไม่เคยถึง +{STALL_MIN:.0%} ({chg:+.1%})")
        elif chg >= TP and not q["tp_done"]:
            close(s, mint, price, TP_SELL, f"ขายครึ่งที่ {chg:+.1%}")
            q["tp_done"] = True
    eq = equity(s)
    roll_day(s, eq)
    note = blocked(s, eq)
    save(s)
    cmd_status(s)
    if note:
        print(note)


def cmd_sell(mint, why):
    s = load()
    if mint not in s["pos"]:
        sys.exit("ไม่ได้ถือเหรียญนี้")
    price = px(mint) or s["pos"][mint]["last"]
    pnl = close(s, mint, price, 1, why)
    save(s)
    print(f"ขายแล้ว กำไร/ขาดทุน ${pnl:+.4f}")


def cmd_calib():
    """Weekly honesty check: do higher judge probabilities actually win more often?"""
    s = load()
    pnl = {}
    for x in s["log"]:
        if x["kind"] == "sell":
            pnl[x["mint"]] = pnl.get(x["mint"], 0) + x["pnl"]
    buys = [x for x in s["log"] if x["kind"] == "judge" and x.get("ok") and x["mint"] in pnl]
    for lo, hi in ((0.7, 0.8), (0.8, 0.9), (0.9, 1.01)):
        b = [x for x in buys if lo <= x["buy"] < hi]
        print(f"buy {lo:.2f}-{min(hi, 1):.2f}: {len(b)} ไม้ ชนะ {sum(pnl[x['mint']] > 0 for x in b)}")
    print(f"กรรมการตัดไป {sum(1 for x in s['log'] if x['kind'] == 'judge' and not x.get('ok'))} ครั้ง")
    flagged = {x["mint"]: x["flags"] for x in s["log"] if x["kind"] == "shadow" and x["mint"] in pnl}
    for label, ms in (("มีธง shadow", [m for m, f in flagged.items() if f]), ("ไม่มีธง", [m for m, f in flagged.items() if not f])):
        print(f"{label}: {len(ms)} ไม้ ชนะ {sum(pnl[m] > 0 for m in ms)} รวม ${sum(pnl[m] for m in ms):+.4f}")
    ex = {x["mint"]: x["price"] for x in s["log"] if x["kind"] == "shadow_exit"}
    if ex:
        print(f"holder ลด 10% ระหว่างถือ {len(ex)} ไม้ ถ้าขายตอนนั้น vs ผลจริง: ดูใน log kind=shadow_exit")


def cmd_status(s=None):
    s = s or load()
    rate = usdthb()
    eq = equity(s)
    print(f"พอร์ต ${eq:.2f} = {eq * rate:,.2f} บาท ({eq / s['start_usd'] - 1:+.1%}) เงินสด ${s['cash']:.2f}")
    for m, q in s["pos"].items():
        print(f"  {q['sym']}: ทุน ${q['cost']:.2f} เข้า ${q['entry']:.8g} ล่าสุด ${q['last']:.8g} "
              f"({q['last'] / q['entry'] - 1:+.1%}) เปิดเมื่อ {q['opened']}")
    sells = [x for x in s["log"] if x["kind"] == "sell"]
    if sells:
        wins = sum(x["pnl"] > 0 for x in sells)
        print(f"ขายไปแล้ว {len(sells)} ครั้ง ชนะ {wins} รวม ${sum(x['pnl'] for x in sells):+.4f}")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmds = {"init": lambda: cmd_init(a[1]), "check": lambda: cmd_check(a[1]), "scan": cmd_scan,
            "buy": lambda: cmd_buy(a[1], a[2]), "skip": lambda: cmd_skip(a[1], a[2]),
            "run": cmd_run, "calib": cmd_calib,
            "ghost": lambda: cmd_ghost_report() if a[1:] == ["report"] else cmd_ghost_update(), "sell": lambda: cmd_sell(a[1], a[2]), "status": cmd_status}
    if not a or a[0] not in cmds:
        sys.exit(__doc__)
    cmds[a[0]]()
