"""Rebuild the calendar and map from annual FIRMS detection extracts.

Requires the year files in --raw, DuckDB, numpy and shapely. A complete
2000-through-current-year archive is required to avoid mixing regions.
"""
import argparse
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

import build_calendar as calendar
from aggregate import aggregate_observations

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=ROOT / "data/harmonization/raw")
    ap.add_argument("--allow-missing-west", action="store_true", help="allow incomplete coastal strip extracts")
    args = ap.parse_args()
    last_year = datetime.now(timezone.utc).year
    years = list(range(2000, last_year + 1))
    missing = [str(y) for y in years if not (args.raw / f"{y}.parquet").exists()]
    if missing:
        raise SystemExit(f"Missing annual extracts {missing}; refusing partial rebuild")
    missing_west = [y for y in years if not (args.raw / f"{y}.west.parquet").exists()]
    if missing_west and not args.allow_missing_west:
        raise SystemExit(f"Missing coastal-strip extracts {missing_west}; refusing partial rebuild")
    if missing_west:
        print(f"WARNING: coastal strip missing from {missing_west}", flush=True)

    old_days = calendar.load_state()
    days, map_days = {}, {}
    con = duckdb.connect()
    try:
        for year in years:
            paths = [str(args.raw / f"{year}.parquet")]
            if year not in missing_west:
                paths.append(str(args.raw / f"{year}.west.parquet"))
            cursor = con.execute("""SELECT satellite, confidence, latitude, longitude,
                acq_date, strftime(acq_datetime, '%H:%M') AS acq_time, daynight,
                frp, scan, track, bright_ti4, bright_ti5, brightness, bright_t31,
                version, type, quality FROM read_parquet(?)
                WHERE satellite IN ('Terra','Aqua','Suomi-NPP','NOAA-20')""", [paths])
            names = [v[0] for v in cursor.description]
            buckets = defaultdict(list)
            while batch := cursor.fetchmany(50000):
                for values in batch:
                    row = dict(zip(names, values))
                    d = row["acq_date"].isoformat()
                    sat = row["satellite"]
                    if year <= 2011:
                        desired = old_days.get(d, {}).get("source")
                        if desired and desired != "modis_" + sat.lower():
                            continue
                        if not desired and sat != ("Terra" if d < "2002-07-01" else "Aqua"):
                            continue
                    elif sat != ("Suomi-NPP" if d < calendar.CONFIG["noaa20_start"] else "NOAA-20"):
                        continue
                    buckets[row["quality"]].append(row)
            by_quality = {}
            for quality in ("nrt", "sp"):
                passes = aggregate_observations(buckets.get(quality, []), calendar.CONFIG["region_id"])
                grouped = defaultdict(list)
                for p in passes:
                    if year <= 2011:
                        p["harmonized_activity"] = p["occupied_cells"]
                    else:
                        calendar.score_passes([p])
                    grouped[p["date"]].append(p)
                by_quality[quality] = grouped
            selected = dict(by_quality["nrt"])
            selected.update(by_quality["sp"])
            for day, passes in selected.items():
                quality = "sp" if day in by_quality["sp"] else "nrt"
                entry = calendar.day_entry(day, passes, quality)
                if year <= 2011:
                    entry["status"] = "modis-native"
                    entry["source"] = "modis_" + passes[0]["platform"].lower()
                days[day] = entry
                map_days[day] = calendar.map_entries(passes)
            print(f"{year}: {len(selected)} California days", flush=True)
    finally:
        con.close()
    if not days or min(days)[:4] != "2000" or max(days)[:4] != str(last_year):
        raise SystemExit("Unexpected archive coverage; no output was written")
    map_data = calendar.build_map_payload(map_days)
    map_data["missing_west_years"] = missing_west
    state = {"schema_version": 1, "region_id": calendar.CONFIG["region_id"],
             "model": calendar.MODEL["name"],
             "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "missing_west_years": missing_west, "days": days}
    calendar.atomic_write_json(calendar.STATE_PATH, state)
    calendar.atomic_write_json(calendar.CALENDAR_PATH, calendar.build_calendar_payload(days))
    calendar.atomic_write_json(calendar.MAP_STATE_PATH, {"schema_version": 1, "days": map_days}, compact=True)
    calendar.atomic_write_json(ROOT / "docs/assets/cells.json", map_data)
    print(f"Rebuilt {len(days)} days and {len(map_data['cells'])} California grid cells")


if __name__ == "__main__":
    main()
