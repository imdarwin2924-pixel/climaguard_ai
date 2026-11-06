from pathlib import Path

import pandas as pd
import psycopg

from .config import DATABASE_URL


def connect():
    return psycopg.connect(DATABASE_URL)


def init_schema():
    sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf8")
    with connect() as conn:
        conn.execute(sql)


def read_df(sql, params=None):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)
