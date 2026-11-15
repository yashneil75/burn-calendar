# California Burn Calendar

California fire activity, one day at a time, placed on a single consistent scale across the entire VIIRS S‑NPP era (2015–present). Every day with science-quality 375 m VIIRS detections is harmonized to a MODIS‑Aqua-equivalent occupied-cell scale by a California-tailored model, then served as a fully static site on GitHub Pages. Refreshed every morning at 07:23 UTC by GitHub Actions.

**Live:** https://yashneil75.github.io/burn-calendar/

## What you get

- A month grid: per-day harmonized activity with FRP and day/night splits
- An archive matrix: every year and month since 2015 at a glance
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

1. Pull `VIIRS_SNPP_SP` (standard processing, science quality) year-to-date in 5-day chunks; months appear as NASA publishes them.
2. Pull `VIIRS_SNPP_NRT` for a trailing 120-day window to cover the SP lag.
3. Aggregate to 10-minute overpasses on a 1 km cylindrical equal-area grid (same cleaning semantics throughout: vegetation type only, nominal/high confidence, occupancy kept, zero-the-unobserved explicitly not applied).
4. Score each SNPP pass with `pipeline/model/ca_model.json`.
5. Merge (SP wins over NRT; newest SP wins), atomically rewrite `pipeline/state.json` and `docs/data/calendar.json`, commit.

## Local run

```bash
python -m http.server 8000 -d docs        # view the site
pip install -r requirements.txt           # numpy only
FIRMS_MAP_KEY=... python pipeline/build_calendar.py   # reproduce today's data
python pipeline/build_calendar.py --offline           # rebuild from committed state
python pipeline/fit_model.py --derived <mirror-derived-dir> --out pipeline/model/ca_model.json
```

## Data & license

Code: MIT (see LICENSE). Detections: NASA FIRMS, public domain. The archive bootstrap used the CC0 Source Cooperative FIRMS mirror (NASA LANCE republished verbatim), cross-validated row-for-row against FIRMS API extracts.
