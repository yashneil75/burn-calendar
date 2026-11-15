"""Retrospective Timestral-5M evaluation on reported calendar activity.

Experimental research only: missing dates remain NaN; scoring is conditional
on reported future days and is not an evaluation of wildfire prediction.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np

MODEL_ID = "mistralai/Timestral-5M"
MODEL_REVISION = "bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f"
ROOT = Path(__file__).resolve().parent.parent


def context_for(days, origin, length=730):
    return np.array([math.log1p(days[d]) if d in days else np.nan
                     for d in (origin - timedelta(days=offset) for offset in range(length - 1, -1, -1))], dtype=np.float32)


def seasonal_baseline(days, origin, horizon):
    """Median of reported days near the target date, from prior years only."""
    values = []
    for n in range(1, horizon + 1):
        target = origin + timedelta(days=n)
        pool = []
        for y in range(origin.year - 5, origin.year):
            for shift in range(-15, 16):
                try:
                    day = date(y, target.month, target.day) + timedelta(days=shift)
                except ValueError:
                    day = date(y, 2, 28) + timedelta(days=shift)
                if day in days and day <= origin:
                    pool.append(days[day])
        values.append(float(np.median(pool)) if pool else float('nan'))
    return np.asarray(values)


def metrics(y, prediction):
    mask = np.isfinite(y) & np.isfinite(prediction)
    y, prediction = y[mask], prediction[mask]
    if not len(y):
        return {"n": 0}
    return {"n": len(y), "mae": float(np.mean(np.abs(prediction-y))),
            "rmse": float(np.sqrt(np.mean((prediction-y)**2))),
            "bias": float((prediction.sum()-y.sum())/y.sum()) if y.sum() else None}


def run(calendar, local_only=False):
    import torch
    from timestral import TimestralForecaster
    torch.set_num_threads(2)
    days = {date.fromisoformat(row['date']): float(row['activity']) for row in calendar['daily']}
    model = TimestralForecaster.from_pretrained(MODEL_ID, revision=MODEL_REVISION, local_files_only=local_only)
    observed, timestral, seasonal, persistence, low, high = [], [], [], [], [], []
    yearly = {}
    for year in (2023, 2024, 2025):
        yd = {k: [] for k in ('actual','median','seasonal','persistence','low','high')}
        for month in range(1, 13):
            for day in (1, 15):
                origin = date(year, month, day)
                context = context_for(days, origin)
                if not np.isfinite(context[-14:]).any():
                    continue
                output = model.forecast(context, prediction_length=7)
                median = np.maximum(0, np.expm1(np.asarray(output.median).reshape(-1)))
                lo = np.maximum(0, np.expm1(np.asarray(output.quantile(.1)).reshape(-1)))
                hi = np.maximum(0, np.expm1(np.asarray(output.quantile(.9)).reshape(-1)))
                actual = [days.get(origin+timedelta(days=h), float('nan')) for h in range(1,8)]
                baseline = seasonal_baseline(days, origin, 7)
                valid = context[np.isfinite(context)]
                last = np.expm1(valid[-1]) if len(valid) else float('nan')
                for key, arr in [('actual',actual),('median',median),('seasonal',baseline),('persistence',[last]*7),('low',lo),('high',hi)]:
                    yd[key].extend(arr)
        actual, pred, base, persist, lo, hi = (np.asarray(yd[k], dtype=float) for k in ('actual','median','seasonal','persistence','low','high'))
        mask = np.isfinite(actual) & np.isfinite(lo) & np.isfinite(hi)
        yearly[str(year)] = {'timestral':metrics(actual,pred), 'seasonal':metrics(actual,base),
                             'persistence':metrics(actual,persist),
                             'interval_10_90_coverage':float(np.mean((actual[mask]>=lo[mask]) & (actual[mask]<=hi[mask]))) if mask.any() else None}
        print(year, json.dumps(yearly[str(year)]), flush=True)
        observed.extend(actual); timestral.extend(pred); seasonal.extend(base); persistence.extend(persist); low.extend(lo); high.extend(hi)
    actual, pred, base, persist, lo, hi = map(np.asarray, (observed,timestral,seasonal,persistence,low,high))
    mask = np.isfinite(actual) & np.isfinite(lo) & np.isfinite(hi)
    peak_threshold = float(np.quantile(actual[mask], .9))
    peak_mask = mask & (actual >= peak_threshold)
    return {'model':MODEL_ID,'model_revision':MODEL_REVISION,'horizon_days':7,'context_days':730,
            'evaluation':'1st and 15th of each month 2023–2025; only reported future days are scored; inputs use latest available historical archive, not as-of snapshots.',
            'warning':'Activity index conditional on satellite detection; not a wildfire-risk or emergency forecast.',
            'pooled':{'timestral':metrics(actual,pred),'seasonal':metrics(actual,base),'persistence':metrics(actual,persist),
                      'interval_10_90_coverage':float(np.mean((actual[mask]>=lo[mask]) & (actual[mask]<=hi[mask]))),
                      'top_10_percent_threshold':peak_threshold,
                      'top_10_percent_timestral':metrics(actual[peak_mask],pred[peak_mask]),
                      'top_10_percent_seasonal':metrics(actual[peak_mask],base[peak_mask])},'by_year':yearly}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--calendar',type=Path,default=ROOT/'docs/data/calendar.json')
    p.add_argument('--out',type=Path,default=ROOT/'data/harmonization/forecast-backtest.json')
    p.add_argument('--local-only',action='store_true')
    a=p.parse_args()
    report=run(json.loads(a.calendar.read_text(encoding='utf-8')),a.local_only)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('pooled',json.dumps(report['pooled'],indent=2))
    print('wrote',a.out)


if __name__=='__main__':
    main()
