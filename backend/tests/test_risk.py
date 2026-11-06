import pytest

from climaguard.drivers import LOOKUP, to_cards
from climaguard.features import FEATURES
from climaguard.risk import alert_reason, level_for


@pytest.mark.parametrize("p,level", [(0.0, "Low"), (0.249, "Low"), (0.25, "Moderate"), (0.5, "High"),
                                     (0.749, "High"), (0.75, "Very high"), (1.0, "Very high")])
def test_levels_follow_prd_thresholds(p, level):
    assert level_for(p) == level


def test_alert_two_high_runs_fires():
    assert alert_reason("High", "High")
    assert alert_reason("High", "Very high")


def test_alert_fires_once_per_high_streak():
    assert alert_reason("High", "High", before_previous="Moderate")      # streak reaches two: alert
    assert alert_reason("High", "Very high", before_previous="High") is None  # third run of the streak: quiet
    assert alert_reason("Very high", "High", before_previous="Very high") is None
    assert alert_reason("High", "High", before_previous=None)            # no older run yet: streak starts here


def test_alert_fires_again_after_a_break():
    # High, Moderate, High, High: the second streak alerts again
    assert alert_reason("High", "High", before_previous="Moderate")


def test_two_level_jump_still_alerts_mid_streak_rules():
    assert alert_reason("Low", "High", before_previous="High")           # dropped then jumped: alert


def test_alert_single_high_run_does_not_fire():
    assert alert_reason("Moderate", "High") is None
    assert alert_reason(None, "Very high") is None


def test_alert_two_level_jump_fires():
    assert alert_reason("Low", "High")
    assert alert_reason("Moderate", "Very high")


def test_no_alert_below_high_without_jump():
    assert alert_reason("Low", "Moderate") is None
    assert alert_reason("High", "Moderate") is None


def test_every_feature_has_a_sentence():
    assert set(FEATURES) <= set(LOOKUP)


def test_cards_are_three_plain_ordered_and_distinct():
    contrib = {f: 0.0 for f in FEATURES} | {"rain_w3_4": 0.9, "humidity_mean": 0.4,
                                            "month_sin": -0.3, "month_cos": -0.2, "temp_mean": 0.1}
    cards = to_cards(contrib)
    assert len(cards) == 3
    assert [c["factor"] for c in cards] == ["Rainfall", "Season", "Humidity"]
    assert cards[1]["direction"] == "lowers"
    for c in cards:
        assert not any(f in c["text"] for f in FEATURES)  # no raw feature names
