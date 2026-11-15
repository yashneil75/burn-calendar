"""Deterministic FIRMS point-to-pass aggregation (1 km cylindrical grid).

Ported from the Fireharmonizer research prototype with identical cleaning
semantics: same grid, same 10-minute pass window, same confidence/type
thresholds, same occupied-cell accounting.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
import math
from typing import Any

import numpy as np
from boundary import within_california

EARTH_RADIUS_KM = 6371.0088
GRID_KM = 1.0
PASS_WINDOW_MINUTES = 10


def _first(row, *names):
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def _platform(value):
    if value is None:
        return None
    val = str(value).strip().upper()
    return {"A": "Aqua", "AQUA": "Aqua", "T": "Terra", "TERRA": "Terra",
            "N": "SNPP", "SNPP": "SNPP", "SUOMI-NPP": "SNPP",
            "SUOMI NPP": "SNPP", "SUOMI_NPP": "SNPP",
            "1": "NOAA20", "N20": "NOAA20", "NOAA-20": "NOAA20",
            "NOAA20": "NOAA20", "NOAA_20": "NOAA20"}.get(val)


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    val = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            pass
    if len(val) == 7 and val.isdigit():
        try:
            return datetime.strptime(val, "%Y%j").date()
        except ValueError:
            pass
    return None


def _parse_time(value):
    if value is None:
        return None
    if isinstance(value, time):
        return value.replace(tzinfo=None, second=0, microsecond=0)
    if isinstance(value, datetime):
        return value.time().replace(tzinfo=None, second=0, microsecond=0)
    val = str(value).strip()
    if ":" in val:
        try:
            return datetime.strptime(val, "%H:%M").time()
        except ValueError:
            return None
    try:
        digits = str(int(float(val)))
    except (ValueError, OverflowError):
        return None
    if not digits.isdigit() or len(digits) > 4:
        return None
    digits = digits.zfill(4)
    hour, minute = int(digits[:2]), int(digits[2:])
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def _daynight(value):
    if value is None:
        return None
    val = str(value).strip().upper()
    if val in {"D", "DAY"}:
        return "day"
    if val in {"N", "NIGHT"}:
        return "night"
    return None


def _confidence_ok(platform, confidence):
    if confidence is None:
        return False
    if platform in {"Aqua", "Terra"}:
        try:
            return float(confidence) >= 30
        except (ValueError, TypeError):
            return False
    return str(confidence).strip().lower() in {"n", "h"}


def _number(value):
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _cell(lat, lon):
    x = EARTH_RADIUS_KM * math.radians(lon)
    y = EARTH_RADIUS_KM * math.sin(math.radians(lat))
    return (math.floor(x / GRID_KM), math.floor(y / GRID_KM))


def aggregate_observations(rows, region_id):
    """Clean detections, collapse occupied cells, and form 10-minute passes."""
    exclusions: Counter = Counter()
    cleaned = []
    for row in rows:
        platform = _platform(_first(row, "satellite", "platform", "sensor"))
        if platform is None:
            exclusions["unknown_platform"] += 1
            continue
        type_value = _first(row, "type", "fire_type")
        if type_value is not None:
            parsed_type = _number(type_value)
            if parsed_type is None or parsed_type != 0:
                exclusions["non_vegetation"] += 1
                continue
        confidence = _first(row, "confidence", "conf")
        if not _confidence_ok(platform, confidence):
            exclusions["low_confidence"] += 1
            continue
        lat = _number(_first(row, "latitude", "lat"))
        lon = _number(_first(row, "longitude", "lon", "long"))
        if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            exclusions["invalid_coordinates"] += 1
            continue
        acq_date = _parse_date(_first(row, "acq_date", "date"))
        acq_time = _parse_time(_first(row, "acq_time", "time"))
        if acq_date is None or acq_time is None:
            exclusions["invalid_timestamp"] += 1
            continue
        dn = _daynight(_first(row, "daynight", "day_night"))
        if dn is None:
            exclusions["invalid_daynight"] += 1
            continue
        dt = datetime.combine(acq_date, acq_time, tzinfo=timezone.utc)
        cleaned.append({
            "platform": platform, "daynight": dn, "datetime": dt,
            "cell": _cell(lat, lon), "frp": _number(_first(row, "frp")) or 0.0,
            "scan": _number(_first(row, "scan", "mean_scan")),
            "track": _number(_first(row, "track", "mean_track")),
            "lat": lat, "lon": lon,
            "ti4": _number(_first(row, "bright_ti4", "brightness")),
            "ti5": _number(_first(row, "bright_ti5", "bright_t31")),
            "processing_version": str(row.get("version", "unknown")),
        })
    if region_id == "california-state" and cleaned:
        mask = within_california([item["lon"] for item in cleaned], [item["lat"] for item in cleaned])
        exclusions["outside_california"] += int(len(cleaned) - np.count_nonzero(mask))
        cleaned = [item for item, inside in zip(cleaned, mask) if inside]
    aggregate_observations.last_exclusions = dict(exclusions)

    strata = defaultdict(list)
    for item in cleaned:
        strata[(item["platform"], item["daynight"])].append(item)
    summaries = []
    max_span = timedelta(minutes=PASS_WINDOW_MINUTES)
    for (platform, dn), items in sorted(strata.items()):
        items.sort(key=lambda item: (item["datetime"], item["cell"]))
        batch, anchor = [], None
        for item in items:
            if anchor is not None and (
                item["datetime"].date() != anchor.date()
                or item["datetime"] - anchor > max_span
            ):
                summaries.append(_summarize(batch, region_id, platform, dn))
                batch, anchor = [], None
            if anchor is None:
                anchor = item["datetime"]
            batch.append(item)
        if batch:
            summaries.append(_summarize(batch, region_id, platform, dn))
    summaries.sort(key=lambda p: (p["region_id"], p["date"], p["time"], p["platform"], p["daynight"]))
    return summaries


def _summarize(items, region_id, platform, dn):
    from observation import response

    cell_frp = defaultdict(float)
    for item in items:
        cell_frp[item["cell"]] += max(0.0, item["frp"])
    cells = {item["cell"] for item in items}
    coarse_counts = Counter((x // 5, y // 5) for x, y in cells)
    representatives = {}
    for item in items:
        key = (item["cell"][0] // 5, item["cell"][1] // 5)
        representatives.setdefault(key, (item["lon"], item["lat"]))
    scans = [item["scan"] for item in items if item["scan"] is not None]
    tracks = [item["track"] for item in items if item["track"] is not None]
    dt = min(item["datetime"] for item in items)
    powers = np.array(list(cell_frp.values()))
    pixel_powers = np.array([max(0.0, i["frp"]) for i in items])
    lat = sum(i["lat"] for i in items) / len(items)
    lon = sum(i["lon"] for i in items) / len(items)
    thermal = {}
    for field in ("ti4", "ti5"):
        values = [i[field] for i in items if i.get(field) is not None]
        thermal[field + "_median"] = float(np.median(values)) if values else 0.0
    topology = {
        "cell_frp_q25": float(np.quantile(powers, .25)),
        "cell_frp_median": float(np.median(powers)),
        "cell_frp_q90": float(np.quantile(powers, .9)),
        "cell_frp_max": float(max(powers)),
        "pixel_frp_max": float(max(pixel_powers)),
        "pixel_frp_std": float(np.std(pixel_powers)),
        "zero_frp_fraction": float(np.mean(pixel_powers == 0)),
        "mean_latitude": lat,
        "mean_longitude": lon,
        "local_solar_hour": (dt.hour + dt.minute / 60 + lon / 15) % 24,
        "cell_neighbor_fraction": sum(
            any((x + dx, y + dy) in cells for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            for x, y in cells
        ) / len(cells),
        "coarse5_fraction": len({(x // 5, y // 5) for x, y in cells}) / len(cells),
        "latitude_span": max(i["lat"] for i in items) - min(i["lat"] for i in items),
        "longitude_span": max(i["lon"] for i in items) - min(i["lon"] for i in items),
        **thermal,
    }
    for area in (2, 4, 8):
        topology[f"visibility_area{area}"] = sum(
            response(p, area, "MODIS", "D" if dn == "day" else "N") for p in powers
        )
    for threshold in (5, 10, 20, 40):
        topology[f"cells_above{threshold}"] = float(np.mean(powers >= threshold))
    return {
        "region_id": region_id,
        "platform": platform,
        "daynight": "D" if dn == "day" else "N",
        "date": dt.date().isoformat(),
        "time": dt.isoformat(timespec="minutes"),
        "occupied_cells": len(cells),
        "frp": float(sum(item["frp"] for item in items)),
        "detections": len(items),
        "processing_versions": sorted({item["processing_version"] for item in items}),
        "source_features": topology,
        "coarse_cells": [list(c) for c in sorted({(c[0] // 5, c[1] // 5) for c in cells})],
        "coarse_cell_counts": [[x, y, count, *representatives[(x, y)]]
                               for (x, y), count in sorted(coarse_counts.items())],
        "center_time": sorted(item["datetime"] for item in items)[len(items) // 2].isoformat(timespec="minutes"),
        "mean_scan": float(sum(scans) / len(scans)) if scans else None,
        "mean_track": float(sum(tracks) / len(tracks)) if tracks else None,
    }


aggregate_observations.last_exclusions = {}
