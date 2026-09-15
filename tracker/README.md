# 12-Week Tracker

Flask + local Postgres. Single user. Runs on the laptop.

Database: `fitness` on localhost:5432. Its own database, used only by this project.

## Files

| File | Purpose |
|---|---|
| `schema.sql` | Creates the 6 tables. |
| `seed.sql` | Loads the 12-week plan and the exercise list. Safe to re-run. |
| `setup_db.py` | Runs both SQL files. Run once. |
| `db.py` | Connection and query helpers. |
| `app.py` | The web app. Port 5055. |
| `db_config.json` | Your Postgres credentials. You create this. Not shared. |

## Setup

1. Copy `db_config.example.json` to `db_config.json`.
2. Put your Postgres password in it.
3. Double-click `setup.bat`. It creates the database, the tables and the plan.

## Daily use

- Double-click `run.bat`. Open `http://localhost:5055`.
- On the phone, use `http://<laptop-ip>:5055` on the home Wi-Fi. The laptop must be awake.
- Log sets on paper at the gym. Enter them at home.

## Tables

- `daily` — one row per day. Garmin fills it.
- `exercise` — the exercise catalogue. `ref_kg` is the 100% load.
- `gym_session` — one gym session.
- `set_log` — one row per set. This is the progression record.
- `weekly` — the Sunday check-in.
- `plan` — the 12 weeks: target weight, load percentage, focus.

## Querying

Add a `postgres-fitness` MCP connection pointing at this database. Example query:

```sql
select e.name, s.date, l.set_no, l.reps, l.kg
from set_log l
join gym_session s on s.id = l.session_id
join exercise e on e.id = l.exercise_id
order by s.date desc, e.sort_order, l.set_no;
```
