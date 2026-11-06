import datetime as dt
import json

import numpy as np
import pandas as pd
import xgboost as xgb
from psycopg.types.json import Jsonb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .cases import labels, live_baseline
from . import index, staff
from .config import HORIZONS, INDEX_LEVELS, LEVELS, MODEL_DIR, RISK_ENGINE
from .db import connect, read_df
from .drivers import to_cards
from .features import FEATURES, add_season, weather_features
from .risk import alert_reason, level_for

MODEL_FILE = MODEL_DIR / "dengue_xgb.json"
META_FILE = MODEL_DIR / "dengue_meta.json"
HIGH = 0.5


def season_of(year, month):
    """Indian fiscal season, April-March, as its starting year."""
    return np.where(np.asarray(month) >= 4, year, np.asarray(year) - 1)


def _xgb():
    return xgb.XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8,
                             colsample_bytree=0.8, eval_metric="logloss")


def _load_inputs():
    districts = read_df("SELECT id AS district_id, name, history_of FROM districts")
    weather = read_df("SELECT district_id, date, temp_mean, humidity_mean, precip FROM weather_daily "
                      "WHERE NOT is_forecast")
    cases = read_df("SELECT district, year, month, cases, outbreaks FROM dengue_monthly")
    if cases.empty:
        raise RuntimeError("No dengue cases imported yet: run `python -m climaguard.cli import-cases <file>` first")
    feats = weather_features(weather).merge(districts, on="district_id")
    feats["year"], feats["month"] = feats["date"].dt.year, feats["date"].dt.month
    return districts, add_season(feats), cases


def _examples(feats, labels):
    # Only districts with their own case history train the model; new districts would copy parent labels.
    own = feats[feats["name"] == feats["history_of"]]
    ex = own.merge(labels, left_on=["name", "year", "month"], right_on=["district", "year", "month"])
    ex = ex.dropna(subset=["above_normal", "baseline"])
    ex["baseline"] = np.log1p(ex["baseline"])
    return ex


def _contribs(model, X):
    # XGBoost's built-in TreeSHAP: exact per-row SHAP values; last column is the bias.
    return model.get_booster().predict(xgb.DMatrix(X[FEATURES]), pred_contribs=True)[:, :-1]


def _levels():
    return INDEX_LEVELS if RISK_ENGINE == "index" else LEVELS


def _save_risk(conn, run_id, rows):
    conn.cursor().executemany(
        "INSERT INTO risk (run_id, district_id, horizon, probability, level, drivers) VALUES (%s,%s,%s,%s,%s,%s)",
        [(run_id, int(r["district_id"]), int(r["horizon"]), float(r["probability"]), level_for(r["probability"], _levels()),
          Jsonb(to_cards(r["contribs"] if isinstance(r["contribs"], dict) else dict(zip(FEATURES, r["contribs"])))))
         for r in rows],
    )


def train_and_backtest():
    """Hold out the latest season, score it against the baselines, then refit on every season."""
    _, feats, cases = _load_inputs()
    cases["season"] = season_of(cases["year"], cases["month"])
    months_per_season = cases.groupby("season")["month"].nunique()
    holdout = int(months_per_season[months_per_season == 12].index.max())  # latest complete season
    train_labels = labels(cases[cases["season"] < holdout])  # holdout cases never shape training labels
    test_labels = labels(cases[cases["season"] <= holdout])
    test_labels = test_labels[season_of(test_labels["year"], test_labels["month"]) == holdout]

    train = _examples(feats[feats["date"].dt.weekday == 0], train_labels)  # one example per district-week
    if train["above_normal"].sum() < 5:
        raise RuntimeError(f"Only {int(train['above_normal'].sum())} above-normal months in training data")
    model = _xgb().fit(train[FEATURES], train["above_normal"])
    logit = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)).fit(train[FEATURES], train["above_normal"])

    # Backtest runs: every Monday of the held-out season, both horizons; target = run + horizon.
    test_all = _examples(feats, test_labels)
    runs = []
    for h in HORIZONS:
        t = test_all.copy()
        t["run_date"], t["horizon"] = t["date"] - pd.Timedelta(days=h), h
        runs.append(t[t["run_date"].dt.weekday == 0])
    test = pd.concat(runs, ignore_index=True)
    test["p_model"] = model.predict_proba(test[FEATURES])[:, 1]
    test["p_logit"] = logit.predict_proba(test[FEATURES])[:, 1]
    last_year = train_labels.assign(year=train_labels["year"] + 1)[["district", "year", "month", "above_normal"]]
    test = test.merge(last_year.rename(columns={"above_normal": "p_last_year"}), on=["district", "year", "month"], how="left")
    test["p_last_year"] = test["p_last_year"].fillna(0.0)

    metrics = backtest_metrics(test, test_labels)
    metrics["holdout_season"] = f"{holdout}-{str(holdout + 1)[-2:]}"
    metrics["train_examples"], metrics["train_positives"] = len(train), int(train["above_normal"].sum())
    _store_backtest(model, test)

    final = _examples(feats[feats["date"].dt.weekday == 0], labels(cases))
    model = _xgb().fit(final[FEATURES], final["above_normal"])
    MODEL_DIR.mkdir(exist_ok=True)
    model.save_model(MODEL_FILE)
    version = dt.datetime.now().strftime("%Y%m%d-%H%M")
    META_FILE.write_text(json.dumps({"version": version, "features": FEATURES, "backtest": metrics}, indent=2))
    return metrics


def backtest_metrics(test, test_labels):
    """PRD §4 metrics. Month-level detection and lead time; run-level Brier and false alarms."""
    out = {}
    for col in ["p_model", "p_logit", "p_last_year"]:
        out[f"brier_{col[2:]}"] = round(brier_score_loss(test["above_normal"], test[col]), 4)
        if test["above_normal"].nunique() == 2:
            out[f"auc_{col[2:]}"] = round(roc_auc_score(test["above_normal"], test[col]), 4)

    positives = test_labels[test_labels["above_normal"] == 1]
    detected, leads = 0, []
    for m in positives.itertuples():
        start = pd.Timestamp(m.year, m.month, 1)
        early = test[(test["district"] == m.district) & (test["year"] == m.year) & (test["month"] == m.month)
                     & (test["run_date"] < start) & (test["p_model"] >= HIGH)]
        if len(early):
            detected += 1
            leads.append((start - early["run_date"].min()).days / 7)
    n = len(positives)
    last_year_hits = test.drop_duplicates(["district", "year", "month"])
    last_year_hits = last_year_hits[(last_year_hits["above_normal"] == 1) & (last_year_hits["p_last_year"] == 1)]
    flags = test[test["p_model"] >= HIGH]
    out.update({
        "above_normal_months": n,
        "detection_rate_model": round(detected / n, 3) if n else None,
        "detection_rate_last_year": round(len(last_year_hits) / n, 3) if n else None,
        "lead_time_weeks_median": float(np.median(leads)) if leads else None,
        "share_detected_with_2wk_lead": round(sum(l >= 2 for l in leads) / len(leads), 3) if leads else None,
        "false_alarm_rate": round(float((flags["above_normal"] == 0).mean()), 3) if len(flags) else None,
        "forecast_assumption": "observed weather used as a perfect forecast",
    })
    return out


def _store_backtest(model, test):
    contribs = _contribs(model, test)
    with connect() as conn:
        conn.execute("DELETE FROM runs WHERE kind = 'backtest'")
        for run_date, g in test.assign(contribs=list(contribs)).groupby("run_date"):
            run_id = conn.execute("INSERT INTO runs (run_date, kind, model_version) VALUES (%s, 'backtest', 'backtest') "
                                  "RETURNING id", (run_date.date(),)).fetchone()[0]
            _save_risk(conn, run_id, g.rename(columns={"p_model": "probability"}).to_dict("records"))


def live_weather(today, district_id=None):
    """Daily weather around a run date: enough observed days for the 8-week lag, plus the forecast."""
    return read_df("SELECT district_id, date, temp_mean, humidity_mean, precip FROM weather_daily "
                   "WHERE date BETWEEN %s AND %s AND (%s::int IS NULL OR district_id = %s)",
                   (today - pd.Timedelta(days=70), today + pd.Timedelta(days=16), district_id, district_id))


def score_weather(weather, today, horizons=HORIZONS):
    """Weather -> one scored row per district and horizon (probability, contribs) with the active engine."""
    districts = read_df("SELECT id AS district_id, name, history_of FROM districts")
    feats = add_season(weather_features(weather)).merge(districts, on="district_id")
    targets = {h: today + pd.Timedelta(days=h) for h in horizons}
    rows = pd.concat([feats[feats["date"] == t].assign(horizon=h) for h, t in targets.items()], ignore_index=True)
    rows["month"] = rows["date"].dt.month
    if RISK_ENGINE == "index":
        rows["probability"], rows["contribs"] = index.score(rows, index.load_climatology())
        return rows, index.VERSION
    return _model_scores(rows)


def score_live(today=None):
    """Score all 38 districts for 7 and 14 days ahead from the latest weather, store the run, raise alerts."""
    today = pd.Timestamp(today or dt.date.today())
    rows, version = score_weather(live_weather(today), today)
    missing = set(read_df("SELECT id FROM districts")["id"]) - set(rows["district_id"])
    if missing:
        raise RuntimeError(f"No weather features for district ids {sorted(missing)}; run fetch-live first")
    with connect() as conn:
        # One live run per day: a re-run (missed schedule catching up, manual run) replaces today's run,
        # otherwise two runs on one day would count as "two runs in a row" and alert after a single day.
        conn.execute("DELETE FROM runs WHERE kind = 'live' AND model_version = %s AND run_date = %s",
                     (version, today.date()))
        # Compare only with the same engine version: levels from a different engine are not comparable.
        # The last two earlier days: the previous one for the rule, the one before it to alert once per High streak.
        earlier = [rid for (rid,) in conn.execute(
            "SELECT id FROM runs WHERE kind = 'live' AND model_version = %s AND run_date < %s "
            "ORDER BY run_date DESC, id DESC LIMIT 2", (version, today.date()))]
        levels = [{(d, h): lvl for d, h, lvl in conn.execute(
            "SELECT district_id, horizon, level FROM risk WHERE run_id = %s", (rid,))} for rid in earlier]
        prev_levels, before_prev_levels = (levels + [{}, {}])[:2]
        run_id = conn.execute("INSERT INTO runs (run_date, kind, model_version) VALUES (%s, 'live', %s) RETURNING id",
                              (today.date(), version)).fetchone()[0]
        records = rows.to_dict("records")
        _save_risk(conn, run_id, records)
        alerts = 0
        for r in records:
            key = (r["district_id"], r["horizon"])
            reason = alert_reason(prev_levels.get(key), level_for(r["probability"], _levels()), before_prev_levels.get(key))
            if reason:
                alerts += 1
                conn.execute("INSERT INTO district_alerts (run_id, district_id, horizon, reason) VALUES (%s,%s,%s,%s)",
                             (run_id, int(r["district_id"]), int(r["horizon"]), reason))
        messages = staff.fan_out(conn, run_id)
    return {"run_id": run_id, "districts": rows["district_id"].nunique(), "alerts": alerts, "messages": messages,
            "engine": version}


def _model_scores(rows):
    model = _xgb()
    model.load_model(MODEL_FILE)
    version = json.loads(META_FILE.read_text())["version"]
    base = live_baseline(read_df("SELECT district, year, month, cases, outbreaks FROM dengue_monthly"))
    rows = rows.merge(base, left_on=["history_of", "month"], right_on=["district", "month"], how="left")
    state = base.groupby("month")["baseline"].median()
    rows["baseline"] = np.log1p(rows["baseline"].fillna(rows["month"].map(state)))  # no history: state median
    rows["probability"] = model.predict_proba(rows[FEATURES])[:, 1]
    rows["contribs"] = list(_contribs(model, rows))
    return rows, version


def what_if(district_id, run_date, horizon, rain_pct=0, humidity_pct=0):
    """E5-S1: re-score one district with forecast rainfall and humidity scaled by a percentage.

    Only forecast days (after the run date) change; observed weather is fact. Returns the unchanged
    and the scenario result side by side, both recomputed from the same weather so the difference is
    only the sliders.
    """
    today = pd.Timestamp(run_date)
    weather = live_weather(today, district_id)
    future = pd.to_datetime(weather["date"]) > today
    scenario = weather.copy()
    scenario.loc[future, "precip"] = scenario.loc[future, "precip"] * (1 + rain_pct / 100)
    scenario.loc[future, "humidity_mean"] = (scenario.loc[future, "humidity_mean"] * (1 + humidity_pct / 100)).clip(upper=100)

    def result(w):
        rows, _ = score_weather(w, today, (horizon,))
        if rows.empty:
            raise RuntimeError("No weather for this district around the latest run")
        r = rows.iloc[0]
        contribs = r["contribs"] if isinstance(r["contribs"], dict) else dict(zip(FEATURES, r["contribs"]))
        cards = [{k: v for k, v in c.items() if k != "contribution"} for c in to_cards(contribs)]
        return {"score": round(float(r["probability"]), 3), "level": level_for(r["probability"], _levels()), "drivers": cards}

    target = today + pd.Timedelta(days=horizon)
    changed = int((future & (pd.to_datetime(weather["date"]) <= target)).sum())
    return {"current": result(weather), "scenario": result(scenario), "forecast_days_changed": changed}
