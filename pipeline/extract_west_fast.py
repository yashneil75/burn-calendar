"""Backfill the missing Cape Mendocino strip using GeoParquet row-group bounds.

Requires duckdb (httpfs), pyarrow, requests and shapely. The source's native
GeoParquet 2.0 geographic statistics identify candidate row groups; every
candidate is then read and filtered by its actual point coordinates.
"""
import io
import os
import ssl
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import requests
from shapely import from_wkb, get_x, get_y

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/harmonization/raw"
BASE = "https://data.source.coop/portolan-mirrors/firms-catalog/detections"


class RangeFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos = url, 0
        self.session = requests.Session()
        response = self.session.head(url, timeout=30)
        response.raise_for_status()
        self.size = int(response.headers["Content-Length"])

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos

    def read(self, n=-1):
        if n < 0:
            n = self.size - self.pos
        if n <= 0 or self.pos >= self.size:
            return b""
        end = min(self.pos + n, self.size) - 1
        response = self.session.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=60)
        response.raise_for_status()
        if response.status_code != 206 or len(response.content) != end - self.pos + 1:
            raise IOError("source did not return the requested byte range")
        self.pos += len(response.content)
        return response.content

    def close(self):
        self.session.close()
        super().close()


def main():
    con = duckdb.connect()
    con.execute("LOAD httpfs")
    ca = None
    try:
        if os.name == "nt" and hasattr(ssl, "enum_certificates"):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
                ca = f.name
                for store in ("ROOT", "CA"):
                    for cert, enc, _ in ssl.enum_certificates(store):
                        if enc == "x509_asn":
                            f.write(ssl.DER_cert_to_PEM_cert(cert))
            con.execute("SET ca_cert_file = ?", [ca])
        for year in range(2012, 2027):
            target = RAW / f"{year}.west.parquet"
            if target.exists():
                print(f"{year}: already available", flush=True)
                continue
            url = f"{BASE}/year={year}/detections.parquet"
            print(f"{year}: inspect row-group bounds", flush=True)
            stats = con.execute("""SELECT row_group_id, geo_bbox FROM parquet_metadata(?)
                WHERE path_in_schema = 'geometry' ORDER BY row_group_id""", [url]).fetchall()
            if not stats or any(bbox is None for _, bbox in stats):
                raise ValueError(f"missing geographic statistics in {year}; cannot safely skip row groups")
            groups = [int(i) for i, b in stats if b['xmin'] <= -124.4 and b['xmax'] >= -124.41
                      and b['ymin'] <= 40.46 and b['ymax'] >= 40.42]
            print(f"{year}: reading {len(groups)} of {len(stats)} row groups", flush=True)
            with RangeFile(url) as source:
                pf = pq.ParquetFile(source, pre_buffer=True)
                if pf.num_row_groups != len(stats):
                    raise ValueError(f"source changed while reading {year}")
                table = pf.read_row_groups(groups) if groups else pf.schema_arrow.empty_table()
                geom = from_wkb(table.column("geometry").to_pylist())
                lon, lat = get_x(geom), get_y(geom)
                keep = (lon >= -124.41) & (lon < -124.4) & (lat >= 40.42) & (lat <= 40.46)
                table = table.append_column("longitude", pa.array(lon))
                table = table.append_column("latitude", pa.array(lat))
                table = table.filter(pa.array(keep))
                tmp = target.with_suffix(".parquet.part")
                try:
                    pq.write_table(table, tmp, compression="zstd")
                    os.replace(tmp, target)
                finally:
                    tmp.unlink(missing_ok=True)
                print(f"{year}: {len(table)} detections", flush=True)
    finally:
        con.close()
        if ca:
            Path(ca).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
