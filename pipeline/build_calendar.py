"""Build the California burn calendar.

Two modes:
  --bootstrap DIR   One-off local rebuild of pipeline/state.json from the
                    mirror-mined statewide pass archive (SP passes only).
  (no args)         Daily refresh: pull trailing SP and NRT windows from
                    NASA FIRMS, upsert per-day harmonized activity, rewrite
                    docs/data/calendar.json and pipeline/state.json.
  --offline         Rewrite calendar.json from the existing state.json only.

"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from aggregate import aggregate_observations
from firms_api import fetch_rows
import harmonize

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "pipeline" / "config.json").read_text(encoding="utf-8"))
STATE_PATH = ROOT / CONFIG["state_path"]
CALENDAR_PATH = ROOT / CONFIG["calendar_path"]
MODEL = harmonize.load_model(ROOT / CONFIG["model_path"])


def atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # One field per line keeps git history efficient; the file is only ever
    # parsed by a fast JSON parser, not read by humans.
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def score_passes(passes: list[dict]) -> list[dict]:
    """Attach harmonized activity to each SNPP pass."""
    for p in passes:
        if p["platform"] == "SNPP":
            p["harmonized_activity"] = round(harmonize.predict(MODEL, p), 3)
    return passes


def day_entry(date_str: str, snpp_passes: list[dict], status: str) -> dict:
    per_period: dict[str, dict] = {}
    for period in ("D", "N"):
        subset = [p for p in snpp_passes if p["daynight"] == period]
        per_period[period] = {
            "activity": round(sum(p["harmonized_activity"] for p in subset), 3),
            "passes": len(subset),
            "frp_mw": round(sum(p["frp"] for p in subset), 1),
            "viirs_cells": sum(p["occupied_cells"] for p in subset),
            "viirs_detections": sum(p["detections"] for p in subset),
        }
    epochs = sorted({v for p in snpp_passes for v in p.get("processing_versions", [])})
    return {
        "date": date_str,
        "status": status,
        "activity": round(sum(p["harmonized_activity"] for p in snpp_passes), 3),
        "frp_mw": round(sum(p["frp"] for p in snpp_passes), 1),
        "viirs_cells": sum(p["occupied_cells"] for p in snpp_passes),
        "viirs_detections": sum(p["detections"] for p in snpp_passes),
        "day": per_period["D"],
        "night": per_period["N"],
        "epochs": epochs,
    }


def entries_from_rows(rows: list[dict], source: str, region_id: str) -> dict[str, dict]:
    """Rows (FIRMS CSV) -> per-date day entries, keyed by date."""
    passes = aggregate_observations(rows, region_id)
    snpp = [p for p in passes if p["platform"] == "SNPP"]
    scored = score_passes(snpp)
    by_date: dict[str, list[dict]] = defaultdict(list)
    for p in scored:
        by_date[p["date"]].append(p)
    status = "sp" if source.endswith("_SP") else "nrt"
    return {d: day_entry(d, ps, status) for d, ps in by_date.items()}


def entries_from_pass_archive(year_files: list[Path], region_id: str) -> dict[str, dict]:
    """Bootstrap from already-aggregated mirror SP passes."""
    entries: dict[str, dict] = {}
    for f in year_files:
        passes = json.loads(f.read_text(encoding="utf-8"))
        snpp = score_passes([p for p in passes if p["platform"] == "SNPP"])
        by_date: dict[str, list[dict]] = defaultdict(list)
        for p in snpp:
            by_date[p["date"]].append(p)
        for d, ps in by_date.items():
            entries[d] = day_entry(d, ps, "sp")
    return entries


def merge_days(existing: dict[str, dict], fresh: dict[str, dict]) -> dict[str, dict]:
    """SP wins over NRT; fresh data wins within the same status."""
    out = dict(existing)
    for d, entry in fresh.items():
        cur = out.get(d)
        if cur is None:
            out[d] = entry
            continue
        rank = {"nrt": 0, "sp": 1}
        if rank[entry["status"]] >= rank[cur["status"]]:
            out[d] = entry
    return out


def build_calendar_payload(days: dict[str, dict]) -> dict:
    daily = [days[d] for d in sorted(days)]
    total = round(sum(e["activity"] for e in daily), 1)
    peak = max(daily, key=lambda e: e["activity"], default=None)
    months: dict[str, dict] = {}
    for e in daily:
        m = e["date"][:7]
        slot = months.setdefault(m, {"month": m, "activity": 0.0, "days_reported": 0,
                                     "peak_day": None, "peak_activity": 0.0})
        slot["activity"] = round(slot["activity"] + e["activity"], 3)
        slot["days_reported"] += 1
        if e["activity"] >= slot["peak_activity"]:
            slot["peak_activity"] = e["activity"]
            slot["peak_day"] = e["date"]
    payload = {
        "schema_version": 1,
        "region": {"id": CONFIG["region_id"], "name": CONFIG["name"], "bbox": CONFIG["bbox"]},
        "unit": CONFIG["unit"],
        "timezone": "UTC",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": {
            "name": MODEL["name"],
            "target": MODEL["target"],
            "holdout": MODEL.get("metrics", {}).get("leave_one_year_out_pooled", {}),
            "metrics_by_year": MODEL.get("metrics", {}).get("leave_one_year_out_by_year", {}),
        },
        "warning": "Activity index in MODIS-Aqua-equivalent occupied cells; not burned area, not a fire count, and not a detection-precision estimate. Days without observations are absent, not zero.",
        "stats": {
            "days_reported": len(daily),
            "total_activity": total,
            "peak_day": peak["date"] if peak else None,
            "peak_activity": peak["activity"] if peak else 0.0,
            "first_day": daily[0]["date"] if daily else None,
            "last_day": daily[-1]["date"] if daily else None,
        },
        "months": [months[m] for m in sorted(months)],
        "daily": daily,
    }
    return payload


def load_state() -> dict[str, dict]:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8")).get("days", {})


def chunked_windows(start: date, end: date, chunk: int):
    """Yield (start, days) consecutive windows fully covering [start, end]."""
    cursor = start
    while cursor <= end:
        take = min(chunk, (end - cursor).days + 1)
        yield cursor, take
        cursor = cursor + timedelta(days=take)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", metavar="DERIVED_DIR", default=None,
                    help="Rebuild state from mirror-mined statewide passes (local one-off)")
    ap.add_argument("--offline", action="store_true",
                    help="Rewrite calendar.json from existing state.json without network")
    args = ap.parse_args()

    if args.bootstrap:
        derived = Path(args.bootstrap)
        year_dir = derived / "passes" / "california-state"
        year_files = sorted(year_dir.glob("*.json"))
        if not year_files:
            raise SystemExit(f"no pass files under {year_dir}")
        days = entries_from_pass_archive(year_files, CONFIG["region_id"])
        print(f"bootstrap: {len(days)} days with SNPP passes from {len(year_files)} year files")
    else:
        days = load_state()
        if not args.offline:
            today = date.today()
            fresh_sp: dict[str, dict] = {}
            for start, n in chunked_windows(date(today.year, 1, 1), today, CONFIG["sp_chunk_days"]):
                rows = fetch_rows(CONFIG["sources"]["sp"], CONFIG["bbox"], n, start)
                fresh_sp.update(entries_from_rows(rows, CONFIG["sources"]["sp"], CONFIG["region_id"]))
            nrt_start = today - timedelta(days=CONFIG["nrt_trailing_days"] - 1)
            fresh_nrt: dict[str, dict] = {}
            for start, n in chunked_windows(nrt_start, today, CONFIG["nrt_chunk_days"]):
                rows = fetch_rows(CONFIG["sources"]["nrt"], CONFIG["bbox"], n, start)
                fresh_nrt.update(entries_from_rows(rows, CONFIG["sources"]["nrt"], CONFIG["region_id"]))
            days = merge_days(days, fresh_sp)
            days = merge_days(days, fresh_nrt)
            print(f"sp refresh: {len(fresh_sp)} days; nrt refresh: {len(fresh_nrt)} days; state: {len(days)} days")
        else:
            print(f"offline rebuild from state.json: {len(days)} days")

    atomic_write_json(STATE_PATH, {"schema_version": 1,
                                   "region_id": CONFIG["region_id"],
                                   "model": MODEL["name"],
                                   "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                   "days": days})
    atomic_write_json(CALENDAR_PATH, build_calendar_payload(days))
    print("wrote", STATE_PATH)
    print("wrote", CALENDAR_PATH)


if __name__ == "__main__":
    main()
