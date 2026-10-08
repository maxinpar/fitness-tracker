"""Log the 8 Oct 2026 session (week 4) from paper. Safe to re-run.

3 x 10 Goblet Squat at 16 kg, the rest as the week 4 plan. Split Kneeling Rocks
was skipped. The row time was not recorded.
"""
import db

SETS = [  # (exercise, reps, kg) per set
    ("500 m Row",            [(500, None)]),
    ("Goblet Squat",         [(10, 16)] * 3),
    ("Single Arm Row",       [(8, 22.5)] * 3),
    ("Cable Chest Press",    [(10, 12.5)] * 3),
    ("Pallof Press",         [(12, 12.5)] * 3),
    ("DB Romanian Deadlift", [(10, 17.5)] * 3),
    ("Face Pulls",           [(15, 12.5)] * 2),
]

rows = db.query("select id from gym_session where date = '2026-10-08'")
if rows:
    sid = rows[0]["id"]
else:
    sid = db.execute("insert into gym_session (date, label, week_no) values ('2026-10-08', '-', 4) "
                     "returning id", returning=True)

for name, sets in SETS:
    ex = db.query("select id from exercise where name = %s", (name,))[0]["id"]
    for set_no, (reps, kg) in enumerate(sets, 1):
        db.execute(
            "insert into set_log (session_id, exercise_id, set_no, reps, kg) "
            "values (%s, %s, %s, %s, %s) "
            "on conflict (session_id, exercise_id, set_no) do update "
            "set reps = excluded.reps, kg = excluded.kg",
            (sid, ex, set_no, reps, kg))

print("Session 8 Oct now reads:")
for r in db.query("select e.name, l.set_no, l.reps, l.kg from set_log l "
                  "join exercise e on e.id = l.exercise_id where l.session_id = %s "
                  "order by e.sort_order, l.set_no", (sid,)):
    kg = f"{r['kg']} kg" if r["kg"] else "—"
    print(f"  {r['name']:<22} set {r['set_no']}   {r['reps']} reps   {kg}")
