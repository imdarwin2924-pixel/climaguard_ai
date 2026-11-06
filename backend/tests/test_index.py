import numpy as np
import pandas as pd
import pytest

from climaguard import index
from climaguard.config import INDEX_LEVELS
from climaguard.drivers import LOOKUP, to_cards
from climaguard.risk import level_for

OCT = pd.Timestamp("2025-10-10")


def feats(**kw):
    base = dict(district_id=1, date=OCT, temp_mean=28.0, rain_w3_4=50.0, rain_w5_8=50.0, rainy_days=6.0,
                humidity_mean=75.0)
    return pd.DataFrame([base | kw])


def climatology():
    """One district, October: 100 past days from dry to wet, everything else as usual."""
    rain = np.linspace(0, 150, 100)
    f = pd.DataFrame({"district_id": 1, "date": pd.Timestamp("2020-10-01"), "temp_mean": 28.0,
                      "rain_w3_4": rain, "rain_w5_8": rain, "rainy_days": rain / 12, "humidity_mean": 75.0})
    return index.calibrate(f)


@pytest.mark.parametrize("t,s", [(10, 0), (18, 0), (22, 0.5), (26, 1), (28, 1), (30, 1), (32, 0.5), (34, 0), (38, 0)])
def test_temperature_curve(t, s):
    assert index.temperature_suitability([t])[0] == pytest.approx(s)


def test_weights_sum_to_one_and_have_sentences():
    assert sum(index.WEIGHTS.values()) == pytest.approx(1)
    assert set(index.WEIGHTS) <= set(LOOKUP)


def test_score_is_percentile_within_district_month():
    clim = climatology()
    (wettest,), _ = index.score(feats(rain_w3_4=150, rain_w5_8=150, rainy_days=12.5), clim)
    (driest,), _ = index.score(feats(rain_w3_4=0, rain_w5_8=0, rainy_days=0), clim)
    (middle,), _ = index.score(feats(rain_w3_4=75, rain_w5_8=75, rainy_days=6.25), clim)
    assert wettest == pytest.approx(1.0) and driest == pytest.approx(0.0)
    assert 0.4 < middle < 0.6
    assert level_for(wettest, INDEX_LEVELS) == "Very high" and level_for(middle, INDEX_LEVELS) in ("Low", "Moderate")


def test_cards_compare_with_the_usual_for_the_month():
    _, (c,) = index.score(feats(rain_w3_4=150, rain_w5_8=150, rainy_days=12), climatology())
    top = to_cards(c)[0]
    assert top["factor"] == "Rainfall" and top["direction"] == "raises" and "More rain than usual" in top["text"]
    assert c["temp_suit"] == pytest.approx(0, abs=1e-4) and c["hum_suit"] == pytest.approx(0, abs=1e-4)  # as usual

    _, (c,) = index.score(feats(humidity_mean=55), climatology())
    hum = {k["factor"]: k for k in to_cards(c, n=4)}["Humidity"]
    assert hum["direction"] == "lowers" and hum["text"].startswith("Less humid than usual")


def test_feedback_flags_lead_time_and_shared_records(monkeypatch):
    """Two districts, October 2025 outbreak in A; A's runs say Very high from mid-September on.
    B is a newer district sharing A's record: shown, but counted once."""
    days = pd.date_range("2025-04-01", "2026-03-31", freq="D")
    f = pd.concat([pd.DataFrame({"district_id": d, "name": n, "history_of": "A", "date": days,
                                 "temp_mean": 28.0, "rain_w3_4": 50.0, "rain_w5_8": 50.0, "rainy_days": 6.0,
                                 "humidity_mean": 75.0}) for d, n in [(1, "A"), (2, "B")]], ignore_index=True)
    wet = (f["date"] >= "2025-09-28") & (f["date"] <= "2025-10-31")
    f.loc[wet, ["rain_w3_4", "rain_w5_8", "rainy_days"]] = [150.0, 150.0, 12.5]
    clim = index.calibrate(pd.concat([f.assign(rain_w3_4=r, rain_w5_8=r, rainy_days=r / 12) for r in (0.0, 40, 80, 120, 150)]))
    monkeypatch.setattr(index, "load_climatology", lambda: clim)
    labels = pd.DataFrame({"district": "A", "year": [2025, 2024], "month": [10, 10], "above_normal": [1.0, 0.0]})

    fb = index.feedback(f, labels, 2025, INDEX_LEVELS)
    oct_a = next(m for m in fb["districts"]["1"]["months"] if m["month"] == "2025-10")
    assert oct_a["outbreak"] and oct_a["flagged_in_advance"] and oct_a["peak_level"] == "Very high"
    assert 0 < oct_a["lead_weeks"] <= 2                          # a run before 1 October already said Very high
    assert fb["districts"]["2"]["shares_record_of"] == "A"
    assert fb["state"]["outbreak_months"] == 1 and fb["state"]["detected"] == 1   # B not double-counted
    assert fb["state"]["detection_rate_last_year"] == 0.0 and fb["season"] == "2025-26"
