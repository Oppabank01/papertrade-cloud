"""fwd_maxmom.py walking daily bars one at a time gives the same weekly trades as the scout's backtest (/tmp/scout_1121/maxmom.py)."""
import fwd_maxmom as M
import test_fwd_lowvol as T

if __name__ == "__main__":
    T.check(M.signal, "fwd_maxmom")
