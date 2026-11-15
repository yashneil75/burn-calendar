"""Published clear-sky observation operator (Sofiev & Kouznetsov 2026, GMD).

Maps FRP to a fractional pixel response. Used for the visibility-proxy
features consumed by the California harmonization model. Ported from the
Fireharmonizer research prototype (equations 5-7, tables 1-2).
"""
import math

# lambda, mu, r0, r1, cutoff; table coefficients, with area in km^2, FRP in MW.
PARAMETERS = {
    ("MODIS", "D"): (4.44, .52, .07, 1.26, .045),
    ("MODIS", "N"): (4.43, 1.01, .11, 1.06, .045),
    ("VIIRS", "D"): (6.17, 1.44, .61, .21, .05),
    ("VIIRS", "N"): (1.38, .35, 2.12, 1.02, .05),
}


def response(frp_mw, area_km2, sensor="MODIS", daynight="D", *, valid=True):
    """Shifted-logistic response in [0, 1]."""
    if valid is None:
        raise ValueError("valid must be True or False")
    if not valid:
        return 0.0
    if not math.isfinite(frp_mw) or frp_mw < 0 or not math.isfinite(area_km2) or area_km2 <= 0:
        raise ValueError("FRP must be finite/nonnegative and area positive")
    lam, mu, r0, r1, cutoff = PARAMETERS[(sensor, daynight)]
    z = (r0 + r1 / area_km2) * (frp_mw - (lam * area_km2 + mu))
    sigmoid = 1 / (1 + math.exp(-max(-700, min(700, z))))
    return max(0.0, (sigmoid - cutoff) / (1 - cutoff))
