"""Check the merge: which exercises the log screen offers, and what is on record."""
import os
import re

os.environ["CF_ACCESS_AUD"] = ""
os.environ["CF_ACCESS_TEAM_DOMAIN"] = ""

from app import app, current_week  # noqa: E402
import db  # noqa: E402

wk = current_week()
print(f"week {wk['week_no']} · {wk['block']} · {wk['sets_per_lift']} sets · "
      f"{wk['load_pct']}% · split={wk['split']}\n")

html = app.test_client().get("/log").get_data(as_text=True)
names = re.findall(r'class="ex-name">([^<]+)</span>', html)
split = html.find("Add an exercise")
planned = [n for n in names if html.find(f'>{n}<') < split]
print("PLANNED TODAY:")
for n in planned:
    print("  ", n)
print("OFFERED AS EXTRA:", len(names) - len(planned))
print("add-set control:", "yes" if "data-addset" in html else "NO")
print("remove-set control:", "yes" if "data-delset" in html else "NO")
print("A/B in nav:", "YES - BUG" if "Log A" in html else "no")

print("\nSESSIONS ON RECORD:")
for s in db.query("select id, date, label, week_no from gym_session order by date"):
    print(f"  #{s['id']} {s['date']} label={s['label']} week={s['week_no']}")
    for r in db.query("select e.name, l.set_no, l.reps, l.kg from set_log l "
                      "join exercise e on e.id=l.exercise_id where l.session_id=%s "
                      "order by e.sort_order, l.set_no", (s["id"],)):
        print(f"      {r['name']:<22} set {r['set_no']}  {r['reps']} reps  {r['kg']} kg")
