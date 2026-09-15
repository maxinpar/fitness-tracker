"""Database helpers. One connection per request is enough for a single user."""
import json
from pathlib import Path
import psycopg2
import psycopg2.extras

CONFIG = Path(__file__).with_name("db_config.json")

# Return numeric columns as float, not Decimal. Decimal will not mix with float in templates.
psycopg2.extensions.register_type(psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values, "DEC2FLOAT",
    lambda v, cur: float(v) if v is not None else None))


def connect():
    cfg = json.loads(CONFIG.read_text())
    return psycopg2.connect(**cfg)


def query(sql, args=None):
    """Run a SELECT. Return a list of dicts."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, args or ())
            return cur.fetchall()


def execute(sql, args=None, returning=False):
    """Run an INSERT, UPDATE or DELETE."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            if returning:
                return cur.fetchone()[0]


def run_file(path):
    """Run a .sql file. Used for setup."""
    sql = Path(path).read_text()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
