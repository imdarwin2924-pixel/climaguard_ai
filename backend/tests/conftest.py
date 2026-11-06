"""Shared fixtures: a throwaway Postgres database (never the real one) and test users."""
import psycopg
import pytest

from climaguard import auth, cases, db, model
from climaguard.config import DATABASE_URL

TEST_DB = "climaguard_test"
TEST_URL = DATABASE_URL.rsplit("/", 1)[0] + "/" + TEST_DB


@pytest.fixture
def test_db(monkeypatch, tmp_path):
    admin = DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    try:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
            conn.execute(f"CREATE DATABASE {TEST_DB}")
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable")
    monkeypatch.setattr(db, "DATABASE_URL", TEST_URL)
    monkeypatch.setattr(model, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(model, "MODEL_FILE", tmp_path / "m.json")
    monkeypatch.setattr(model, "META_FILE", tmp_path / "meta.json")
    monkeypatch.setattr(cases, "LABEL", "counts")  # generated data is monthly counts
    monkeypatch.setattr(model, "RISK_ENGINE", "model")
    db.init_schema()
    yield
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")


@pytest.fixture
def make_user(test_db):
    """make_user(role, login, password, district_id=None, must_change=False) -> staff id."""
    def make(role, login, password, district_id=None, must_change=False):
        email, mobile = (login, None) if "@" in login else (None, login)
        with db.connect() as conn:
            return conn.execute(
                "INSERT INTO staff (name, email, mobile, role, district_id, password_hash, must_change_password) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (f"Test {role}", email, mobile, role, district_id, auth.hash_password(password), must_change)).fetchone()[0]
    return make
