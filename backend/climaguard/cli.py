"""Pipeline commands. Run from backend/:  python -m climaguard.cli <command>"""
import argparse
import datetime as dt
import json

import pandas as pd

from . import auth, blocks, cases, db, districts, idsp, index, model, weather
from .config import DATASET_DIR, INDEX_LEVELS


def main():
    p = argparse.ArgumentParser(prog="climaguard")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db", help="create tables and load the 38 districts")
    h = sub.add_parser("fetch-history", help="observed weather for training")
    h.add_argument("--start", default="2017-01-01")
    h.add_argument("--end", default="2021-03-31")
    i = sub.add_parser("import-cases", help="CSV with columns district,year,month,cases")
    i.add_argument("file")
    i.add_argument("--source", required=True, help="e.g. 'Indiastat IPD 2017-18'")
    o = sub.add_parser("import-idsp", help="parse IDSP weekly outbreak PDFs in dataset/idsp_weekly")
    o.add_argument("--start", default="2017-01")
    o.add_argument("--end", required=True, help="last fully reported month, e.g. 2026-08")
    o.add_argument("--reuse-csv", action="store_true", help="skip PDF parsing, reuse the last parsed CSV")
    sub.add_parser("train", help="train, backtest on the latest season, save the model")
    sub.add_parser("load-blocks", help="sub-district units, census and past outbreaks -> vulnerability index")
    sub.add_parser("calibrate-index", help="build the index's district-month climatology and check it against outbreaks")
    ad = sub.add_parser("create-admin", help="first state admin account; prints a one-time password")
    ad.add_argument("--name", required=True)
    ad.add_argument("--email", required=True)
    sub.add_parser("run-live", help="fetch live weather and score today (schedule this daily)")
    a = p.parse_args()

    if a.cmd == "init-db":
        db.init_schema()
        print(f"{districts.load_districts()} districts loaded")
    elif a.cmd == "fetch-history":
        weather.fetch_history(a.start, a.end)
    elif a.cmd == "import-cases":
        print(f"{cases.import_cases(pd.read_csv(a.file), a.source)} district-months imported")
    elif a.cmd == "import-idsp":
        parsed = DATASET_DIR / "idsp_tn_dengue_outbreaks.csv"  # row-level, for audit
        if a.reuse_csv:
            rows = pd.read_csv(parsed)
        else:
            rows = idsp.parse_all(DATASET_DIR / "idsp_weekly")
            rows.to_csv(parsed, index=False)
        monthly, unknown = idsp.to_monthly(rows, db.read_df("SELECT name, history_of FROM districts"), a.start, a.end)
        if unknown:
            raise SystemExit(f"Unknown district names, add them to cases.ALIASES: {unknown}")
        print(f"{len(rows)} TN dengue outbreaks, {int((monthly['outbreaks'] > 0).sum())} outbreak district-months")
        print(f"{cases.import_cases(monthly, 'IDSP weekly outbreak reports')} district-months imported")
    elif a.cmd == "train":
        print(json.dumps(model.train_and_backtest(), indent=2))
    elif a.cmd == "load-blocks":
        print(blocks.load_units())
    elif a.cmd == "calibrate-index":
        _, feats, history = model._load_inputs()
        feats = feats[feats["date"] < pd.Timestamp(dt.date.today())]
        index.MODEL_DIR.mkdir(exist_ok=True)
        index.CLIMATOLOGY_FILE.write_text(json.dumps(index.calibrate(feats)))
        labels = cases.labels(history)
        report = index.validate(feats, labels)
        index.VALIDATION_FILE.write_text(json.dumps(report, indent=2))
        history["season"] = model.season_of(history["year"], history["month"])
        per_season = history.groupby("season")["month"].nunique()
        season = int(per_season[per_season == 12].index.max())  # latest season with all 12 months reported
        fb = index.feedback(feats, labels, season, INDEX_LEVELS)
        index.FEEDBACK_FILE.write_text(json.dumps(fb))
        print("feedback", fb["season"], fb["state"])
        print(json.dumps({k: report[k] for k in ["auc_all", "level_share", "outbreak_rate_by_level"]}, indent=2))
    elif a.cmd == "create-admin":
        temporary = auth.temporary_password()
        with db.connect() as conn:
            conn.execute("INSERT INTO staff (name, email, role, password_hash) VALUES (%s, %s, 'admin', %s)",
                         (a.name.strip(), auth.normalise_login(a.email), auth.hash_password(temporary)))
        print(f"Admin created. One-time password (shown once, change it at first sign-in): {temporary}")
    elif a.cmd == "run-live":
        weather.fetch_live(dt.date.today())
        print(model.score_live())


if __name__ == "__main__":
    main()
