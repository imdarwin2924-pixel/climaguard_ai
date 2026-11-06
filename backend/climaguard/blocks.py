"""E4-S1: field priority units and their vulnerability index.

Units are Census 2011 sub-districts (taluks): the finest level with free boundaries and population.
Vulnerability (equal weights, ranked within the current district) = population density, share of
children 0-6, and past IDSP dengue outbreaks whose report names the unit. Older adults are left
out: Census age bands are published only per district, so they cannot rank units inside one.
"""
import difflib
import json
import re

import pandas as pd
from psycopg.types.json import Jsonb

from .cases import canonical_name
from .config import DATASET_DIR
from .db import connect, read_df
from .districts import centroid

SUBDISTRICTS = DATASET_DIR / "TAMILNADU_SUBDISTRICTS.geojson"
DISTRICTS = DATASET_DIR / "TAMIL NADU_DISTRICTS.geojson"
CENSUS_DIR = DATASET_DIR / "census"
OUTBREAKS = DATASET_DIR / "idsp_tn_dengue_outbreaks.csv"
FACTORS = ["density", "child_share", "past_outbreaks"]


def _inside(lon, lat, ring):
    hit = False
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        if (y0 > lat) != (y1 > lat) and lon < x0 + (lat - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def point_in(lon, lat, geometry):
    polys = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    return any(_inside(lon, lat, [tuple(p[:2]) for p in poly[0]]) for poly in polys)


def _key(name):
    return re.sub(r"[^a-z]", "", str(name).lower())


def match_unit(block, candidates):
    """Outbreak 'Block X' -> unit name among candidates (fuzzy, spelling varies). None if no close match."""
    keys = {_key(c): c for c in candidates}
    hit = difflib.get_close_matches(_key(block), list(keys), n=1, cutoff=0.8)
    return keys[hit[0]] if hit else None


def vulnerability(units):
    """Mean of within-district percentile ranks of the factors (0-1, higher = more vulnerable)."""
    pct = units.groupby("district_id")[FACTORS].rank(pct=True)
    return pct.mean(axis=1), pct


# SMS wording for each action (keyed by how the action starts), so outbox messages fit 160 characters.
SMS_ACTION = {
    "Dengue outbreak": "revisit past outbreak villages",
    "Dense housing": "check tanks, building sites, tyres",
    "Many young children": "start with schools and anganwadis",
    "Check stored water": "check stored water in homes",
}


def sms_action(action):
    return next(short for start, short in SMS_ACTION.items() if action.startswith(start))


def actions(row, pct):
    """What to check first, most specific first; every unit gets at least the stored-water check."""
    out = []
    if row["past_outbreaks"] > 0:
        out.append(f"Dengue outbreak reported here before ({int(row['past_outbreaks'])}×): revisit those villages first")
    if pct["density"] >= 0.67:
        out.append("Dense housing: check overhead tanks, construction sites and discarded tyres street by street")
    if pct["child_share"] >= 0.67:
        out.append("Many young children: start with schools and anganwadis")
    out.append("Check stored water in every house: empty, scrub or cover drums, pots and tanks")
    return out


def load_units():
    districts_geo = json.loads(DISTRICTS.read_text(encoding="utf8"))["features"]
    db_districts = read_df("SELECT id, name, history_of FROM districts")
    district_id = dict(zip(db_districts["name"], db_districts["id"]))

    units = []
    for f in json.loads(SUBDISTRICTS.read_text(encoding="utf8"))["features"]:
        p = f["properties"]
        lat, lon = centroid(f["geometry"])
        current = next((g["properties"]["dtname"].strip() for g in districts_geo if point_in(lon, lat, g["geometry"])), None)
        if current is None:  # centroid of a coastal unit can fall in the sea: use the 2011 district name
            current = canonical_name(p["dtname"], set(district_id))
        units.append({"sdt_code": int(p["sdtcode11"]), "dt_code": int(p["dtcode11"]), "name": p["sdtname"].strip(),
                      "district_id": district_id[current], "area_km2": p["Shape_Area"] / 1e6})
    units = pd.DataFrame(units)

    census = pd.concat(pd.read_excel(f) for f in sorted(CENSUS_DIR.glob("PCA_TV_*.xlsx")))
    census = census[(census["Level"] == "SUB-DISTRICT") & (census["TRU"] == "Total")]
    units = units.merge(census[["Subdistt", "TOT_P", "P_06"]].rename(columns={"Subdistt": "sdt_code"}), on="sdt_code", how="left")
    # Single-sub-district districts (Chennai) carry code 99999 in the census: match those by district code.
    solo = census.groupby("District").filter(lambda g: len(g) == 1).set_index("District")
    gap = units["TOT_P"].isna() & units["dt_code"].isin(solo.index)
    units.loc[gap, ["TOT_P", "P_06"]] = solo.loc[units.loc[gap, "dt_code"], ["TOT_P", "P_06"]].to_numpy()
    missing = units[units["TOT_P"].isna()]
    if len(missing):
        raise RuntimeError(f"No census row for sub-districts: {missing['name'].tolist()}")
    units["population"] = units["TOT_P"].astype(int)
    units["density"] = units["population"] / units["area_km2"]
    units["child_share"] = units["P_06"] / units["TOT_P"]

    # Past outbreaks: the report's district (old or new name) shares its case history with the unit's district.
    history = dict(zip(db_districts["id"], db_districts["history_of"]))
    units["history_of"] = units["district_id"].map(history)
    units["past_outbreaks"] = 0
    unmatched = []
    if OUTBREAKS.exists():
        o = pd.read_csv(OUTBREAKS).dropna(subset=["block"])
        known = set(district_id)
        for r in o.itertuples():
            d = canonical_name(r.district, known)
            pool = units[units["history_of"] == history.get(district_id.get(d))]
            name = match_unit(r.block, pool["name"])
            if name:
                units.loc[pool.index[pool["name"] == name], "past_outbreaks"] += 1
            else:
                unmatched.append(f"{r.block} ({r.district})")

    units["vulnerability"], pct = vulnerability(units)
    with connect() as conn:
        # Upsert on the census code: block ids must stay stable, nurse assignments point at them.
        conn.cursor().executemany(
            """INSERT INTO blocks (sdt_code, name, district_id, population, density, child_share, past_outbreaks,
                                   vulnerability, factor_pct, actions) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (sdt_code) DO UPDATE SET name = EXCLUDED.name, district_id = EXCLUDED.district_id,
                 population = EXCLUDED.population, density = EXCLUDED.density, child_share = EXCLUDED.child_share,
                 past_outbreaks = EXCLUDED.past_outbreaks, vulnerability = EXCLUDED.vulnerability,
                 factor_pct = EXCLUDED.factor_pct, actions = EXCLUDED.actions""",
            [(int(u.sdt_code), u["name"], int(u.district_id), int(u.population), float(u.density), float(u.child_share),
              int(u.past_outbreaks), float(u.vulnerability), Jsonb({k: round(float(pct.loc[i, k]), 3) for k in FACTORS}),
              Jsonb(actions(units.loc[i], pct.loc[i])))
             for i, u in units.iterrows()],
        )
    return {"units": len(units), "with_past_outbreaks": int((units["past_outbreaks"] > 0).sum()),
            "outbreaks_matched": int(units["past_outbreaks"].sum()), "outbreak_blocks_unmatched": len(unmatched)}
