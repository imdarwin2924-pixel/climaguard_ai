import numpy as np
import pandas as pd

from climaguard.cases import canonical_name, label_months
from climaguard.model import backtest_metrics, season_of


def test_above_normal_uses_other_years_and_min_cases():
    cases = pd.DataFrame({"district": ["A"] * 4 + ["B"] * 4, "year": [2017, 2018, 2019, 2020] * 2,
                          "month": [10] * 8, "cases": [10, 11, 9, 60, 0, 1, 0, 4]})
    lab = label_months(cases).set_index(["district", "year"])
    assert lab.loc[("A", 2020), "above_normal"] == 1.0          # far above 10, 11, 9
    assert lab.loc[("A", 2017), "above_normal"] == 0.0
    assert lab.loc[("B", 2020), "above_normal"] == 0.0          # above normal but under MIN_CASES
    assert lab.loc[("A", 2020), "baseline"] == 10.0             # mean of the other years only


def test_single_other_year_gives_no_label():
    lab = label_months(pd.DataFrame({"district": ["A", "A"], "year": [2019, 2020], "month": [1, 1], "cases": [3, 9]}))
    assert lab["above_normal"].isna().all()


def test_season_is_april_to_march():
    assert list(season_of(np.array([2020, 2021, 2021]), np.array([4, 3, 4]))) == [2020, 2020, 2021]


def test_canonical_names():
    known = {"Kanchipuram", "Tuticorin", "Chennai"}
    assert canonical_name("Kancheepuram ", known) == "Kanchipuram"
    assert canonical_name("THOOTHUKUDI", known) == "Tuticorin"
    assert canonical_name("chennai", known) == "Chennai"
    assert canonical_name("Atlantis", known) is None
    known |= {"Ramanathapuram", "Virudhunagar", "Ariyalur"}
    assert canonical_name("Ramanathapur am-Paramakudi", known) == "Ramanathapuram"
    assert canonical_name("Virudhunagar - Sivakasi", known) == "Virudhunagar"
    assert canonical_name("Ariyallur", known) == "Ariyalur"


def test_detection_and_lead_time():
    labels = pd.DataFrame({"district": ["A", "A"], "year": [2020, 2020], "month": [11, 12], "above_normal": [1.0, 0.0]})
    run = pd.to_datetime(["2020-10-19", "2020-10-26", "2020-11-23"])
    test = pd.DataFrame({"district": "A", "year": 2020, "month": [11, 11, 12], "run_date": run,
                         "above_normal": [1.0, 1.0, 0.0], "p_model": [0.6, 0.8, 0.7],
                         "p_logit": [0.4, 0.5, 0.2], "p_last_year": [0.0, 0.0, 0.0]})
    m = backtest_metrics(test, labels)
    assert m["detection_rate_model"] == 1.0
    assert m["detection_rate_last_year"] == 0.0
    assert m["lead_time_weeks_median"] == (pd.Timestamp("2020-11-01") - run[0]).days / 7
    assert m["false_alarm_rate"] == round(1 / 3, 3)


def test_outbreak_label_and_leave_one_out_share():
    from climaguard.cases import label_outbreaks
    cases = pd.DataFrame({"district": "A", "year": [2017, 2018, 2019, 2020], "month": 10,
                          "cases": [0, 30, 12, 0], "outbreaks": [0, 2, 1, 0]})
    lab = label_outbreaks(cases).set_index("year")
    assert list(lab["above_normal"]) == [0.0, 1.0, 1.0, 0.0]
    assert lab.loc[2017, "baseline"] == 2 / 3      # other years: 2018, 2019 had outbreaks, 2020 did not
    assert lab.loc[2018, "baseline"] == 1 / 3


def test_idsp_dates_survive_line_breaks():
    from climaguard.idsp import _date
    assert str(_date("12-07- 2026")) == "2026-07-12"
    assert str(_date("30-09-19")) == "2019-09-30"
    assert _date("31-02-2020") is None
