import os

import psycopg
from dotenv import load_dotenv

load_dotenv()


def connect():
    url = os.environ["DATABASE_URL"]
    return psycopg.connect(url, row_factory=psycopg.rows.dict_row)


def apply_schema(conn):
    with open(os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")) as f:
        conn.execute(f.read())
    conn.commit()
