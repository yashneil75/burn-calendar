"""Fit the California-tailored VIIRS -> MODIS-Aqua harmonization model.

Offline tool. Training data: full-coverage California (statewide bbox) SNPP
acquisitions co-detected with Aqua MODIS within 10 minutes, 2015-2026
(science-quality standard-processing rows, 1 km equal-area occupied cells).
Target: MODIS-Aqua occupied cells per paired overpass.

The model retains a date-based epoch indicator for compatibility. A date is
not a reliable processing collection identifier. Validation holds out each
year and applies the same 500-cell cap as the production scoring code.

Outputs pipeline/model/ca_model.json consumed by harmonize.py. Never runs
in CI; the coefficients ship in the repo.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

FEATURES = [
    "log_cells", "log_frp_med", "log_frp_max", "log_frp_q90",
    "zero_frp_frac", "scan", "track", "neighbor_frac", "coarse5_frac",
    "log_vis2", "cells_above10", "daynight_d",
    "doy_sin", "doy_cos", "epoch_c61",
    "hour_sin", "hour_cos",
]
C61_CUTOFF = date(2023, 1, 1)


def featurize(pass_: dict) -> dict:
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


def load_joined(derived: Path) -> list[dict]:
    pairs = json.loads((derived / "pairs" / "california-state" / "pairs.json").read_text(encoding="utf-8"))
    passes_by_time = {}
    for f in sorted((derived / "passes" / "california-state").glob("*.json")):
        for p in json.loads(f.read_text(encoding="utf-8")):
            if p["platform"] == "SNPP":
                # Spatial pairs reference a pass's center_time, not its batch anchor.
                key = p.get("center_time", p["time"])
                if key in passes_by_time:
                    raise ValueError(f"Duplicate SNPP pass time: {key}")
                passes_by_time[key] = p
    rows = []
    for pair in pairs:
        snpp = passes_by_time.get(pair["viirs_time"])
        if snpp is None:
            raise ValueError(f"Missing SNPP pass: {pair['viirs_time']}")
        rows.append({**featurize(snpp), "y": float(pair["modis_count"]),
                     "date": snpp["date"], "year": snpp["date"][:4]})
    return rows


def fit_poisson(X: np.ndarray, y: np.ndarray, l2: float, max_iter: int = 200) -> np.ndarray:
    beta = np.zeros(X.shape[1])
    for _ in range(max_iter):
        eta = X @ beta
        mu = np.exp(np.clip(eta, -20, 20))
        grad = X.T @ (y - mu) - l2 * beta
        hess = -(X.T * mu) @ X - l2 * np.eye(X.shape[1])
        step = np.linalg.solve(-hess, grad)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-8:
            break
    return beta


def fit_with_intercept(X: np.ndarray, y: np.ndarray, l2: float):
    mean, std = X.mean(axis=0), X.std(axis=0)
    std[std < 1e-8] = 1.0
    Xz = (X - mean) / std
    beta = fit_poisson(Xz, y, l2)
    eta = Xz @ beta
    b = math.log(max(y.mean(), 1e-3))
    for _ in range(200):
        mu = np.exp(np.clip(eta + b, -20, 20))
        update = math.log(max(y.sum(), 1e-9) / max(mu.sum(), 1e-9))
        b += update
        if abs(update) < 1e-10:
            break
    return beta, b, mean, std


def predict(X: np.ndarray, beta, intercept, mean, std) -> np.ndarray:
    Xz = (X - mean) / std
    return np.clip(np.exp(np.clip(Xz @ beta + intercept, -20, 20)), 0, 500)


def metrics(y: np.ndarray, mu: np.ndarray) -> dict:
    err = np.abs(mu - y)
    return {
        "n": int(len(y)),
        "mae": float(err.mean()),
        "median_ae": float(np.median(err)),
        "rmse": float(np.sqrt(((mu - y) ** 2).mean())),
        "relative_bias": float((mu.sum() - y.sum()) / max(y.sum(), 1e-9)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--derived", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--l2", type=float, default=1.0)
    args = ap.parse_args()

    rows = load_joined(Path(args.derived))
    print(f"joined training rows: {len(rows)}")
    X = np.array([[r[f] for f in FEATURES] for r in rows], dtype=float)
    y = np.array([r["y"] for r in rows], dtype=float)
    years_arr = np.array([r["year"] for r in rows])

    # Leave-one-year-out CV
    pooled_true, pooled_pred, fold_metrics = [], [], {}
    for yr in sorted(set(years_arr)):
        tr = years_arr != yr
        if tr.sum() < 30 or (~tr).sum() == 0:
            continue
        beta, intercept, mean, std = fit_with_intercept(X[tr], y[tr], args.l2)
        mu = predict(X[~tr], beta, intercept, mean, std)
        fold_metrics[yr] = metrics(y[~tr], mu)
        pooled_true.append(y[~tr])
        pooled_pred.append(mu)
    pooled_true = np.concatenate(pooled_true)
    pooled_pred = np.concatenate(pooled_pred)
    pooled = metrics(pooled_true, pooled_pred)
    print("leave-one-year-out pooled:", json.dumps(pooled, indent=1))
    for yr, m in sorted(fold_metrics.items()):
        print(f"  fold {yr}: n={m['n']:4d}  mae={m['mae']:.2f}  medae={m['median_ae']:.2f}  bias={m['relative_bias']:+.3f}")

    # Deployed model: all years
    beta, intercept, mean, std = fit_with_intercept(X, y, args.l2)
    mu = predict(X, beta, intercept, mean, std)
    in_sample = metrics(y, mu)
    train_ratio = float(y.sum() / max(np.expm1(X[:, 0]).sum(), 1e-9))
    print("deployed fit (all years):", json.dumps(in_sample, indent=1))
    print(f"modis/viirs summed ratio across cohort: {train_ratio:.3f}")

    payload = {
        "schema_version": 1,
        "name": "california-modis-aqua-poisson-glm",
        "trained_on": f"California bounding-box VIIRS S-NPP/Aqua co-detected pairs, {min(years_arr)}–{max(years_arr)} (leave-one-year-out validation)",
        "target": "MODIS-Aqua occupied 1 km cells per co-detected overpass",
        "feature_order": FEATURES,
        "feature_mean": mean.tolist(),
        "feature_std": std.tolist(),
        "coefficients": beta.tolist(),
        "intercept": float(intercept),
        "l2": args.l2,
        "c61_cutoff": C61_CUTOFF.isoformat(),
        "metrics": {
            "leave_one_year_out_pooled": pooled,
            "leave_one_year_out_by_year": fold_metrics,
            "fit_all_years": in_sample,
            "modis_to_viirs_ratio": train_ratio,
        },
        "clip": [0.0, 500.0],
        "validation_note": "Co-detections only; no common swath or cloud masks. Training uses a bounding box; production filters to the California polygon. NOAA-20 is not calibrated.",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
