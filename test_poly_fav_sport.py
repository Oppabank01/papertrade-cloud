#!/usr/bin/env python3
"""poly_fav_sport only lets sports markets through and otherwise defers to poly_fav's filter (no network)."""
import time
import poly_fav_sport as S

now = time.time()
assert S.F.tradable({"feeType": "crypto_fees_v2"}, now) == "not sports"
assert S.F.tradable({"feeType": None}, now) == "not sports"
assert S.F.tradable({"feeType": "sports_fees_v3"}, now) == "not accepting orders"   # passed on to poly_fav's checks
assert (S.F.FAV_LO, S.F.FAV_HI, S.F.LONG_LO, S.F.LONG_HI) == (0.60, 0.85, 0.15, 0.40)
print("ok")
