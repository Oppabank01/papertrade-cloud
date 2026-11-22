#!/usr/bin/env python3
"""Offline: buys_in detects SOL->token and USDC->token buys, ignores sells and failed tx."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import wallets
W, M, USDC = "Wal1111111111111111111111111111111111111111", "Mint111111111111111111111111111111111111111", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
tb = lambda mint, amt: {"owner": W, "mint": mint, "uiTokenAmount": {"uiAmount": amt}}
def tx(pre, post, sol_pre, sol_post, err=None):
    return {"meta": {"err": err, "preTokenBalances": pre, "postTokenBalances": post, "preBalances": [sol_pre], "postBalances": [sol_post]},
            "transaction": {"message": {"accountKeys": [{"pubkey": W}]}}}
b = wallets.buys_in(tx([], [tb(M, 1000)], 3e9, 1e9), W, 150)            # spent 2 SOL
assert b == [(M, 300.0)], b
b = wallets.buys_in(tx([tb(USDC, 500)], [tb(USDC, 100), tb(M, 50)], 1e9, 1e9), W, 150)
assert b == [(M, 400.0)], b
assert wallets.buys_in(tx([tb(M, 1000)], [], 1e9, 3e9), W, 150) == []   # a sell
assert wallets.buys_in(tx([], [tb(M, 1)], 3e9, 1e9, err={"x": 1}), W, 150) == []
print("wallets ok")

# mirror exits: a leader's sell closes only the position we copied from that leader
import importlib, os as _os
_os.environ["WALLET_LIST"] = "fomo_mirror"
wm = importlib.reload(wallets)
assert wm.MIRROR and wm.agents.STOP == -0.25 and wm.agents.PER_TRADE == 0.10
L = "LeaderWallet1111111111111111111111111111111"
sell_tx = {"meta": {"err": None, "preTokenBalances": [{"owner": L, "mint": "MintA", "uiTokenAmount": {"uiAmount": 100}}],
                    "postTokenBalances": [{"owner": L, "mint": "MintA", "uiTokenAmount": {"uiAmount": 0}}]}}
assert wm.sold_in(sell_tx, L) == ["MintA"] and wm.sold_in(sell_tx, "Other") == []
st = {"cash": 0.0, "pos": {"MintA": dict(sym="A", qty=10.0, entry=1.0, last=1.0, peak=1.0, cost=10.0, wallet=L[:6]),
                           "MintB": dict(sym="B", qty=10.0, entry=1.0, last=1.0, peak=1.0, cost=10.0, wallet="xxxxxx")}, "log": []}
wm.agents.grok.pair = lambda m: {"priceUsd": "2.0"}
wm.mirror_sell(st, "MintA", L); wm.mirror_sell(st, "MintB", L)
assert "MintA" not in st["pos"] and "MintB" in st["pos"] and st["log"][-1]["why"].startswith("ขายตามเจ้าของ")
assert abs(st["cash"] - 15 * (1 - wm.agents.SLIP) * (1 - wm.agents.FEE)) < 1e-9     # price capped at 1.5x the last price
_os.environ.pop("WALLET_LIST")
print("mirror ok")
