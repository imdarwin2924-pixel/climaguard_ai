from .config import LEVELS

ORDER = [name for _, name in LEVELS]


def level_for(probability, levels=LEVELS):
    """PRD §4 for model probabilities: Low <25%, Moderate 25-50%, High 50-75%, Very high >75%."""
    for upper, name in levels:
        if probability < upper:
            return name
    return levels[-1][1]


def alert_reason(previous_level, current_level, before_previous=None):
    """E4-S2: alert on High+ two runs in a row, or a jump of two levels at once. None = no alert.

    Fires once per High streak: a district that stays High is not re-alerted every run (alert fatigue).
    """
    cur = ORDER.index(current_level)
    if previous_level is None:
        return None
    prev = ORDER.index(previous_level)
    high = ORDER.index("High")
    already_alerted = before_previous is not None and ORDER.index(before_previous) >= high
    if prev >= high and cur >= high and not already_alerted:
        return f"{current_level} on two runs in a row"
    if cur - prev >= 2:
        return f"Jumped from {previous_level} to {current_level}"
    return None
