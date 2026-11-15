# California Burn Calendar

Satellite-detected fire activity within the Natural Earth California boundary, one day at a time since 2000. VIIRS detections are scored with a model intended to approximate MODIS-Aqua occupied cells; earlier years use MODIS directly. Sensor, coverage and overpass differences limit comparisons across time. The site is served on GitHub Pages and the refresh is scheduled for 07:23 UTC.

The refresh uses S-NPP through November 2, 2026 and NOAA-20 thereafter. The existing S-NPP-trained model is applied to NOAA-20 without a validated sensor bridge, so NOAA-20 estimates are provisional and may not be directly comparable. Missing days do not mean zero fire. Detection centres are filtered to California; the geographic polygon is approximate.

The narrow California coastal strip west of −124.4° was checked against the 2012–2026 archive snapshot; it contained no reported detections. Current API requests extend to −124.5°. The historical rebuild tools additionally require DuckDB with its httpfs and spatial extensions, plus the locally saved annual extracts.

**Live:** https://yashneil75.github.io/burn-calendar/

## What you get

- A month grid: per-day harmonized activity with FRP and day/night splits
- An archive matrix: every year and month since 2000 at a glance
- A map page: fire density, 2000 to present, pan and zoom limited to California
- A day drawer: D/N breakdown, per-pass counts, percentile vs. the calendar month across years
- An open, rebuilt-daily data file: `docs/data/calendar.json`

Units: MODIS‑Aqua-equivalent occupied 1 km² equal-area grid cells. This is an activity index: not burned area, not a fire count, not an early-warning system. Days without reported observations are blank, never zero.

## Repository layout

```
docs/                  The static site (GitHub Pages serves from here)
  index.html           Month grid + archive + day drawer
  methodology.html     Methods, sources, validation results
  data/calendar.json   The product, rebuilt daily
pipeline/              Everything that runs ahead of time (Python + numpy)
  build_calendar.py    Daily refresh: pull FIRMS, re-aggregate, rewrite calendar.json
  fit_model.py         Offline: fit the CA Poisson GLM (not run in CI)
  model/ca_model.json  Fitted coefficients, LOYO validation metrics
  state.json           Internal per-day state (Inputs to calendar.json)
.github/workflows/     Daily refresh cron + commit bot
```

## Daily refresh mechanics

1. Pull the relevant S-NPP and NOAA-20 standard-processing data for the current year and at least the trailing 120 days in 5-day chunks, respecting the sensor transition date.
2. Pull the relevant near-real-time data for a trailing 120-day window to cover the SP lag.
3. Filter detection centres to California, then aggregate to 10-minute overpasses on a 1 km cylindrical equal-area grid.
4. Score each pass with `pipeline/model/ca_model.json`; NOAA-20 estimates are provisional.
5. Merge (SP wins over NRT; newest SP wins), then rebuild the calendar and map from their synchronized daily states.

After a successful refresh, the experimental Timestral-5M workflow forecasts seven future days of the satellite-detected activity index and publishes them separately. Purple calendar cells are forecasts and are excluded from observed totals, the map and rankings. A 2023–2025 retrospective check found summed median forecasts 73% below reported activity. This is not a wildfire-risk, ignition, spread or emergency forecast. See [forecast evaluation](docs/forecast-experiment.md).

## Local run

```bash
python -m http.server 8000 -d docs        # view the site
pip install -r requirements.txt           # numpy and shapely
FIRMS_MAP_KEY=... python pipeline/build_calendar.py   # reproduce today's data
python pipeline/build_calendar.py --offline           # rebuild from committed state
python pipeline/fit_model.py --derived <mirror-derived-dir> --out pipeline/model/ca_model.json
python -m unittest discover -s tests -v
```

The original paired training archive is not included. The published validation does not apply the production cap, and its co-detected cohort does not establish performance for all observation conditions. A separate [retrained bounding-box candidate](pipeline/model/ca_model_retrained_candidate.json) uses 837 co-detected pairs and cap-aware held-out metrics. Its year-held-out 2025 bias is −47% (36 pairs), so it has not replaced the published model. The candidate's training data cover a bounding box, while the calendar filters to the state polygon. Neither model provides a validated NOAA-20 sensor correction.

## Data & license

Code: MIT (see LICENSE). Detections: NASA FIRMS, public domain. The archive bootstrap used the CC0 Source Cooperative FIRMS mirror (NASA LANCE republished verbatim), cross-validated row-for-row against FIRMS API extracts.
