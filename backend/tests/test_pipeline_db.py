"""End-to-end pipeline on a throwaway database with generated data. Generated data never enters the real DB."""
import numpy as np
import pandas as pd

from climaguard import cases, db, model


def seed(rng):
    names = ["Chennai", "Madurai", "Salem", "Erode", "Ranipet"]
    dates = pd.date_range("2016-11-01", "2021-03-31", freq="D")
    with db.connect() as conn, conn.cursor() as cur:
        for i, n in enumerate(names):
            cur.execute("INSERT INTO districts (name, history_of, lat, lon) VALUES (%s, %s, 0, 0)",
                        (n, "Vellore" if n == "Ranipet" else n))
        weather = []
        for d_id in range(1, len(names) + 1):
            rain = rng.gamma(0.6, 8, len(dates))
            temp = 27 + 3 * np.sin(2 * np.pi * dates.dayofyear / 365) + rng.normal(0, 1, len(dates))
            weather += [(d_id, d.date(), float(t), 75.0, float(r)) for d, t, r in zip(dates, temp, rain)]
        cur.executemany("INSERT INTO weather_daily (district_id, date, temp_mean, humidity_mean, precip) "
                        "VALUES (%s,%s,%s,%s,%s)", weather)
    w = db.read_df("SELECT district_id, date, precip FROM weather_daily")
    w["date"] = pd.to_datetime(w["date"])
    # Cases driven by rain 3-6 weeks earlier, so the model has a real signal to find.
    w["lagged"] = w.groupby("district_id")["precip"].transform(lambda s: s.shift(21).rolling(21).sum())
    monthly = w.dropna().groupby(["district_id", w["date"].dt.year.rename("year"), w["date"].dt.month.rename("month")])["lagged"].mean()
    monthly = monthly.reset_index()
    monthly["district"] = monthly["district_id"].map(dict(enumerate(names[:4], 1)))
    monthly = monthly.dropna(subset=["district"])
    monthly = monthly[(monthly["year"] * 100 + monthly["month"]) >= 201704]
    monthly["cases"] = rng.poisson(np.exp(monthly["lagged"] / 40)).astype(int) * 3
    return monthly[["district", "year", "month", "cases"]]


def test_train_backtest_live_and_alerts(test_db, make_user):
    rng = np.random.default_rng(0)
    assert cases.import_cases(seed(rng), "generated test data") > 0

    m = model.train_and_backtest()
    assert m["holdout_season"] == "2020-21"
    for key in ["detection_rate_model", "detection_rate_last_year", "brier_model", "brier_last_year", "lead_time_weeks_median"]:
        assert key in m
    assert db.read_df("SELECT count(*) n FROM runs WHERE kind = 'backtest'")["n"][0] > 0

    first = model.score_live("2021-03-01")
    assert first["districts"] == 5 and first["alerts"] == 0   # no previous run, no alert
    risk = db.read_df("SELECT level, drivers FROM risk WHERE run_id = %s", (first["run_id"],))
    assert len(risk) == 10                                    # 5 districts x 2 horizons
    assert all(len(d) == 3 for d in risk["drivers"])          # three driver cards each

    # Two nurses on blocks in Chennai, one in Madurai; blocks are needed for the outbox fan-out.
    with db.connect() as conn:
        for d_id, name in [(1, "North"), (1, "South"), (2, "Central")]:
            conn.execute("INSERT INTO blocks (sdt_code, name, district_id, population, density, child_share, "
                         "past_outbreaks, vulnerability, factor_pct, actions) VALUES (%s,%s,%s,1000,100,0.1,0,0.5,'{}',%s)",
                         (hash(name) % 10**6, name, d_id, '["Check stored water in every house"]'))
        blocks = dict(conn.execute("SELECT name, id FROM blocks").fetchall())
        for nurse, mobile, block in [("A", "9000000001", "North"), ("B", "9000000002", "South"), ("C", "9000000003", "Central")]:
            sid = conn.execute("INSERT INTO staff (name, mobile, district_id) VALUES (%s, %s, 1) RETURNING id",
                               (nurse, mobile)).fetchone()[0]
            conn.execute("INSERT INTO staff_blocks VALUES (%s, %s)", (sid, blocks[block]))

    second = model.score_live("2021-03-08")
    expected = db.read_df(
        "SELECT count(*) n FROM risk a JOIN risk b USING (district_id, horizon) WHERE a.run_id = %s AND b.run_id = %s "
        "AND ((a.level IN ('High','Very high') AND b.level IN ('High','Very high')) OR "
        "(array_position(ARRAY['Low','Moderate','High','Very high'], b.level) - "
        " array_position(ARRAY['Low','Moderate','High','Very high'], a.level) >= 2))",
        (first["run_id"], second["run_id"]))["n"][0]
    assert second["alerts"] == expected
    alerted = set(db.read_df("SELECT district_id FROM district_alerts WHERE run_id = %s", (second["run_id"],))["district_id"])
    assert second["messages"] == 2 * (1 in alerted) + (2 in alerted)   # one message per nurse in an alerted district
    sent = db.read_df("SELECT message FROM outbox")["message"]
    assert all(len(m) <= 160 and "Start at" in m and "9000" not in m for m in sent)

    # Deterministic: Chennai alerts on both horizons -> exactly one message per Chennai nurse, 7-day wording.
    from climaguard import staff
    with db.connect() as conn:
        conn.execute("DELETE FROM outbox; DELETE FROM district_alerts")
        conn.execute("INSERT INTO district_alerts (run_id, district_id, horizon, reason) VALUES (%s,1,7,'t'), (%s,1,14,'t')",
                     (second["run_id"], second["run_id"]))
        assert staff.fan_out(conn, second["run_id"]) == 2
        msgs = [m for (m,) in conn.execute("SELECT message FROM outbox")]
    assert len(msgs) == 2 and all("next 7 days" in m and "Chennai" in m for m in msgs)

    # A third run: districts High+ in runs 1 and 2 must not get another "two runs in a row" alert.
    third = model.score_live("2021-03-15")
    repeats = db.read_df(
        "SELECT count(*) n FROM district_alerts a "
        "JOIN risk r1 ON r1.district_id = a.district_id AND r1.horizon = a.horizon AND r1.run_id = %s "
        "JOIN risk r2 ON r2.district_id = a.district_id AND r2.horizon = a.horizon AND r2.run_id = %s "
        "WHERE a.run_id = %s AND a.reason LIKE '%%two runs in a row' "
        "AND r1.level IN ('High','Very high') AND r2.level IN ('High','Very high')",
        (first["run_id"], second["run_id"], third["run_id"]))["n"][0]
    assert repeats == 0

    # Re-running the same day replaces that day's run: no duplicate run, no same-day "two in a row" alert.
    again = model.score_live("2021-03-15")
    runs = db.read_df("SELECT id FROM runs WHERE kind = 'live' AND run_date = '2021-03-15'")["id"].tolist()
    assert runs == [again["run_id"]] and again["alerts"] == third["alerts"]

    from fastapi.testclient import TestClient
    import api.main as api_main
    api_main.META_FILE = model.META_FILE
    api_main.RISK_ENGINE = "model"
    client = TestClient(api_main.app)
    make_user("officer", "officer@test.in", "officer-pass-1", district_id=1)
    assert client.post("/api/auth/login", json={"login": "officer@test.in", "password": "officer-pass-1"}).status_code == 200
    r = client.get("/api/risk", params={"horizon": 14}).json()
    assert len(r["districts"]) == 5 and r["disclaimer"] and "14 days" in r["title"]
    probs = [d["score"] for d in r["needs_attention"]]
    assert probs == sorted(probs, reverse=True)
    assert all(d["level"] in ("High", "Very high") for d in r["needs_attention"])
    d = client.get(f"/api/districts/{r['districts'][0]['id']}").json()
    assert len(d["drivers"]) == 3 and all("contribution" not in c for c in d["drivers"])
    assert client.get("/api/districts/999").status_code == 404
    assert client.get("/api/risk", params={"horizon": 10}).status_code == 422
    assert "detection_rate_model" in client.get("/api/backtest").json()
    assert "alerts" in client.get("/api/alerts").json()

    # E5-S1 what-if: zero change reproduces the forecast; limits enforced; only forecast days change.
    r = client.get("/api/districts/1/whatif", params={"horizon": 7}).json()
    assert r["current"] == r["scenario"] and r["label"] == "Forecast"
    r = client.get("/api/districts/1/whatif", params={"horizon": 14, "rain": 50, "humidity": -30}).json()
    assert r["label"] == "Scenario, not forecast" and r["forecast_days_changed"] == 14
    assert r["scenario"]["level"] in ("Low", "Moderate", "High", "Very high") and len(r["scenario"]["drivers"]) == 3
    assert client.get("/api/districts/1/whatif", params={"rain": 60}).status_code == 422
