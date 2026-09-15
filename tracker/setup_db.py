"""Create the fitness database, then the tables, then the programme. Run once."""
import json
from pathlib import Path
import psycopg2
import db

HERE = Path(__file__).parent
cfg = json.loads((HERE / "db_config.json").read_text())
target = cfg["dbname"]

# CREATE DATABASE cannot run inside a transaction, so connect to postgres first.
admin = dict(cfg, dbname="postgres")
conn = psycopg2.connect(**admin)
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("select 1 from pg_database where datname = %s", (target,))
    if cur.fetchone():
        print(f"database {target} already exists")
    else:
        cur.execute(f'create database "{target}"')
        print(f"created database {target}")
conn.close()

for name in ("schema.sql", "seed.sql"):
    db.run_file(HERE / name)
    print(f"applied {name}")

print("plan weeks:", db.query("select count(*) as n from plan")[0]["n"])
print("exercises: ", db.query("select count(*) as n from exercise")[0]["n"])
