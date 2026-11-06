import datetime as dt
import time

import requests

from .config import LIVE_PAST_DAYS
from .db import connect, read_df

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY = "temperature_2m_mean,relative_humidity_2m_mean,precipitation_sum"


def _get(url, params, tries=4):
    for i in range(tries):
        r = requests.get(url, params=params, timeout=120)
        if r.status_code == 429 and i < tries - 1:  # Open-Meteo rate limit: back off and retry
            time.sleep(30 * (i + 1))
            continue
        r.raise_for_status()
        return r.json()


def _rows(district_id, daily, today=None):
    for d, t, h, p in zip(daily["time"], daily["temperature_2m_mean"],
                          daily["relative_humidity_2m_mean"], daily["precipitation_sum"]):
        date = dt.date.fromisoformat(d)
        yield district_id, date, t, h, p, today is not None and date > today


def _upsert(rows):
    with connect() as conn, conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO weather_daily (district_id, date, temp_mean, humidity_mean, precip, is_forecast)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (district_id, date) DO UPDATE SET temp_mean = EXCLUDED.temp_mean,
                 humidity_mean = EXCLUDED.humidity_mean, precip = EXCLUDED.precip,
                 is_forecast = EXCLUDED.is_forecast, fetched_at = now()""",
            list(rows),
        )


def fetch_history(start, end):
    """Observed daily weather for every district between two dates (training data)."""
    districts = read_df("SELECT id, name, lat, lon FROM districts ORDER BY id")
    for d in districts.itertuples():
        data = _get(ARCHIVE_URL, {"latitude": d.lat, "longitude": d.lon, "start_date": start,
                                  "end_date": end, "daily": DAILY, "timezone": "Asia/Kolkata"})
        _upsert(_rows(d.id, data["daily"]))
        print(f"history: {d.name} {len(data['daily']['time'])} days")
        time.sleep(1)
    return len(districts)


def fetch_live(today=None):
    """Last LIVE_PAST_DAYS observed days plus the 16-day forecast, all districts in one call."""
    today = today or dt.date.today()
    districts = read_df("SELECT id, lat, lon FROM districts ORDER BY id")
    data = _get(FORECAST_URL, {
        "latitude": ",".join(f"{x:.4f}" for x in districts.lat),
        "longitude": ",".join(f"{x:.4f}" for x in districts.lon),
        "daily": DAILY, "past_days": LIVE_PAST_DAYS, "forecast_days": 16, "timezone": "Asia/Kolkata",
    })
    data = data if isinstance(data, list) else [data]
    for district_id, loc in zip(districts.id, data):
        _upsert(_rows(int(district_id), loc["daily"], today))
    return len(data)
