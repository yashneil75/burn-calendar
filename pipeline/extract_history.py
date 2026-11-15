"""Download historical FIRMS bounding-box extracts for the California rebuild.

Requires DuckDB with httpfs and spatial extensions. The mirror is mutable;
retain extracts locally to reproduce a rebuild.
"""
import argparse
import os
import ssl
import tempfile
import time
from pathlib import Path

import duckdb

BASE = "https://data.source.coop/portolan-mirrors/firms-catalog/detections"
ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start-year", type=int, default=2000)
    ap.add_argument("--end-year", type=int, default=2014)
    ap.add_argument("--west-strip", action="store_true", help="download the strip omitted by older extracts")
    ap.add_argument("--out", type=Path, default=ROOT / "data/harmonization/raw")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("LOAD httpfs"); con.execute("LOAD spatial")
    con.execute("SET http_timeout = 15")
    con.execute("SET http_retries = 1")
    ca = None
    try:
        if os.name == "nt" and hasattr(ssl, "enum_certificates"):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
                ca = f.name
                for store in ("ROOT", "CA"):
                    for cert, encoding, _ in ssl.enum_certificates(store):
                        if encoding == "x509_asn":
                            f.write(ssl.DER_cert_to_PEM_cert(cert))
            con.execute("SET ca_cert_file = ?", [ca])
        for year in range(args.start_year, args.end_year + 1):
            target = args.out / (f"{year}.west.parquet" if args.west_strip else f"{year}.parquet")
            if target.exists():
                print(f"{year}: already available", flush=True); continue
            tmp = target.with_suffix(".parquet.part")
            url = f"{BASE}/year={year}/detections.parquet"
            print(f"{year}: downloading", flush=True)
            try:
                dest = str(tmp).replace("'", "''")
                # The only part of the Natural Earth California polygon west of
                # -124.4 lies within this small envelope near Cape Mendocino.
                # ST_Intersects lets GeoParquet skip unrelated spatial row groups.
                west_clause = ("ST_Intersects(geometry, ST_MakeEnvelope(-124.41, 40.42, -124.4, 40.46)) "
                               "AND ST_X(geometry) < -124.4" if args.west_strip
                               else "ST_X(geometry) BETWEEN -124.4 AND -114.1")
                for attempt in range(4):
                    try:
                        con.execute(f"""COPY (SELECT *, ST_X(geometry) AS longitude, ST_Y(geometry) AS latitude
                            FROM read_parquet(?) WHERE {west_clause}
                            AND ST_Y(geometry) BETWEEN 32.5 AND 42.0)
                            TO '{dest}' (FORMAT PARQUET, COMPRESSION ZSTD)""", [url])
                        break
                    except duckdb.Error:
                        tmp.unlink(missing_ok=True)
                        if attempt == 3:
                            raise
                        print(f"{year}: retrying after connection error", flush=True)
                        time.sleep(2 ** attempt)
                count = con.execute("select count(*) from read_parquet(?)", [str(tmp)]).fetchone()[0]
                if not count and not args.west_strip:
                    raise ValueError(f"empty source extract for {year}")
                os.replace(tmp, target)
                print(f"{year}: {count:,} rows", flush=True)
            finally:
                tmp.unlink(missing_ok=True)
    finally:
        con.close()
        if ca:
            Path(ca).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
