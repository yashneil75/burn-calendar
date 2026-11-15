"""Minimal NASA FIRMS area CSV client with caching-friendly semantics.

Only the endpoints needed for the daily California refresh. The map key is
read from the FIRMS_MAP_KEY environment variable and is never logged.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import time
from datetime import date, datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API_BASE = "https://firms.modaps.eosdis.nasa.gov"
USER_AGENT = "califire/1.0 (+https://github.com/yashneil75/califire)"


class FIRMSClientError(RuntimeError):
    pass


def fetch_rows(source: str, bbox: list[float], days: int, start: date,
               timeout: float = 30.0, retries: int = 6) -> list[dict]:
    """Fetch `days` of FIRMS detections ending at `start` + `days` - 1."""
    key = os.environ.get("FIRMS_MAP_KEY")
    if not key:
        raise FIRMSClientError("FIRMS_MAP_KEY is not set")
    box = ",".join(f"{v:.4f}".rstrip("0").rstrip(".") for v in bbox)
    url = (
        f"{API_BASE}/api/area/csv/{quote(key, safe='')}/"
        f"{quote(source, safe='')}/{quote(box, safe=',')}/{int(days)}/{start.isoformat()}"
    )
    body: bytes | None = None
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=timeout) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                body = resp.read().decode(charset, errors="replace").encode("utf-8")
            break
        except HTTPError as exc:
            last_error = exc
            # 4xx means the request itself will not fix itself by retrying.
            if 400 <= exc.code < 500:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "replace").strip().replace("\n", " ")[:160]
                except Exception:
                    pass
                raise FIRMSClientError(f"FIRMS API returned HTTP {exc.code} for {source}: {detail}") from None
        except (URLError, TimeoutError) as exc:
            last_error = exc
        if body is None and attempt < retries - 1:
            time.sleep(2 ** attempt)
    if body is None:
        raise FIRMSClientError(f"FIRMS API request failed for {source}: {last_error}")

    text = body.decode("utf-8", errors="replace").lstrip("﻿").strip()
    if not text:
        return []
    if text.lower().startswith(("invalid", "error", "no such")):
        raise FIRMSClientError(f"FIRMS API rejected the request for {source}")
    rows = []
    for record in csv.DictReader(io.StringIO(text)):
        record["_source"] = source
        rows.append(record)
    return rows


def sha256(body_text: str) -> str:
    return hashlib.sha256(body_text.encode("utf-8")).hexdigest()
