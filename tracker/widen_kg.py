"""Store loads to 0.01 kg. Gym stacks come in steps like 23.25 and 10.75 kg.

Widens numeric(5,1) to numeric(6,2) on set_log.kg, prescription.kg and
exercise.ref_kg. Existing values are kept. Safe to re-run.
"""
import db

for table, col in (("set_log", "kg"), ("prescription", "kg"), ("exercise", "ref_kg")):
    db.execute(f"alter table {table} alter column {col} type numeric(6,2)")

print(db.query("select table_name, column_name, numeric_precision, numeric_scale "
               "from information_schema.columns where column_name in ('kg', 'ref_kg') "
               "and table_schema = 'public'"))
