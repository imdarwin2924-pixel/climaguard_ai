import re

import numpy as np
import pandas as pd

from .config import ABOVE_NORMAL_SD, LABEL, MIN_CASES
from .db import connect, read_df

# Spellings used by case sources -> names in the district boundaries file (keys: lowercase, no spaces).
ALIASES = {
    "kancheepuram": "Kanchipuram", "thoothukudi": "Tuticorin", "thoothukkudi": "Tuticorin",
    "nilgiris": "The Nilgiris", "viluppuram": "Villupuram", "tiruvallur": "Thiruvallur",
    "thiruvallore": "Thiruvallur", "tiruvarur": "Thiruvarur", "kanyakumari": "Kanniyakumari",
    "trichy": "Tiruchirappalli", "tiruchchirappalli": "Tiruchirappalli", "tiruchirapalli": "Tiruchirappalli",
    "sivagangai": "Sivaganga", "tirupattur": "Tirupathur", "chengalpet": "Chengalpattu",
    "ariyallur": "Ariyalur", "pudukottai": "Pudukkottai", "tiruneveli": "Tirunelveli", "tirupur": "Tiruppur",
}


def canonical_name(raw, known):
    """Tolerates words broken across PDF lines ("Ramanathapur am") and health-unit names
    ("Virudhunagar-Sivakasi" -> Virudhunagar, the revenue district before the hyphen)."""
    key = re.sub(r"\s+", "", str(raw)).lower().split("-")[0]
    if key in ALIASES:
        return ALIASES[key]
    for name in known:
        if re.sub(r"\s+", "", name).lower() == key:
            return name
    return None


def import_cases(df, source):
    """Load monthly district cases (columns: district, year, month, cases[, outbreaks]) into dengue_monthly.

    Refuses the whole file if any district name is unknown, so a typo never silently drops data.
    """
    known = set(read_df("SELECT name FROM districts")["name"])
    df = df.copy()
    df["district"] = [canonical_name(d, known) for d in df["district"]]
    if df["district"].isna().any():
        raise ValueError(f"Unknown district names: {sorted(set(df.loc[df['district'].isna(), 'district']))}")
    if "outbreaks" not in df:
        df["outbreaks"] = None
    df = df.groupby(["district", "year", "month"], as_index=False).agg(
        cases=("cases", "sum"), outbreaks=("outbreaks", lambda s: None if s.isna().all() else int(s.sum())))
    with connect() as conn, conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO dengue_monthly (district, year, month, cases, outbreaks, source) VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (district, year, month) DO UPDATE SET cases = EXCLUDED.cases,
                 outbreaks = EXCLUDED.outbreaks, source = EXCLUDED.source""",
            [(r.district, int(r.year), int(r.month), int(r.cases), r.outbreaks, source) for r in df.itertuples()],
        )
    return len(df)


def label_months(cases):
    """Leave-one-year-out normal level per district-month (design §0).

    Returns district, year, month, cases, baseline (mean of the other years) and above_normal
    (cases > mean + ABOVE_NORMAL_SD * sd of the other years, and >= MIN_CASES). NaN when fewer
    than two other years exist.
    """
    rows = []
    for (district, month), g in cases.groupby(["district", "month"]):
        for r in g.itertuples():
            others = g.loc[g["year"] != r.year, "cases"].astype(float)
            if len(others) < 2:
                rows.append((district, r.year, month, r.cases, np.nan, np.nan))
                continue
            limit = others.mean() + ABOVE_NORMAL_SD * others.std()
            rows.append((district, r.year, month, r.cases, others.mean(),
                         float(r.cases > limit and r.cases >= MIN_CASES)))
    return pd.DataFrame(rows, columns=["district", "year", "month", "cases", "baseline", "above_normal"])


def label_outbreaks(cases):
    """Outbreak label: 1 if an IDSP dengue outbreak was reported that district-month.

    Needs a full grid (zero rows for months without outbreaks). Baseline = share of the other
    years with an outbreak in the same month; NaN when fewer than two other years exist.
    """
    df = cases.assign(above_normal=(cases["outbreaks"] > 0).astype(float))
    g = df.groupby(["district", "month"])["above_normal"]
    n, hits = g.transform("count"), g.transform("sum")
    df["baseline"] = ((hits - df["above_normal"]) / (n - 1)).where(n >= 3)
    return df[["district", "year", "month", "cases", "baseline", "above_normal"]]


def labels(cases):
    return label_outbreaks(cases) if LABEL == "outbreak" else label_months(cases)


def live_baseline(cases):
    """Per district and calendar month over every year: outbreak share, or mean cases (used for live runs)."""
    signal = (cases["outbreaks"] > 0).astype(float) if LABEL == "outbreak" else cases["cases"]
    return (cases.assign(baseline=signal).groupby(["district", "month"], as_index=False)["baseline"].mean())
