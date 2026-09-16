"""Set reference loads from what Max actually lifted, not from my estimates.

ref_kg is the 100% load. Week 1 is 70% of it, rounded to 2.5 kg.
Goblet Squat 17.5 -> 12.5 in week 1 (he did 12).
Cable Chest Press 14 -> 10 in week 1 (he did 10, and it was fine).
"""
import db

db.execute("update exercise set ref_kg = 17.5 where name = %s", ("Goblet Squat",))
db.execute("update exercise set ref_kg = 14 where name = %s", ("Cable Chest Press",))

for r in db.query("select name, ref_kg from exercise where ref_kg is not null "
                  "order by sort_order"):
    wk1 = round(float(r["ref_kg"]) * 0.7 / 2.5) * 2.5
    print(f"{r['name']:<24} ref {r['ref_kg']:>5} kg   week 1 -> {wk1} kg")
