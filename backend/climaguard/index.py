"""Climate suitability index for dengue transmission: weather only, no case data.

Each component is a 0-1 suitability from known Aedes biology and the raw index is their weighted
sum. Tamil Nadu is suitable most of the year, so the published score is relative, matching the
PRD's "above normal for this district and month": the percentile of today's raw index among the
same district and calendar month in past years. Cards explain the gap to that month's normal:
weight * (component - normal component).
"""
import json

import numpy as np
import pandas as pd

from .config import MODEL_DIR

VERSION = "weather-index-v2"
CLIMATOLOGY_FILE = MODEL_DIR / "index_climatology.json"
VALIDATION_FILE = MODEL_DIR / "index_validation.json"

# Weights sum to 1. Temperature and lagged rain drive transmission; rainy days and humidity modulate it.
WEIGHTS = {"temp_suit": 0.35, "rain_suit": 0.35, "rainy_suit": 0.15, "hum_suit": 0.15}


def temperature_suitability(t):
    """28-day mean °C -> 0-1. Aedes dengue transmission is negligible below ~18°C, best at 26-30°C,
    and falls off towards ~34°C (Mordecai et al. 2017, PLoS NTD)."""
    t = np.asarray(t, dtype=float)
    rise = np.clip((t - 18) / (26 - 18), 0, 1)
    fall = np.clip((34 - t) / (34 - 30), 0, 1)
    return np.minimum(rise, fall)


def components(f):
    """Weather features (features.weather_features) -> suitability components."""
    return pd.DataFrame({
        "temp_suit": temperature_suitability(f["temp_mean"]),
        # Rain 3-8 weeks back fills containers that are breeding sites now; saturates by ~200 mm.
        "rain_suit": 1 - np.exp(-(f["rain_w3_4"] + f["rain_w5_8"]) / 100),
        # Repeated rainy days keep water standing; 12+ of the last 28 days counts as fully wet.
        "rainy_suit": np.clip(f["rainy_days"] / 12, 0, 1),
        # Adult mosquito survival improves from ~50% to ~80% relative humidity.
        "hum_suit": np.clip((f["humidity_mean"] - 50) / 30, 0, 1),
    }, index=f.index)


def raw(f):
    c = components(f)
    return sum(w * c[k] for k, w in WEIGHTS.items()), c


def calibrate(feats):
    """Per district and calendar month: 101 quantiles of the raw index and each component's mean."""
    s, c = raw(feats)
    df = c.assign(raw=s, district_id=feats["district_id"].to_numpy(), month=feats["date"].dt.month.to_numpy())
    clim = {}
    for (d, m), g in df.groupby(["district_id", "month"]):
        clim.setdefault(str(d), {})[str(m)] = {"q": np.quantile(g["raw"], np.linspace(0, 1, 101)).round(5).tolist(),
                                               "normal": {k: round(float(g[k].mean()), 5) for k in WEIGHTS}}
    return clim


def load_climatology():
    if not CLIMATOLOGY_FILE.exists():
        raise RuntimeError("Index not calibrated: run `python -m climaguard.cli calibrate-index` first")
    return json.loads(CLIMATOLOGY_FILE.read_text())


def score(f, clim):
    """-> (percentile 0-1 vs this district-month's past, per-row {component: contribution to the gap})."""
    s, c = raw(f)
    scores, contribs = [], []
    for i, (d, m) in enumerate(zip(f["district_id"], f["date"].dt.month)):
        ref = clim[str(int(d))][str(int(m))]
        scores.append(float(np.interp(s.iloc[i], ref["q"], np.linspace(0, 1, 101))))
        contribs.append({k: w * (c[k].iloc[i] - ref["normal"][k]) for k, w in WEIGHTS.items()})
    return np.array(scores), contribs


def validate(feats, labels):
    """Check the index against reported outbreaks (it is never fitted to them).

    feats: weather features with district name/year/month; labels: district, year, month, above_normal.
    """
    from sklearn.metrics import roc_auc_score

    from .config import INDEX_LEVELS
    from .risk import level_for

    weekly = feats[feats["date"].dt.weekday == 0]
    ex = weekly.merge(labels, left_on=["name", "year", "month"], right_on=["district", "year", "month"])
    ex = ex.assign(score=score(ex, load_climatology())[0])
    ex["level"] = [level_for(s, INDEX_LEVELS) for s in ex["score"]]
    by_level = ex.groupby("level")["above_normal"].agg(["mean", "size"])
    seasons = np.where(ex["month"] >= 4, ex["year"], ex["year"] - 1)
    per_season = {int(y): round(roc_auc_score(g["above_normal"], g["score"]), 3)
                  for y, g in ex.groupby(seasons) if g["above_normal"].nunique() == 2}
    return {
        "engine": VERSION,
        "against": "IDSP weekly dengue outbreak reports, Tamil Nadu",
        "examples": len(ex), "outbreak_examples": int(ex["above_normal"].sum()),
        "auc_all": round(roc_auc_score(ex["above_normal"], ex["score"]), 3),
        "auc_by_season": per_season,
        "level_share": {k: round(int(v["size"]) / len(ex), 3) for k, v in by_level.iterrows()},
        "outbreak_rate_by_level": {k: {"rate": round(v["mean"], 4), "n": int(v["size"])} for k, v in by_level.iterrows()},
    }


FEEDBACK_FILE = MODEL_DIR / "index_feedback.json"


def _lead_rows(scored, horizons=(7, 14)):
    """Scored rows at target dates -> one row per (district, run date, horizon) with the month it targets."""
    out = []
    for h in horizons:
        r = scored.assign(horizon=h, run_date=scored["date"] - pd.Timedelta(days=h))
        out.append(r[r["run_date"].dt.weekday == 0])  # the daily run is weekly here: Mondays, as in validation
    return pd.concat(out, ignore_index=True)


def feedback(feats, labels, season, levels):
    """E5-S2: replay the index over one season and compare with reported outbreaks, per district and month.

    A month counts as flagged in advance when a run before the month started already said High or above
    for a target date inside it; lead time is how many weeks before the month that first happened.
    """
    from .risk import level_for

    start, end = pd.Timestamp(season, 4, 1), pd.Timestamp(season + 1, 3, 31)
    f = feats[(feats["date"] >= start) & (feats["date"] <= end)].copy()
    f["score"] = score(f, load_climatology())[0]
    runs = _lead_rows(f)
    runs["month_start"] = runs["date"].dt.to_period("M").dt.start_time
    runs["high"] = [level_for(s, levels) in ("High", "Very high") for s in runs["score"]]
    runs["ahead"] = runs["high"] & (runs["run_date"] < runs["month_start"])

    lab = labels.set_index(["district", "year", "month"])["above_normal"]
    districts, state = {}, {"outbreak_months": 0, "detected": 0, "leads": [], "flagged_months": 0, "false_alarm_months": 0,
                            "detected_last_year": 0}
    for (did, name, hist), g in runs.groupby(["district_id", "name", "history_of"]):
        months = []
        for ms, m in g.groupby("month_start"):
            outbreak = bool(lab.get((hist, ms.year, ms.month), 0) == 1)
            ahead = m[m["ahead"]]
            lead = round((ms - ahead["run_date"].min()).days / 7, 1) if len(ahead) else None
            peak = float(m["score"].max())
            months.append({"month": ms.strftime("%Y-%m"), "peak_score": round(peak, 3), "peak_level": level_for(peak, levels),
                           "flagged_in_advance": lead is not None, "lead_weeks": lead, "outbreak": outbreak})
            if name == hist:  # new districts share their parent's outbreak record: count it once, for the parent
                state["outbreak_months"] += outbreak
                state["detected_last_year"] += bool(outbreak and lab.get((hist, ms.year - 1, ms.month), 0) == 1)  # PRD baseline
                state["detected"] += outbreak and lead is not None
                state["flagged_months"] += lead is not None
                state["false_alarm_months"] += lead is not None and not outbreak
                if outbreak and lead is not None:
                    state["leads"].append(lead)
        districts[str(int(did))] = {"name": name, "shares_record_of": None if name == hist else hist, "months": months,
                                    "outbreak_months": sum(m["outbreak"] for m in months),
                                    "detected": sum(m["outbreak"] and m["flagged_in_advance"] for m in months)}
    leads = state.pop("leads")
    n = state["outbreak_months"]
    state.update({"detection_rate": round(state["detected"] / n, 3) if n else None,
                  "detection_rate_last_year": round(state["detected_last_year"] / n, 3) if n else None,
                  "median_lead_weeks": float(np.median(leads)) if leads else None,
                  "false_alarm_share": round(state["false_alarm_months"] / state["flagged_months"], 3) if state["flagged_months"] else None})
    return {"engine": VERSION, "season": f"{season}-{str(season + 1)[-2:]}", "against": "IDSP weekly dengue outbreak reports",
            "state": state, "districts": districts}
