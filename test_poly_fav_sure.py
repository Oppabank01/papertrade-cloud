#!/usr/bin/env python3
"""poly_fav_sure's ranges and widened fill bounds (no network)."""
import poly_fav_sure as S

assert (S.F.FAV_LO, S.F.FAV_HI, S.F.LONG_LO, S.F.LONG_HI) == (0.985, 0.995, 0.005, 0.015)
assert S.F.P.PX_MIN <= S.F.LONG_LO and S.F.P.PX_MAX >= S.F.FAV_HI
print("ok")
