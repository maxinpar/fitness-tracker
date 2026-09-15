# Fitness Tracker — Project Instructions for Claude

A 12-week training and fat-loss tracker. Flask + local Postgres. Single user, runs on the laptop.

## Layout

```
fitness-tracker/
  .venv/                  This project's Python. Use it for everything.
  tracker/                The web app.
    app.py                Flask app, port 5055.
    db.py                 Connection and query helpers.
    schema.sql            The 6 tables.
    seed.sql              The 12-week plan and exercise list. Safe to re-run.
    setup_db.py           Creates the database, applies schema then seed.
    db_config.json        Postgres credentials. Never print its contents.
    run.bat               Start the app.
    garmin_reauth.bat     Fresh Garmin login when the token expires.
  garmin_sync.py          Garmin Connect sync.
  garmin_sync_runner.bat  Called daily at 08:00 by Task Scheduler.
  garmin_log.csv          Garmin data, the source of truth.
```

## Python — use this exact executable

```
C:\Users\maxim\PycharmProjects\fitness-tracker\.venv\Scripts\python.exe
```

Do NOT use `python`, `py` or `python3`. They fail on this machine. Do not ask which Python to use;
it is always the path above. `requirements.txt` records the installed versions.

## Database

- `fitness` on `localhost:5432`, public schema. Auth is scram-sha-256.
- Read it with the `postgres-fitness` MCP connection, which is read-only and connects as the
  `fitness_ro` role. Use a Python script in `tracker/` for any write.
- Credentials live in `tracker/db_config.json`. Never print them.

Tables: `daily` (one row per day, Garmin fills it), `exercise` (catalogue, `ref_kg` is the 100%
load), `gym_session`, `set_log` (the progression record), `weekly` (Sunday check-in), `plan`
(the 12 weeks).

## Running it

- `tracker\run.bat`, then open `http://localhost:5055`.
- On the phone, use the laptop IP on the home Wi-Fi. The laptop must be awake.
- Log sets on paper at the gym. Enter them at home.

## Programme summary

- **Dates:** Mon 14 Sep 2026 to Sun 6 Dec 2026.
- **Weight:** 78 kg baseline (estimated 9 Sep, not weighed) to 72 kg.
- **Goals:** 72 kg, visible abs, golf fitness, no injury.
- **Diet (soft):** eating window 12:00–20:00. Maximum 4 standard drinks per week, none Mon–Thu.
  No dessert or sweets, one treat per week. 130–140 g protein per day. 9,000 steps per day.
- **Training:** 3 gym sessions per week, alternating Session A and Session B. Golf once a week.
  - Weeks 1–3 Ramp, 70–80% load, 2 sets.
  - Weeks 4–7 Build, 85–100% load, 3 sets.
  - Week 8 Deload, 60% load.
  - Weeks 9–12 Sharpen, 100–105% load, plus the Cable Rotational Chop.
- **Loads:** `exercise.ref_kg` is the 100% reference load. The app multiplies it by the week's
  `load_pct` and rounds to 2.5 kg.
- **Check-in:** Sunday evening, on the `/checkin` page.

## Garmin sync

```
"C:\Users\maxim\PycharmProjects\fitness-tracker\.venv\Scripts\python.exe" "C:\Users\maxim\PycharmProjects\fitness-tracker\garmin_sync.py" --from YYYY-MM-DD --to YYYY-MM-DD
```

The script writes `garmin_log.csv` first, which stays the source of truth. It then upserts
`weight_kg`, `steps`, `sleep_mins` and `resting_hr` into the `daily` table.

**Flags:** `--force` overwrites existing values. `--no-db` skips the Postgres push. `--setup`
clears the cached token and forces a fresh login. `--non-interactive` never prompts and exits with
a clear error instead; Task Scheduler passes this. `--dry-run` fetches and prints without writing.

`garmin_sync_runner.bat` runs daily at 08:00 via the `Garmin Daily Sync` scheduled task.

### Known failure mode

When the OAuth token expires it does NOT disappear — `garmin_tokens.json` stays in
`C:\Users\maxim\.garminconnect` and starts returning `API Error 401`. Fix it by running
`tracker\garmin_reauth.bat` from a terminal. Max must be at the machine, because Garmin prompts for
the password and an MFA code.

Garmin rate-limits the login endpoints this library uses. Repeated failed logins return
`429 IP rate limited`, and the fallback path then reports `401 Invalid Username or Password`, which
is misleading — it does not mean the password is wrong. Wait an hour rather than retrying. A working
browser login at connect.garmin.com does not clear it; the browser uses different endpoints.

After any sync, check actual values rather than row counts:
`select count(steps), count(sleep_mins) from daily;`

## Weekly progress photos

Max copies the photos himself. Do NOT upload or move photos programmatically.

## How to work with Max

- Skip generic advice. Work from his stats, his food style, and his timeline.
- Be direct and practical. Give actionable outputs only.
- Flag if he is off track. Do not lecture.
- Weekly check-in prompts: weight, sleep quality, alcohol units, sessions done, any issues.
- Units: metric (kg, km, °C).
- Write in Simplified Technical English. Short sentences. Active voice.
- Do not create `.xlsx` tracker files.
- Never use the Chrome connector.
