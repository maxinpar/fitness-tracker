"""Remove Split Kneeling Rocks from the programme. Max dropped it on 8 Oct 2026.

Deletes its prescription rows and the exercise. If it was ever logged, the
exercise row stays (set_log points at it) and is pushed past week 12 instead.
Safe to re-run.
"""
import db

NAME = "Split Kneeling Rocks"
rows = db.query("select id from exercise where name = %s", (NAME,))
if not rows:
    print(f"{NAME} is already gone.")
    raise SystemExit

ex = rows[0]["id"]
db.execute("delete from prescription where exercise_id = %s", (ex,))

logged = db.query("select count(*) as n from set_log where exercise_id = %s", (ex,))[0]["n"]
if logged:
    db.execute("update exercise set from_week = 99 where id = %s", (ex,))
    print(f"{NAME} has {logged} logged sets, so it stays in the catalogue but leaves every week.")
else:
    db.execute("delete from exercise where id = %s", (ex,))
    print(f"{NAME} removed.")

print("Week 4 now reads:")
for r in db.query("select e.name, p.sets, p.reps, p.kg from prescription p "
                  "join exercise e on e.id = p.exercise_id "
                  "where p.week_no = 4 order by p.sort_order"):
    print(f"  {r['name']:<22} {r['sets']} x {r['reps']:<8} {r['kg'] or '—'}")
