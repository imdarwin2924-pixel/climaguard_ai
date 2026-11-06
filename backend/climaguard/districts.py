import json

from .config import DATASET_DIR, PARENT
from .db import connect

GEOJSON = DATASET_DIR / "TAMIL NADU_DISTRICTS.geojson"


def ring_centroid(ring):
    """Area-weighted centroid of one polygon ring (shoelace), in lon/lat."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a /= 2
    return abs(a), cx / (6 * a), cy / (6 * a)


def centroid(geometry):
    polys = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    parts = [ring_centroid([tuple(p[:2]) for p in poly[0]]) for poly in polys]
    total = sum(a for a, _, _ in parts)
    lon = sum(a * x for a, x, _ in parts) / total
    lat = sum(a * y for a, _, y in parts) / total
    return lat, lon


def load_districts():
    """Seed the 38 districts from the boundaries file; weather is fetched at each centroid."""
    features = json.loads(GEOJSON.read_text(encoding="utf8"))["features"]
    with connect() as conn:
        for f in features:
            name = f["properties"]["dtname"].strip()
            lat, lon = centroid(f["geometry"])
            area = f["properties"].get("st_area(shape)")
            conn.execute(
                """INSERT INTO districts (name, history_of, lat, lon, area_km2)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (name) DO UPDATE SET history_of = EXCLUDED.history_of,
                     lat = EXCLUDED.lat, lon = EXCLUDED.lon, area_km2 = EXCLUDED.area_km2""",
                (name, PARENT.get(name, name), lat, lon, area / 1e6 if area else None),
            )
    return len(features)
