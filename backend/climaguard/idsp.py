"""Tamil Nadu dengue outbreaks from IDSP weekly outbreak reports (NCDC PDFs).

Each report row: unique ID (TN/ERO/2019/40/1292), state, district, disease, cases, deaths,
date of start, date of report, status, action. Later reports can repeat an ID as a follow-up,
so rows are de-duplicated on the ID.
"""
import datetime as dt
import re

import pandas as pd
import pdfplumber

ID_RE = re.compile(r"^TN/[A-Z]+/(\d{4})/(\d{1,2})/\d+")


def _int(text):
    m = re.search(r"\d+", text or "")
    return int(m.group()) if m else None


def _date(text):
    m = re.search(r"(\d{1,2})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{2,4})", text or "")
    if not m:
        return None
    d, mo, y = (int(g) for g in m.groups())
    y += 2000 if y < 100 else 0
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


ANY_ID_RE = re.compile(r"^[A-Z]{2}/[A-Z]+/\d{4}/")
BLOCK_RE = re.compile(r"Block\s*[:\-]?\s*([A-Z][A-Za-z.\s]{2,40}?)(?=[,.;]|\s+District|\s+PHC|\s+HSC|$)")


def block_of(details):
    """'... PHC Neikarapatti, Block Palani. District RRT ...' -> 'Palani' (None if no block named)."""
    m = BLOCK_RE.search(details or "")
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def parse_pdf(path):
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                current = None
                for r in table:
                    cells = [(c or "").replace("\n", " ").strip() for c in r]
                    if cells and ANY_ID_RE.match(cells[0]):
                        current = None  # a new outbreak row ends the previous one's description
                    elif current is not None:  # continuation line of the description column
                        current["details"] += " " + " ".join(c for c in cells if c)
                        continue
                    m = ID_RE.match(cells[0]) if cells else None
                    if not m or len(cells) < 8 or "dengue" not in cells[3].lower().replace(" ", ""):
                        continue
                    current = {"outbreak_id": cells[0].split()[0], "district": cells[2], "disease": cells[3],
                               "cases": _int(cells[4]), "deaths": _int(cells[5]) or 0,
                               "start_date": _date(cells[6]), "report_date": _date(cells[7]),
                               "id_year": int(m.group(1)), "id_week": int(m.group(2)), "file": str(path.name),
                               "details": " ".join(c for c in cells[9:] if c)}
                    rows.append(current)
    for row in rows:
        row["block"] = block_of(row["details"])
    return rows


def week_start(year, week):
    return dt.date.fromisocalendar(year, min(max(week, 1), 52), 1)


def parse_all(folder):
    rows = []
    for pdf in sorted(folder.rglob("*.pdf")):
        try:
            rows += parse_pdf(pdf)
        except Exception as e:  # a damaged PDF should not stop the other ~500
            print(f"skip {pdf.name}: {e}")
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates("outbreak_id", keep="first")
    # Onset month; fall back to report date, then the ID's week.
    # Typos in dates are common, so an onset more than 60 days from the ID's week is replaced by that week.
    df["id_date"] = [week_start(y, w) for y, w in zip(df["id_year"], df["id_week"])]
    df["onset"] = df["start_date"].fillna(df["report_date"])
    bad = df["onset"].isna() | (pd.to_datetime(df["onset"]) - pd.to_datetime(df["id_date"])).abs().dt.days.gt(60)
    df.loc[bad, "onset"] = df.loc[bad, "id_date"]
    return df


def to_monthly(outbreaks, districts, start, end):
    """Full grid of parent districts x months from start to end: cases and outbreak counts (0 when none).

    New districts are counted under their parent so the series stays comparable across the 2019-20 split.
    """
    from .cases import canonical_name

    known = set(districts["name"])
    parent = dict(zip(districts["name"], districts["history_of"]))
    names = [canonical_name(d, known) for d in outbreaks["district"]]
    unknown = sorted({d for d, n in zip(outbreaks["district"], names) if n is None})
    o = outbreaks.assign(district=[parent.get(n) for n in names]).dropna(subset=["district"])
    onset = pd.to_datetime(o["onset"])
    o = o.assign(year=onset.dt.year, month=onset.dt.month, cases=o["cases"].fillna(0))
    o = o[(onset >= pd.Timestamp(start)) & (onset < (pd.Period(end, "M") + 1).start_time)]
    agg = o.groupby(["district", "year", "month"]).agg(cases=("cases", "sum"), outbreaks=("outbreak_id", "count"))
    months = pd.period_range(start, end, freq="M")
    grid = pd.MultiIndex.from_tuples([(d, p.year, p.month) for d in sorted(set(parent.values())) for p in months],
                                     names=["district", "year", "month"])
    monthly = agg.reindex(grid, fill_value=0).reset_index()
    return monthly, unknown
