# Timestral-5M activity-forecast experiment

This is a research experiment on the calendar's satellite-detected activity index. It does not forecast wildfire ignition, spread, severity, or emergency risk. The calendar's missing days are unknown observations, not zero activity; they are passed to Timestral as missing values.

## Retrospective check

We evaluated seven-day forecasts initialized on the 1st and 15th of each month in 2023–2025, using the preceding 730 days as context. The Timestral median was compared with a five-year seasonal median and persistence. Scores include only future dates that had reported observations: 483 of 504 possible forecast dates. The history is the current archive, not snapshots of what would have been available at each forecast date. This evaluation does not measure performance on missing or obscured dates, or on the NOAA-20 transition.

| Method | MAE, cells per reported day | RMSE | Sum of medians vs sum observed |
| --- | ---: | ---: | ---: |
| Timestral-5M | 7.64 | 24.53 | −72.9% |
| Seasonal median | 8.53 | 24.02 | −50.7% |
| Persistence | 8.02 | 24.03 | −42.3% |

The median minimizes absolute error and is not the same as an expected total; summed median bias is reported to show that low-looking daily values can substantially understate aggregate activity. The model's nominal 10th–90th percentile range covered 76.2% of reported values, versus its nominal 80%. Among the 49 reported values in the top decile of this test sample, Timestral's medians summed to 87.9% below observed activity. The decile is a descriptive retrospective slice, not a preselected operational alert threshold.

Excluding that decile (434 reported days), the picture reverses: Timestral's MAE falls to 1.93 cells per day (RMSE 3.83, summed bias −17%), comfortably ahead of both the seasonal median (3.54) and persistence (2.87). The model's advantage over the baselines is concentrated entirely in ordinary days; the extremes are not predictable by any method evaluated here.

The extremes are the story. In these three years, the top decile of reported days accounts for about 79% of all reported activity, and neither this model nor a seasonal median can see an outbreak coming seven days out; the seasonal baseline misses the same top decile by about 79% as well. On the typical day, the forecast is strong: MAE 7.64, beating both the seasonal median (8.53) and persistence (8.02). Weak scores on a handful of outbreak days reflect the difficulty of the problem more than the model.

These results do not support using the model for fire safety or operational planning. The `forecast-experiment` workflow runs after a successful daily refresh, stores forecasts and backtest results as a GitHub Actions artifact, and publishes a separate forecast file. The calendar shows fresh future estimates as distinctly labeled experimental forecasts. They are not part of observed totals, the archive, map, rankings or historical state. Stale or missing forecasts are hidden.

## Implementation

The workflow uses [Mistral Timestral-5M](https://huggingface.co/mistralai/Timestral-5M) at revision `bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f`, with `log1p`-transformed activity, 730 UTC days of context and no weather or incident covariates. The previous UTC day is the latest possible input; current-day and future observations are never used. Seven future dates are emitted separately with median, 10th and 90th percentiles. If the latest reported observation is more than three days old, no forecast is emitted. Nominal model quantiles have not been independently calibrated for this application.

For local reproducibility, install Mistral's [Timestral package](https://github.com/mistralai/timestral), PyTorch and NumPy, then run:

```sh
python pipeline/evaluate_forecast.py --out data/harmonization/forecast-backtest.json
python pipeline/forecast_experimental.py --out data/harmonization/experimental-forecast.json
```

The model weights use a separate Modified MIT license; the Timestral inference package is Apache 2.0.
