"""Log the 20 Oct 2026 session (week 6) from the gym chat. Safe to re-run.

Row 500 m in 2:12. Face pulls went to 3 sets. Chest press at 13.25 kg on the stack.
"""
import db

DATE, WEEK = "2026-10-20", 6
SETS = [  # (exercise, [(reps, kg)] per set). The row keeps its time in seconds in kg.
    ("500 m Row",            [(500, 132)]),
    ("Goblet Squat",         [(10, 16)] * 3),
    ("Single Arm Row",       [(8, 25)] * 3),
    ("Cable Chest Press",    [(10, 13.25)] * 3),
    ("Pallof Press",         [(12, 15)] * 3),
    ("DB Romanian Deadlift", [(10, 20)] * 3),
    ("Face Pulls",           [(15, 15)] * 3),
]

rows = db.query("select id from gym_session where date = %s", (DATE,))
if rows:
    sid = rows[0]["id"]
else:
    sid = db.execute("insert into gym_session (date, label, week_no) values (%s, '-', %s) "
                     "returning id", (DATE, WEEK), returning=True)

for name, sets in SETS:
    ex = db.query("select id from exercise where name = %s", (name,))[0]["id"]
    for set_no, (reps, kg) in enumerate(sets, 1):
        db.execute(
            "insert into set_log (session_id, exercise_id, set_no, reps, kg) "
            "values (%s, %s, %s, %s, %s) "
            "on conflict (session_id, exercise_id, set_no) do update "
            "set reps = excluded.reps, kg = excluded.kg",
            (sid, ex, set_no, reps, kg))

print(f"Session {DATE} now reads:")
for r in db.query("select e.name, l.set_no, l.reps, l.kg from set_log l "
                  "join exercise e on e.id = l.exercise_id where l.session_id = %s "
                  "order by e.sort_order, l.set_no", (sid,)):
    kg = f"{r['kg']} kg" if r["kg"] else "—"
    print(f"  {r['name']:<22} set {r['set_no']}   {r['reps']} reps   {kg}")
