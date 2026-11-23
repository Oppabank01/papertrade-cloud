#!/usr/bin/env python3
"""Polymarket favourite ladder to x20, opened 23 Nov 2026 (idea ranked first by a Fable research pass). Fake money only.

Rides on poly_fav's live buys instead of placing its own: when idle, the ladder takes the newest poly_fav buy that is still
unresolved, priced 0.85-0.90 at the ask, ends within 6 h, and is not from the event of its previous step. It stakes the whole
ladder on it at that buy's cost per share (ask plus fee and slip, as poly_fav booked it). A YES at resolution multiplies the
ladder by 1/cost (about x1.13), a NO ends it at zero; at x20 it banks and starts again. One attempt = one trade, staking
1/20 of the start.
History (data/poly_fav_calib.json, 30 days, 91% sports, one random side per event, 20,000 runs): the 0.85-0.90 band won
92.6% at 1 h before the end (n 470, priced 0.872) and 92.1% at 6 h, so x20 (25 straight wins) came up in 9-13% of attempts,
against about 5% if prices were fair. The first calibration by total volume gave the opposite sign (0.85-0.97 won only 82.6%),
which would make this a fast way to zero. Control: fwd_x20 (a fair lottery) and the fair-price 5%.
  state_fwd_polyladder.json
  python3 fwd_polyladder.py"""
from byttrade import iso, load, save
import time

LO, HI, MAX_H, TARGET, UNITS = 0.85, 0.90, 6, 20, 20
LABEL = "Polymarket บันไดทบตัวเต็ง 0.85-0.90 จบใน 6 ชม. ทบทั้งก้อนทีละตลาดจนถึง x20 หรือหมด (รอบละ 1/20 ของทุน ไอเดียจาก Fable)"


def step(s, fav, now_iso):
    lad = s.get("lad")
    if lad and lad["token"]:
        done = [x for x in fav["log"] if x["kind"] == "sell" and x.get("token") == lad["token"]]
        if not done:
            return                                        # waiting for this step's market to resolve
        t = done[-1]["t"]
        if done[-1]["px"] >= 0.999:
            lad.update(v=lad["v"] / lad["cost"], wins=lad["wins"] + 1, token=None, after=t, last_event=lad["event"])
            if lad["v"] >= TARGET:
                s["cash"] += lad["unit"] * lad["v"]
                s["log"].append(dict(kind="sell", t=t, coin="ladder", px=1.0, usd=lad["unit"], ret=round(lad["v"] - 1, 6),
                                     pnl=lad["unit"] * (lad["v"] - 1), cost_side=0.012, why=f"ถึง x{lad['v']:.1f} ใน {lad['wins']} ขั้น"))
                s["lad"], s["after"] = None, t
        else:
            s["log"].append(dict(kind="sell", t=t, coin="ladder", px=0.0, usd=lad["unit"], ret=-1.0, pnl=-lad["unit"],
                                 cost_side=0.012, why=f"แพ้ที่ขั้น {lad['wins'] + 1} (ถึง x{lad['v']:.2f} แล้ว): {lad['coin'][:60]}"))
            s["lad"], s["after"] = None, t
    lad = s.get("lad")
    after, last_event = (lad["after"], lad["last_event"]) if lad else (s["after"], None)
    open_tokens = set(fav["pos"])                         # poly_fav keys open positions by token id
    pick = [x for x in fav["log"] if x["kind"] == "buy" and x["t"] > after and LO <= x["px"] < HI and x.get("end_h", 99) <= MAX_H
            and x.get("event") != last_event and x.get("token") in open_tokens]
    if not pick:
        return
    b = pick[-1]
    if lad is None:
        unit = s["start_usd"] / UNITS
        if s["cash"] < unit * 0.99:
            return                                        # lottery budget spent
        s["cash"] -= unit
        lad = s["lad"] = dict(v=1.0, wins=0, unit=unit, t=b["t"])
        s["log"].append(dict(kind="buy", t=b["t"], coin="ladder", px=b["px"], usd=unit, why="เริ่มบันไดใหม่"))
    lad.update(token=b["token"], event=b.get("event"), cost=b["usd"] / b["qty"], coin=b["coin"])


def main():
    fav = load("state_poly_fav.json", "")
    if not fav.get("log"):
        return
    s = load("state_fwd_polyladder.json", LABEL)
    if s.get("after") is None:
        s["after"] = iso(time.time() * 1000)              # only buys made after this account opened
    step(s, fav, iso(time.time() * 1000))
    save("state_fwd_polyladder.json", s)


if __name__ == "__main__":
    main()
