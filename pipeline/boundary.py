"""Filter detection centres to the project's Natural Earth California boundary."""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from shapely import intersects_xy, prepare
from shapely.geometry import shape


@lru_cache(maxsize=1)
def california():
    path = Path(__file__).resolve().parent.parent / "docs/assets/california.geojson"
    data = json.loads(path.read_text(encoding="utf-8"))
    geometry = shape(data["features"][0]["geometry"])
    prepare(geometry)
    return geometry


def within_california(longitudes, latitudes):
    """Include points on the boundary as well as points inside it."""
    return intersects_xy(california(), np.asarray(longitudes, dtype=float),
                         np.asarray(latitudes, dtype=float))
