"""E3-S2: every model feature has a plain-language sentence; raw feature names never reach the UI."""

# feature -> (factor shown on the card, lag text, sentence if it raises risk, sentence if it lowers risk)
LOOKUP = {
    "rain_w1_2": ("Rainfall", "last 2 weeks", "Recent heavy rain → water collecting in containers",
                  "Little rain in the last 2 weeks → fewer new breeding sites"),
    "rain_w3_4": ("Rainfall", "3–4 weeks ago", "Heavy rain 3–4 weeks ago → more breeding sites now",
                  "Dry spell 3–4 weeks ago → fewer breeding sites now"),
    "rain_w5_8": ("Rainfall", "5–8 weeks ago", "Wet weather 5–8 weeks ago → mosquito numbers built up",
                  "Dry weather 5–8 weeks ago → mosquito numbers stayed low"),
    "rainy_days": ("Rainy days", "last 4 weeks", "Many rainy days in a row → standing water stays",
                   "Few rainy days → standing water dries out"),
    "temp_mean": ("Temperature", "last 4 weeks", "Warm temperatures → mosquitoes develop faster",
                  "Cooler temperatures → mosquitoes develop slower"),
    "aedes_days": ("Temperature", "last 4 weeks", "Many days in the 26–30°C transmission band → virus spreads faster",
                   "Few days in the 26–30°C transmission band → virus spreads slower"),
    "humidity_mean": ("Humidity", "last 4 weeks", "High humidity → mosquitoes live longer",
                      "Low humidity → mosquitoes live shorter"),
    "month_sin": ("Season", "this time of year", "This time of year usually brings more dengue",
                  "This time of year usually brings less dengue"),
    "month_cos": ("Season", "this time of year", "This time of year usually brings more dengue",
                  "This time of year usually brings less dengue"),
    # Weather suitability index components (index.py), compared with this district's usual for the month.
    "temp_suit": ("Temperature", "last 4 weeks", "Closer to the 26–30°C transmission band than usual → virus spreads faster",
                  "Further from the 26–30°C transmission band than usual → virus spreads slower"),
    "rain_suit": ("Rainfall", "3–8 weeks ago", "More rain than usual 3–8 weeks ago → more breeding sites now",
                  "Less rain than usual 3–8 weeks ago → fewer breeding sites now"),
    "rainy_suit": ("Rainy days", "last 4 weeks", "More rainy days than usual → standing water stays",
                   "Fewer rainy days than usual → standing water dries out"),
    "hum_suit": ("Humidity", "last 4 weeks", "More humid than usual → mosquitoes live longer",
                 "Less humid than usual → mosquitoes live shorter"),
    "baseline": ("Past years", "same month, earlier years", "Past years often had dengue here this month",
                 "Past years rarely had dengue here this month"),
}


def to_cards(contributions, n=3):
    """Top n features by absolute SHAP contribution -> plain-language cards, largest first.

    Season terms are merged so the same card never appears twice.
    """
    merged = {}
    for feature, value in contributions.items():
        key = "month_sin" if feature == "month_cos" else feature
        merged[key] = merged.get(key, 0.0) + value
    top = sorted(merged.items(), key=lambda kv: abs(kv[1]), reverse=True)[:n]
    cards = []
    for feature, value in top:
        factor, lag, up, down = LOOKUP[feature]
        cards.append({"factor": factor, "lag": lag, "direction": "raises" if value > 0 else "lowers",
                      "text": up if value > 0 else down, "contribution": round(float(value), 4)})
    return cards
