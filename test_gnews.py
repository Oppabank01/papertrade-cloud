import gnews
from datetime import timedelta


def fresh():
    return {"label": "t", "start_thb": 500, "start_usd": 100.0, "cash": 100.0, "pos": {}, "log": []}


def value(s):
    return s["cash"] + sum(p["qty"] * p["last"] for p in s["pos"].values())


def test_long_and_short_pnl_match_cash():
    for side, exit_px, ret in (("long", 104.0, 0.04), ("short", 96.0, 0.04)):
        s = fresh()
        assert gnews.open_pos(s, "BTC", side, 100.0, "x")
        assert abs(value(s) - (100 - 20 * gnews.COST)) < 1e-9          # marked at entry: only the fee is gone
        assert not gnews.open_pos(s, "BTC", side, 100.0, "x")          # one position per coin
        gnews.exits(s, {"BTC": exit_px})
        sell = s["log"][-1]
        assert sell["kind"] == "sell" and not s["pos"]
        assert abs(s["cash"] - 100 - sell["pnl"]) < 1e-9               # logged pnl equals the cash change
        assert sell["pnl"] < 20 * ret                                  # fees came off


def test_time_exit_and_hold():
    s = fresh()
    gnews.open_pos(s, "ETH", "long", 100.0, "x")
    gnews.exits(s, {"ETH": 101.0})
    assert "ETH" in s["pos"]                                           # inside TP/SL, not expired: hold
    s["pos"]["ETH"]["t"] = (gnews.now - timedelta(hours=13)).isoformat()
    gnews.exits(s, {})                                                 # no price: hold even when expired
    assert "ETH" in s["pos"]
    gnews.exits(s, {"ETH": 101.0})
    assert not s["pos"] and s["log"][-1]["why"] == "หมดเวลา"


def test_outcomes_filled_once_due(tmp_path, monkeypatch):
    import json
    f = tmp_path / "d.jsonl"
    t0 = (gnews.now - timedelta(hours=5)).isoformat(timespec="minutes")
    f.write_text(json.dumps({"t": t0, "coin": "BTC", "price": 100.0}) + "\n" + json.dumps({"t": t0, "coin": "NONE", "price": None}) + "\n")
    monkeypatch.setattr(gnews, "DECISIONS", str(f))
    monkeypatch.setattr(gnews, "price_at", lambda coin, when: 102.0)
    gnews.fill_outcomes()
    a, b = [json.loads(l) for l in f.read_text().splitlines()]
    assert a["ret_1h"] == 0.02 and a["ret_4h"] == 0.02 and "ret_12h" not in a   # 12 h not due yet
    assert "ret_1h" not in b                                                     # no coin, nothing to grade
