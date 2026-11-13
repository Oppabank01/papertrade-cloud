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
