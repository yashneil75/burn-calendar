"""California VIIRS -> MODIS-Aqua harmonization scoring.

Loads the fitted CA Poisson GLM and predicts the MODIS-Aqua occupied-cell
equivalent per SNPP pass. Pure numpy; used by the daily refresh and the
bootstrap builder.
"""
from __future__ import annotations

import json
import math
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np

C61_CUTOFF = date(2023, 1, 1)


@lru_cache(maxsize=1)
def load_model(model_path: str) -> dict:
    return json.loads(Path(model_path).read_text(encoding="utf-8"))


def features_for(pass_: dict) -> dict:
    sf = pass_.get("source_features", {})
    day = date.fromisoformat(pass_["date"])
    hour = sf.get("local_solar_hour", 12.0)
    doy = day.timetuple().tm_yday
    return {
        "log_cells": math.log1p(pass_["occupied_cells"]),
        "log_frp_med": math.log1p(max(0.0, sf.get("cell_frp_median", 0.0))),
        "log_frp_max": math.log1p(max(0.0, sf.get("pixel_frp_max", 0.0))),
        "log_frp_q90": math.log1p(max(0.0, sf.get("cell_frp_q90", 0.0))),
        "zero_frp_frac": float(sf.get("zero_frp_fraction", 0.0)),
        "scan": float(pass_["mean_scan"]) if pass_.get("mean_scan") is not None else 0.4,
        "track": float(pass_["mean_track"]) if pass_.get("mean_track") is not None else 0.4,
        "neighbor_frac": float(sf.get("cell_neighbor_fraction", 0.0)),
        "coarse5_frac": float(sf.get("coarse5_fraction", 1.0)),
        "log_vis2": math.log1p(max(0.0, sf.get("visibility_area2", 0.0))),
        "cells_above10": float(sf.get("cells_above10", 0.0)),
        "daynight_d": 1.0 if pass_.get("daynight") == "D" else 0.0,
        "doy_sin": math.sin(2 * math.pi * doy / 365.25),
        "doy_cos": math.cos(2 * math.pi * doy / 365.25),
        "epoch_c61": 1.0 if day >= C61_CUTOFF else 0.0,
        "hour_sin": math.sin(2 * math.pi * hour / 24),
        "hour_cos": math.cos(2 * math.pi * hour / 24),
    }


def predict(model: dict, pass_: dict) -> float:
    """Predicted MODIS-Aqua occupied 1 km cells for one SNPP pass."""
    f = features_for(pass_)
    x = np.array([f[name] for name in model["feature_order"]], dtype=float)
    xz = (x - np.array(model["feature_mean"], dtype=float)) / np.array(model["feature_std"], dtype=float)
    mu = math.exp(float(xz @ np.array(model["coefficients"], dtype=float) + model["intercept"]))
    clip = model.get("clip", [0.0, 500.0])
    return float(min(max(mu, clip[0]), clip[1]))
