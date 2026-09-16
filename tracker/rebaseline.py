"""Re-baseline the programme to 77.0 kg.

78.0 was an estimate made on 9 Sep. The scales read 76.4 on 15 Sep. Max set the
baseline at 77.0. 5.0 kg over 12 weeks, about 0.4 a week, easing through the
week 8 deload and finishing at 72.0 on 6 Dec.
"""
from pathlib import Path

import db

BASELINE = 77.0
TARGETS = {1: 76.6, 2: 76.2, 3: 75.8, 4: 75.4, 5: 75.0, 6: 74.6,
           7: 74.2, 8: 74.0, 9: 73.5, 10: 73.0, 11: 72.5, 12: 72.0}

for week, kg in TARGETS.items():
    db.execute("update plan set target_weight_kg = %s where week_no = %s", (kg, week))

app = Path(__file__).with_name("app.py")
s = app.read_text(encoding="utf-8")
s = s.replace("START_KG = 78.0", f"START_KG = {BASELINE}")
app.write_text(s, encoding="utf-8")

print(f"baseline {BASELINE} kg -> target 72.0 kg\n")
prev = BASELINE
for r in db.query("select week_no, block, start_date, target_weight_kg from plan order by week_no"):
    kg = float(r["target_weight_kg"])
    print(f"  wk{r['week_no']:>2} {r['block']:<7} ends {r['start_date'].day:>2} "
          f"{r['start_date']:%b}  {kg:.1f} kg   ({kg - prev:+.1f})")
    prev = kg
print(f"\ntotal {BASELINE - 72.0:.1f} kg")
