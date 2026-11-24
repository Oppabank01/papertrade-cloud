#!/usr/bin/env python3
"""poly_fav_weather only lets temperature markets through and otherwise defers to poly_fav's filter (no network)."""
import time
import poly_fav_weather as S

now = time.time()
assert S.F.tradable({"question": "Spurs vs. Kings"}, now) == "not temperature"
assert S.F.tradable({"question": None}, now) == "not temperature"
assert S.F.tradable({"question": "Will the highest temperature in Paris be 10°C on November 25?"}, now) == "not accepting orders"
assert (S.F.FAV_LO, S.F.FAV_HI, S.F.LONG_LO, S.F.LONG_HI) == (0.60, 0.93, 0.15, 0.40)
print("ok")
