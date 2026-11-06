import numpy as np
import pandas as pd

from .config import AEDES_BAND

WEATHER_FEATURES = ["rain_w1_2", "rain_w3_4", "rain_w5_8", "rainy_days", "temp_mean", "aedes_days", "humidity_mean"]
FEATURES = WEATHER_FEATURES + ["month_sin", "month_cos", "baseline"]

RAINY_DAY_MM = 2.5  # IMD definition of a rainy day


def weather_features(weather):
    """Daily weather (district_id, date, temp_mean, humidity_mean, precip) -> one feature row per
    district per date. Each row describes the weeks leading up to that date (the target date)."""
    out = []
    for district_id, w in weather.groupby("district_id"):
        w = w.set_index(pd.to_datetime(w["date"])).sort_index()
        w = w.reindex(pd.date_range(w.index.min(), w.index.max(), freq="D"))  # gaps become NaN, not shifted windows
        rain, temp = w["precip"], w["temp_mean"]
        rain14 = rain.rolling(14).sum()
        f = pd.DataFrame({
            "rain_w1_2": rain14,
            "rain_w3_4": rain14.shift(14),
            "rain_w5_8": rain.rolling(28).sum().shift(28),
            "rainy_days": (rain >= RAINY_DAY_MM).astype(float).where(rain.notna()).rolling(28).sum(),
            "temp_mean": temp.rolling(28).mean(),
            "aedes_days": temp.between(*AEDES_BAND).astype(float).where(temp.notna()).rolling(28).sum(),
            "humidity_mean": w["humidity_mean"].rolling(28).mean(),
        })
        f["district_id"] = district_id
        out.append(f.dropna().rename_axis("date").reset_index())
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["district_id", "date", *WEATHER_FEATURES])


def add_season(df, date_col="date"):
    month = pd.to_datetime(df[date_col]).dt.month
    df["month_sin"] = np.sin(2 * np.pi * month / 12)
    df["month_cos"] = np.cos(2 * np.pi * month / 12)
    return df
