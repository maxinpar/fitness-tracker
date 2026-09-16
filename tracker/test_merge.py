"""Smoke-test every page against the live database, Access gate off."""
import json
import os
import re

os.environ["CF_ACCESS_AUD"] = ""
os.environ["CF_ACCESS_TEAM_DOMAIN"] = ""

from app import app, catalogue, current_week, est_minutes, next_label  # noqa: E402

wk = current_week()
cat = catalogue(wk, next_label(wk))
planned = [c for c in cat if c["planned"]]

print(f"week {wk['week_no']} {wk['block']}  est {est_minutes(cat)} min\n")
print("PLANNED")
for c in planned:
    print(f"   {c['name']:<22} {c['sets']} x {c['reps']} {c['repUnit']:<5} "
          f"{c['kg']} {c['kgUnit']:<4} perSet {c['perSet']}")
print("EXTRA  ", [c["name"] for c in cat if not c["planned"]])

required = {"id", "name", "category", "planned", "sets", "reps", "kg", "ref",
            "perSet", "repStep", "repUnit", "kgStep", "kgUnit", "photo"}
missing = [c["name"] for c in cat if required - set(c)]
print("\ncatalogue contract:", "OK" if not missing else f"MISSING on {missing}")
json.dumps(cat)
print("catalogue serialises: OK")

print()
client = app.test_client()
for path in ("/", "/log", "/plan", "/progress", "/journal", "/settings", "/checkin"):
    r = client.get(path)
    body = r.get_data(as_text=True)
    print(f"{path:<11} {r.status_code}  {len(body):>6} bytes")
    if r.status_code != 200:
        for line in body.splitlines():
            if re.search(r"(Error|error:)", line) and "app.py" not in line:
                print("     ", line.strip()[:170])
                break
