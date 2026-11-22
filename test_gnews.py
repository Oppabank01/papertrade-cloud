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
