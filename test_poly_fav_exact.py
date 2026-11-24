#!/usr/bin/env python3
"""poly_fav_exact only lets exact-score markets through and otherwise defers to poly_fav's filter (no network)."""
import time
import poly_fav_exact as S

now = time.time()
assert S.F.tradable({"question": "Spurs vs. Kings"}, now) == "not exact score"
assert S.F.tradable({"question": None}, now) == "not exact score"
assert S.F.tradable({"question": "Exact Score: Arsenal FC 3 - 2 BVB?"}, now) == "not accepting orders"
assert (S.F.FAV_LO, S.F.FAV_HI, S.F.LONG_LO, S.F.LONG_HI) == (0.85, 0.97, 0.03, 0.15)
print("ok")
