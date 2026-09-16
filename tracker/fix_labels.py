"""Weeks 1-8 are full body, so no session carries an A or B label.

Session 2 was saved as 'A' by the old buggy log screen, which made the Journal
call it "Squat + Pull". It was a full-body session.
"""
import db

db.execute("update gym_session set label = '-' where week_no < 9 and label in ('A', 'B')")
for r in db.query("select date, label, week_no from gym_session order by date"):
    print(f"  {r['date']}  week {r['week_no']}  label {r['label']!r}")
