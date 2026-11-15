"""Generate a separate experimental Timestral activity-index forecast.

This output is not merged into the calendar or map. It is a statistical
forecast of reported satellite activity, not a wildfire-risk forecast.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from evaluate_forecast import MODEL_ID, MODEL_REVISION, context_for

ROOT = Path(__file__).resolve().parent.parent


def make_forecast(calendar, model, today):
    """Forecast tomorrow through seven days later, with no future data in context."""
    closed_day = today - timedelta(days=1)
    days = {date.fromisoformat(row['date']): float(row['activity'])
            for row in calendar['daily'] if date.fromisoformat(row['date']) <= closed_day}
    if not days:
        raise ValueError('No completed-day observations are available')
    latest = max(days)
    if (closed_day - latest).days > 3:
        raise ValueError('Latest reported detection is more than three days old; forecast withheld')
    context = context_for(days, closed_day)
    if np.isfinite(context).sum() < 30:
        raise ValueError('Not enough reported activity for an experimental forecast')
    # Step 1 forecasts the current, still-incomplete UTC day. Omit it and
    # publish only tomorrow onwards so no estimate overwrites observations.
    result = model.forecast(context, prediction_length=8)
    values = [np.asarray(result.quantile(q), dtype=float).reshape(-1) for q in (.1, .5, .9)]
    if any(len(v) != 8 or not np.isfinite(v).all() for v in values):
        raise ValueError('Timestral returned invalid forecast values')
    predictions = []
    for index in range(1, 8):
        q10, median, q90 = [max(0.0, float(np.expm1(v[index]))) for v in values]
        if not (np.isfinite([q10, median, q90]).all() and q10 <= median <= q90):
            raise ValueError('Timestral returned invalid or crossed quantiles')
        predictions.append({'date': (today + timedelta(days=index)).isoformat(),
                            'median': round(median, 3), 'q10': round(q10, 3), 'q90': round(q90, 3)})
    return {'schema_version': 1, 'kind': 'experimental_forecast', 'model': MODEL_ID,
            'model_revision': MODEL_REVISION, 'origin_utc_date': closed_day.isoformat(),
            'latest_reported_date': latest.isoformat(),
            'calendar_generated_utc': calendar.get('generated_utc'),
            'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'unit': calendar.get('unit'),
            'warning': 'Experimental forecast of satellite-detected activity; not a fire-risk forecast or emergency guidance.',
            'predictions': predictions}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--calendar', type=Path, default=ROOT/'docs/data/calendar.json')
    p.add_argument('--out', type=Path, default=ROOT/'data/harmonization/experimental-forecast.json')
    p.add_argument('--backtest', type=Path, help='Backtest report to include with the forecast')
    p.add_argument('--local-only', action='store_true')
    args = p.parse_args()
    import torch
    from timestral import TimestralForecaster
    torch.set_num_threads(2)
    model = TimestralForecaster.from_pretrained(MODEL_ID, revision=MODEL_REVISION,
                                                 local_files_only=args.local_only)
    result = make_forecast(json.loads(args.calendar.read_text(encoding='utf-8')), model,
                           datetime.now(timezone.utc).date())
    if args.backtest:
        report = json.loads(args.backtest.read_text(encoding='utf-8'))
        result['validation'] = {'description': report['evaluation'], 'pooled': report['pooled'],
                                'by_year': report['by_year']}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(f"Wrote {len(result['predictions'])} experimental predictions to {args.out}")


if __name__ == '__main__':
    main()
