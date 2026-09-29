"""Freeze the programme into a prescription table.

Until now the prescription was computed at render time from exercise.ref_kg and
plan.load_pct. That meant changing a reference load silently rewrote every past
week. This table is the record of what was asked for, week by week.

Grain: one row per (week, session type, exercise). Within a week all three
sessions are identical by design, so there is no per-day row. Weeks 9-12 split
into session types A and B, so those weeks get two sets of rows.

Run with no arguments to generate every week.
Run with a week number to regenerate that week and every week after it, which
is what happens when a reference load changes.
"""
import sys

import db

SCHEMA = """
create table if not exists prescription (
  week_no       integer not null,
  session_label text    not null,          -- '-' in weeks 1-8, 'A' or 'B' in 9-12
  exercise_id   integer not null references exercise(id),
  sort_order    integer,
  sets          integer not null,
  reps          text,                      -- as written, e.g. '8 each'
  default_reps  integer,
  kg            numeric(6,2),              -- null means bodyweight
  primary key (week_no, session_label, exercise_id)
);
"""


def round_load(kg):
    return None if kg is None else round(float(kg) / 2.5) * 2.5


def generate(from_week=1):
    db.execute("delete from prescription where week_no >= %s", (from_week,))

    weeks = db.query("select * from plan where week_no >= %s order by week_no", (from_week,))
    lifts = db.query("select * from exercise order by sort_order")
    written = 0

    for wk in weeks:
        labels = ("A", "B") if wk["split"] else ("-",)
        for label in labels:
            for ex in lifts:
                if ex["from_week"] > wk["max_from_week"]:
                    continue
                if wk["split"] and ex["session_label"] not in (label, "BOTH"):
                    continue

                warmup = ex["category"] == "warmup"
                sets = 1 if warmup else min(ex["target_sets"], wk["sets_per_lift"])
                kg = round_load(float(ex["ref_kg"]) * wk["load_pct"] / 100) if ex["ref_kg"] else None

                db.execute(
                    "insert into prescription "
                    "(week_no, session_label, exercise_id, sort_order, sets, reps, default_reps, kg) "
                    "values (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (wk["week_no"], label, ex["id"], ex["sort_order"], sets,
                     ex["target_reps"], ex["default_reps"], kg))
                written += 1
    return written


if __name__ == "__main__":
    db.run_file_sql = None
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    n = generate(start)
    print(f"{n} prescription rows written, from week {start} onwards\n")

    for wk in db.query("select distinct week_no from prescription order by week_no"):
        w = wk["week_no"]
        rows = db.query(
            "select p.session_label, e.name, p.sets, p.reps, p.kg "
            "from prescription p join exercise e on e.id = p.exercise_id "
            "where p.week_no = %s order by p.session_label, p.sort_order", (w,))
        labels = sorted({r["session_label"] for r in rows})
        print(f"week {w:>2}: {len(rows)} rows, session types {labels}")
