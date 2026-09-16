"""Add the Cable Chest Press Max did on 15 Sep but the app never offered.

2 sets of 10 at 10 kg, from his own recollection. One-off repair, safe to re-run.
"""
import db

sid = db.query("select id from gym_session where date = '2026-09-15'")[0]["id"]
ex = db.query("select id from exercise where name = 'Cable Chest Press'")[0]["id"]

for set_no in (1, 2):
    db.execute(
        "insert into set_log (session_id, exercise_id, set_no, reps, kg) "
        "values (%s, %s, %s, 10, 10) "
        "on conflict (session_id, exercise_id, set_no) do update set reps = 10, kg = 10",
        (sid, ex, set_no),
    )

print("Session 15 Sep now reads:")
for r in db.query("select e.name, l.set_no, l.reps, l.kg from set_log l "
                  "join exercise e on e.id = l.exercise_id where l.session_id = %s "
                  "order by e.sort_order, l.set_no", (sid,)):
    kg = f"{r['kg']} kg" if r["kg"] else "—"
    print(f"  {r['name']:<20} set {r['set_no']}   {r['reps']} reps   {kg}")
