import lens
from datetime import timedelta


def acct():
    return dict(start_usd=100.0, cash=100.0, pos={}, log=[])


def bar(t_ms, h, l, c):
    return dict(t=t_ms, o=c, h=h, l=l, c=c, v=1, closed=True)


def test_stop_first_and_cash_matches_pnl():
    s = acct()
    lens.open_pos(s, "BTCUSDT", "long", 100.0, 2.0, "x")          # stop 97, target 104.5
    p = s["pos"]["BTCUSDT"]
    assert (p["stop"], p["tgt"]) == (97.0, 104.5)
    t = int(lens.datetime.fromisoformat(p["t"]).timestamp() * 1000)
    lens.exits(s, {"BTCUSDT": [bar(t, 105, 96, 100)]})             # both touched in one bar: stop
    assert not s["pos"] and s["log"][-1]["why"] == "stop"
    assert abs(s["cash"] - 100 - s["log"][-1]["pnl"]) < 1e-9


def test_short_target_and_time_exit():
    s = acct()
    lens.open_pos(s, "ETHUSDT", "short", 100.0, 2.0, "x")         # stop 103, target 95.5
    t = int(lens.datetime.fromisoformat(s["pos"]["ETHUSDT"]["t"]).timestamp() * 1000)
    lens.exits(s, {"ETHUSDT": [bar(t, 101, 95, 96)]})
    assert s["log"][-1]["why"] == "ถึงเป้า 1.5R" and s["log"][-1]["pnl"] > 0
    lens.open_pos(s, "SOLUSDT", "long", 100.0, 2.0, "x")
    s["pos"]["SOLUSDT"]["t"] = (lens.now - timedelta(hours=49)).isoformat(timespec="seconds")
    t = int(lens.datetime.fromisoformat(s["pos"]["SOLUSDT"]["t"]).timestamp() * 1000)
    lens.exits(s, {"SOLUSDT": [bar(t, 101, 99, 100.5)]})
    assert s["log"][-1]["why"] == "ครบ 48 ชม."


def test_score_shape():
    b = [dict(t=i, o=100 + i, h=101 + i, l=99 + i, c=100.5 + i, v=1 + (5 if i == 79 else 0)) for i in range(80)]
    sc = lens.score(b)
    assert sc["long"] == 100 and sc["short"] == 0 and sc["path"][-1] == 0.0
