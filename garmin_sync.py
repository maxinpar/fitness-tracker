#!/usr/bin/env python3
"""
Garmin Connect API sync for the 12-week fitness tracker.
Fetches daily steps, sleep, resting HR and weight from the Garmin Connect API.

SETUP (one-time):
  pip install garminconnect google-api-python-client google-auth-oauthlib google-auth-httplib2
  python3 garmin_sync.py --setup           # Garmin auth
  python3 garmin_sync.py --setup-sheets    # Google Sheets auth (opens browser once)

REGULAR SYNC (fetches Garmin data AND pushes to Google Sheets):
  python3 garmin_sync.py

SYNC SPECIFIC RANGE:
  python3 garmin_sync.py --from 2026-04-20 --to 2026-04-26

FORCE OVERWRITE existing values (e.g. to refresh all data):
  python3 garmin_sync.py --from 2026-04-14 --force

SKIP SHEETS PUSH (CSV only):
  python3 garmin_sync.py --no-db

NOTES:
  - Preserves manual corrections in the CSV (won't overwrite non-blank fields unless --force)
  - Resting HR is Garmin's own overnight calculation, taken from the API as-is.
  - Sleep duration comes from the API already cleaned; no extra trimming is applied.
  - Garmin credentials: email saved to garmin_config.json, password via GARMIN_PASSWORD env var
    or interactive prompt. Tokens cached in ~/.garminconnect/ — MFA only needed once.
  - Google credentials: download OAuth2 credentials (Desktop app) from Google Cloud Console,
    save as google_credentials.json in this folder, then run --setup-sheets once.
    Token cached to ~/.google_sheets_token.json — auto-refreshes silently.
"""

import os
import json
import csv
import time
import sys
import socket
import getpass
import argparse
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

# ── Paths & schema ────────────────────────────────────────────────────────────
FOLDER      = Path(__file__).parent
OUT_CSV     = FOLDER / "garmin_log.csv"
CONFIG_FILE = FOLDER / "garmin_config.json"
TOKEN_DIR   = Path.home() / ".garminconnect"

# Network safety net. Without this a stalled Garmin request can block the 08:00
# scheduled task indefinitely. Covers the socket-based (requests) login paths.
NET_TIMEOUT = 30
socket.setdefaulttimeout(NET_TIMEOUT)

# Set by --non-interactive. When true, never prompt; fail with a clear message.
NO_PROMPT = False

# ── Google Sheets config ──────────────────────────────────────────────────────
SPREADSHEET_ID   = "1dx6G5sVMeMyYxjokq1O4u48UVPifdAMCAxI-8t_92CM"
DAILY_LOG_SHEET  = "Daily Log"
PROGRAMME_START  = date(2026, 4, 20)   # Day 1
SHEET_ROW_DAY1   = 13                  # Row 13 = Day 1 in the sheet
SHEETS_SCOPES    = ["https://www.googleapis.com/auth/spreadsheets"]
SHEETS_TOKEN     = Path.home() / ".google_sheets_token.json"
SHEETS_CREDS     = FOLDER / "google_credentials.json"

FIELDS = ["date","steps","sleep_start","sleep_end","sleep_mins",
          "awake_mins","avg_hr","resting_hr","max_hr","weight_kg","water_ml","notes"]

# Sydney AEST offset (no DST during Apr–Jun)
SYDNEY = timedelta(hours=10)


# ── Auth & client ─────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}

def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    CONFIG_FILE.chmod(0o600)

def _can_prompt() -> bool:
    """
    True only if a human can actually type at this process.
    Task Scheduler runs with no console, so stdin is not a tty. Prompting there
    blocks forever and the run dies with no output — that is what hid an expired
    token for 82 days from 19 Jun 2026.
    """
    if NO_PROMPT:
        return False
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _no_prompt_exit(what: str):
    """Fail loudly and legibly instead of blocking on a prompt nobody can answer."""
    raise SystemExit(f"""
  AUTH REQUIRED: {what} is needed, but this run is not interactive.
  The cached Garmin token is missing or expired.
  Fix: run tracker/garmin_reauth.bat from a terminal, then type the
  password and the MFA code. Until then this sync writes nothing.
""")


def get_garmin_client():
    """
    Return an authenticated Garmin client.
    - First run: prompts for email, password, MFA; saves tokens to ~/.garminconnect/
    - Subsequent runs: loads tokens silently, refreshes automatically.
    - If tokens expired: prompts for password + MFA only.
    """
    try:
        from garminconnect import Garmin
    except ImportError:
        raise SystemExit(
            "\n  garminconnect not installed.\n"
            "  Run: pip install garminconnect\n"
        )

    cfg   = load_config()
    email = cfg.get("email") or os.environ.get("GARMIN_EMAIL")
    if not email:
        if not _can_prompt():
            _no_prompt_exit("a Garmin email")
        email = input("Garmin email: ").strip()

    if not cfg.get("email"):
        cfg["email"] = email
        save_config(cfg)
        print(f"  Email saved to {CONFIG_FILE.name}")

    TOKEN_DIR.mkdir(mode=0o700, exist_ok=True)

    def _mfa():
        if not _can_prompt():
            _no_prompt_exit("an MFA code")
        return input("  MFA code: ").strip()

    password = os.environ.get("GARMIN_PASSWORD", "")
    client = Garmin(email=email, password=password, prompt_mfa=_mfa)

    # Only try the cached-token path if a token actually exists. Calling login()
    # with no token and no password still fires a real login request at Garmin,
    # which counts towards its login rate limit for nothing.
    have_tokens = any(TOKEN_DIR.glob("*.json"))

    try:
        if not have_tokens:
            raise FileNotFoundError("no cached token")
        client.login(str(TOKEN_DIR))
        print("  ✓ Authenticated (cached tokens)")
    except Exception:
        # Tokens missing or expired — do full login
        if not password:
            if not _can_prompt():
                _no_prompt_exit("a Garmin password")
            # getpass can silently swallow input on Windows PowerShell —
            # fall back to visible input if getpass returns empty string
            password = getpass.getpass("  Garmin password: ")
            if not password:
                print("  (password prompt didn't work — entering visibly instead)")
                password = input("  Garmin password: ").strip()
        client = Garmin(email=email, password=password, prompt_mfa=_mfa)
        client.login(str(TOKEN_DIR))
        print("  ✓ Authenticated (new session — tokens saved)")

    return client


# ── Data fetching ─────────────────────────────────────────────────────────────

def _ms_to_hhmm(ms) -> str | None:
    """
    Convert a Garmin 'Local' millisecond timestamp to HH:MM.
    Garmin's *TimestampLocal fields already encode local time — no offset needed.
    Using utcfromtimestamp reads the raw value without re-applying a tz shift.
    """
    if not ms:
        return None
    return datetime.utcfromtimestamp(ms / 1000).strftime("%H:%M")

def fetch_day(client, day: date, retries: int = 3, debug: bool = False) -> dict:
    """
    Fetch all metrics for one day from the Garmin API.
    Returns a dict with keys matching CSV FIELDS.
    Returns {} on complete failure (will not overwrite existing data).
    """
    day_str = day.isoformat()
    result  = {"date": day_str}

    for attempt in range(retries):
        try:
            # ── Daily stats: steps + HR overview ─────────────────────────────
            stats = client.get_stats(day_str) or {}
            if debug:
                print(f"\n  [DEBUG] get_stats keys: {list(stats.keys())}")
                prev = (day - timedelta(days=1)).isoformat()
                print(f"  [DEBUG] sleep keys: {list((client.get_sleep_data(prev) or {}).keys())}\n")
            steps = (stats.get("steps") or stats.get("totalSteps"))
            result["steps"] = int(steps) if steps else None
            # avg_hr not available in get_stats() — no single daily average field exists.
            # resting_hr and max_hr available but less accurate than FIT 5th-percentile method.
            # Both are handled as FIT-only in merge_into(); grabbed here only as fallback.
            result["resting_hr"] = stats.get("restingHeartRate") or None
            result["max_hr"]     = stats.get("maxHeartRate") or None

            # Small pause between calls to avoid rate limits
            time.sleep(0.5)

            # ── Sleep ─────────────────────────────────────────────────────────
            # IMPORTANT: Garmin API tags sleep to the night you GO TO BED.
            # Our CSV convention (matching FIT parser) tags sleep to the day you WAKE UP.
            # So for CSV date D, we request API sleep for date D-1.
            prev_day = (day - timedelta(days=1)).isoformat()
            sleep_raw = client.get_sleep_data(prev_day) or {}

            sdto = (sleep_raw.get("dailySleepDTO")
                    or sleep_raw.get("sleepDTO")
                    or sleep_raw)

            start_ms  = (sdto.get("sleepStartTimestampLocal")
                         or sdto.get("sleepStartTimestampGMT"))
            end_ms    = (sdto.get("sleepEndTimestampLocal")
                         or sdto.get("sleepEndTimestampGMT"))
            sleep_sec = (sdto.get("sleepTimeSeconds") or sdto.get("sleepSeconds") or 0)
            awake_sec = (sdto.get("awakeSleepSeconds")
                         or sdto.get("awakeDurationInSeconds")
                         or sdto.get("awakeSleepDurationInSeconds")
                         or 0)

            if start_ms:
                result["sleep_start"] = _ms_to_hhmm(start_ms)
                result["sleep_end"]   = _ms_to_hhmm(end_ms)
                result["sleep_mins"]  = round(sleep_sec / 60) if sleep_sec else None
                result["awake_mins"]  = round(awake_sec / 60) if awake_sec else None

            # ── Hydration (if tracked in Garmin app) ─────────────────────────
            time.sleep(0.5)
            try:
                hydration = client.get_hydration_data(day_str) or {}
                ml = (hydration.get("totalIntakeInML")
                      or hydration.get("valueInML"))
                result["water_ml"] = int(ml) if ml else None
            except Exception:
                pass  # hydration endpoint not available on all accounts

            # ── Weight (from Garmin scale or manual Garmin Connect entry) ──────
            time.sleep(0.5)
            try:
                body = client.get_body_composition(day_str, day_str) or {}
                # Response: {"dateWeightList": [{"weight": 79400.0, ...}], ...}
                # weight is in grams
                entries = body.get("dateWeightList") or []
                if entries:
                    w_grams = entries[0].get("weight")
                    if w_grams:
                        result["weight_kg"] = round(w_grams / 1000, 1)
            except Exception:
                pass  # no scale / endpoint not available

            break  # success

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower():
                wait = 30 * (attempt + 1)
                print(f"\n  Rate limited — waiting {wait}s before retry...")
                time.sleep(wait)
            elif attempt < retries - 1:
                wait = 2 ** attempt
                print(f"\n  Retry {attempt + 1}/{retries} (wait {wait}s): {e}")
                time.sleep(wait)
            else:
                print(f"\n  ✗ Could not fetch {day_str}: {e}")
                return result  # return partial data, don't crash

    return result


# ── CSV helpers ───────────────────────────────────────────────────────────────

def load_csv() -> dict:
    existing = {}
    if OUT_CSV.exists():
        with open(OUT_CSV, newline='') as f:
            for row in csv.DictReader(f):
                existing[row["date"]] = row
    return existing

def merge_into(existing_row: dict, fresh: dict, force: bool = False) -> dict:
    """
    Merge API data into an existing CSV row.
    Policy: only fill blanks — never overwrite manual corrections — unless --force.
    'notes' is always preserved from existing data.
    FIT_ONLY fields are never overwritten by API data even with --force: the FIT
    parser's 5th-percentile resting HR and full-day max HR are more accurate than
    Garmin's API equivalents.
    """
    FIT_ONLY = {"resting_hr", "max_hr", "awake_mins"}  # always prefer FIT-parsed values
    merged = dict(existing_row)
    for k, v in fresh.items():
        if k in ("date", "notes"):
            continue                                    # never touch these
        if k in FIT_ONLY and merged.get(k):
            continue                                    # keep FIT value if present
        if force or not merged.get(k):                 # only fill blanks otherwise
            if v is not None:
                merged[k] = str(v)
    return merged

def save_csv(rows: dict):
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for day_str in sorted(rows.keys()):
            w.writerow({k: rows[day_str].get(k, "") for k in FIELDS})


# ── Google Sheets helpers ─────────────────────────────────────────────────────

def get_sheets_service():
    """
    Return an authenticated Google Sheets API service.
    - First run (--setup-sheets): opens browser, saves token to ~/.google_sheets_token.json
    - Subsequent runs: loads token silently, auto-refreshes when expired.
    Raises SystemExit with instructions if google_credentials.json is missing.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise SystemExit(
            "\n  Google API libraries not installed.\n"
            "  Run: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2\n"
        )

    creds = None
    if SHEETS_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(SHEETS_TOKEN), SHEETS_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"  Token refresh failed ({e}), re-authenticating via browser...")
                creds = None
        if not creds or not creds.valid:
            if not SHEETS_CREDS.exists():
                raise SystemExit(
                    f"\n  Google credentials file not found: {SHEETS_CREDS.name}\n\n"
                    f"  One-time setup:\n"
                    f"  1. Go to https://console.cloud.google.com/\n"
                    f"  2. Create/select a project → APIs & Services → Enable Google Sheets API\n"
                    f"  3. Credentials → Create Credentials → OAuth client ID → Desktop app\n"
                    f"  4. Download JSON → rename to google_credentials.json → place in:\n"
                    f"     {FOLDER}\n"
                    f"  5. Run: python garmin_sync.py --setup-sheets\n"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(SHEETS_CREDS), SHEETS_SCOPES)
            creds = flow.run_local_server(port=0)

        SHEETS_TOKEN.write_text(creds.to_json())
        SHEETS_TOKEN.chmod(0o600)

    return build("sheets", "v4", credentials=creds)


def push_to_sheets(rows: dict, dates_to_push: list, force: bool = False):
    """
    Push data for the given dates from `rows` (CSV data dict) into the Sheets Daily Log.
    - Skips dates before PROGRAMME_START
    - Skips dates that already have data in column D (steps) unless force=True
    - Never pushes today (data still accumulating)
    """
    eligible = [d for d in dates_to_push
                if d >= PROGRAMME_START and d < date.today()]
    if not eligible:
        print("  Sheets: nothing to push.")
        return

    try:
        service = get_sheets_service()
    except SystemExit as e:
        print(f"\n  ⚠ Sheets push skipped:{e}")
        return

    # Read existing sheet state to detect which rows already have data
    max_row = SHEET_ROW_DAY1 + (date.today() - PROGRAMME_START).days + 5
    read_range = f"'{DAILY_LOG_SHEET}'!B{SHEET_ROW_DAY1}:P{max_row}"
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range=read_range
        ).execute()
        sheet_rows = result.get("values", [])
    except Exception as e:
        print(f"\n  ⚠ Sheets push skipped — could not read sheet: {e}")
        return

    # Index: day_number (1-based) → list of cell values already in sheet
    sheet_index = {i + 1: vals for i, vals in enumerate(sheet_rows)}

    updates = []
    for d in sorted(eligible):
        day_num   = (d - PROGRAMME_START).days + 1
        sheet_row = SHEET_ROW_DAY1 + day_num - 1

        # Skip if steps column (D = index 2 within B:P) already has a value
        existing_vals = sheet_index.get(day_num, [])
        if not force and len(existing_vals) > 2 and existing_vals[2]:
            continue

        csv_row = rows.get(d.isoformat(), {})

        # Date as "22 Apr" (Windows-compatible, no leading zero stripping needed)
        date_str  = f"{d.day} {d.strftime('%b')}"
        steps_raw = csv_row.get("steps", "")
        ge8k      = "✓" if steps_raw and int(steps_raw) >= 8000 else ("✗" if steps_raw else "")

        sleep_mins = csv_row.get("sleep_mins", "")
        awake_mins = csv_row.get("awake_mins", "")
        try:
            true_sleep = str(int(sleep_mins) - int(awake_mins)) if sleep_mins and awake_mins else ""
        except ValueError:
            true_sleep = ""

        row_values = [
            date_str,                           # B: Date
            str(day_num),                       # C: Day #
            steps_raw,                          # D: Steps
            ge8k,                               # E: ≥8k?
            csv_row.get("sleep_start", ""),     # F: Sleep Start
            csv_row.get("sleep_end",   ""),     # G: Sleep End
            sleep_mins,                         # H: Total Mins
            awake_mins,                         # I: Awake Mins
            true_sleep,                         # J: True Sleep
            csv_row.get("avg_hr",      ""),     # K: Avg HR
            csv_row.get("resting_hr",  ""),     # L: Rest HR
            csv_row.get("max_hr",      ""),     # M: Max HR
            csv_row.get("weight_kg",   ""),     # N: Weight kg
            csv_row.get("notes",       ""),     # O: Notes
            csv_row.get("water_ml",    ""),     # P: Water ml
        ]

        updates.append({
            "range":  f"'{DAILY_LOG_SHEET}'!B{sheet_row}:P{sheet_row}",
            "values": [row_values],
        })

    # ── Daily Checklist: water column (H) ────────────────────────────────────
    # Checklist row mapping: same as Daily Log — row 12 + day_number
    # Water stored as litres (ml / 1000), only fill if currently empty
    CHECKLIST_SHEET    = "Daily Checklist"
    CHECKLIST_ROW_DAY1 = 12   # row 12 = Day 1 in checklist

    checklist_read = f"'{CHECKLIST_SHEET}'!H{CHECKLIST_ROW_DAY1}:H{max_row}"
    try:
        cl_result     = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range=checklist_read
        ).execute()
        checklist_water = cl_result.get("values", [])  # list of [value] or []
    except Exception:
        checklist_water = []

    for d in sorted(eligible):
        day_num      = (d - PROGRAMME_START).days + 1
        checklist_row = CHECKLIST_ROW_DAY1 + day_num - 1
        csv_row       = rows.get(d.isoformat(), {})
        water_ml      = csv_row.get("water_ml", "")
        if not water_ml:
            continue
        # Check if already filled
        idx           = day_num - 1
        existing_val  = checklist_water[idx][0] if idx < len(checklist_water) and checklist_water[idx] else ""
        if not force and existing_val:
            continue
        water_litres  = round(int(water_ml) / 1000, 1)
        updates.append({
            "range":  f"'{CHECKLIST_SHEET}'!H{checklist_row}",
            "values": [[str(water_litres)]],
        })

    if not updates:
        print("  Sheets: already up to date — nothing to push.")
        return

    try:
        body = {"valueInputOption": "USER_ENTERED", "data": updates}
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID, body=body
        ).execute()
        dl_pushed = [u["range"] for u in updates if DAILY_LOG_SHEET in u["range"]]
        cl_pushed = [u["range"] for u in updates if CHECKLIST_SHEET in u["range"]]
        if dl_pushed:
            print(f"  ✓ Daily Log: pushed {len(dl_pushed)} row(s)")
        if cl_pushed:
            print(f"  ✓ Daily Checklist: updated water for {len(cl_pushed)} day(s)")
    except Exception as e:
        print(f"\n  ⚠ Sheets push failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

# ── Postgres push ─────────────────────────────────────────────────────────────

DB_CONFIG = FOLDER / "tracker" / "db_config.json"


def push_to_postgres(rows: dict, dates_to_push: list) -> None:
    """Upsert the given dates into daily. The CSV stays the source of truth."""
    if not dates_to_push:
        return
    if not DB_CONFIG.exists():
        print(f"  ! {DB_CONFIG.name} not found — skipped the database push.")
        return
    try:
        import json as _json
        import psycopg2
    except ImportError:
        print("  ! psycopg2 not installed — skipped the database push.")
        return

    cfg = _json.loads(DB_CONFIG.read_text())
    sql = """
        insert into daily (date, weight_kg, steps, sleep_mins, resting_hr)
        values (%s, %s, %s, %s, %s)
        on conflict (date) do update set
          weight_kg  = coalesce(excluded.weight_kg,  daily.weight_kg),
          steps      = coalesce(excluded.steps,      daily.steps),
          sleep_mins = coalesce(excluded.sleep_mins, daily.sleep_mins),
          resting_hr = coalesce(excluded.resting_hr, daily.resting_hr)
    """

    def num(v, cast):
        v = (v or "").strip() if isinstance(v, str) else v
        try:
            return cast(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    try:
        with psycopg2.connect(**cfg) as conn:
            with conn.cursor() as cur:
                for day in dates_to_push:
                    r = rows.get(day, {})
                    cur.execute(sql, (
                        day,
                        num(r.get("weight_kg"), float),
                        num(r.get("steps"), int),
                        num(r.get("sleep_mins"), int),
                        num(r.get("resting_hr"), int),
                    ))
        print(f"✓ {len(dates_to_push)} day(s) upserted into daily")
    except Exception as e:
        print(f"  ! database push failed: {e}")


def main():
    ap = argparse.ArgumentParser(
        description="Sync Garmin Connect data to garmin_log.csv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--from",  dest="date_from", metavar="YYYY-MM-DD",
                    help="Start date (default: day after last in CSV)")
    ap.add_argument("--to",    dest="date_to",   metavar="YYYY-MM-DD",
                    help="End date inclusive (default: yesterday)")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing non-blank values")
    ap.add_argument("--dry-run", action="store_true",
                    help="Fetch from API and print results without touching garmin_log.csv")
    ap.add_argument("--setup", action="store_true",
                    help="Clear cached tokens and do a fresh Garmin login")
    ap.add_argument("--setup-sheets", action="store_true",
                    help="Authenticate with Google Sheets (opens browser once, saves token)")
    ap.add_argument("--sheets", action="store_true",
                    help="also push to Google Sheets (off by default since the Postgres migration)")
    ap.add_argument("--no-db", action="store_true",
                    help="skip the Postgres push")
    ap.add_argument("--debug", action="store_true",
                    help="Print raw API response for first date (helps diagnose field names)")
    ap.add_argument("--non-interactive", action="store_true",
                    help="Never prompt. Exit with a logged error instead. Use from Task Scheduler.")
    args = ap.parse_args()

    # Task Scheduler passes --non-interactive so a missing token can never block
    # the run on an unanswerable prompt. isatty() alone is not trustworthy here:
    # Git Bash reports a tty even with stdin redirected from /dev/null.
    global NO_PROMPT
    NO_PROMPT = args.non_interactive

    # Google Sheets one-time auth setup
    if args.setup_sheets:
        print("\nAuthenticating with Google Sheets (browser will open)...\n")
        get_sheets_service()
        print(f"  ✓ Token saved to {SHEETS_TOKEN}\n"
              f"  Future runs will authenticate silently.\n")
        return

    # Clear tokens if --setup
    if args.setup:
        cleared = 0
        for f in TOKEN_DIR.glob("*.json"):
            f.unlink(); cleared += 1
        print(f"Cleared {cleared} cached token file(s) — fresh login required.\n")

    existing = load_csv()

    # Determine date range
    yesterday = date.today() - timedelta(days=1)
    if args.date_from:
        start = date.fromisoformat(args.date_from)
    elif existing:
        start = date.fromisoformat(max(existing.keys())) + timedelta(days=1)
    else:
        start = yesterday - timedelta(days=6)

    end = date.fromisoformat(args.date_to) if args.date_to else yesterday

    if start > end:
        print(f"Nothing to sync — CSV already covers up to {end}.")
        return

    n_days = (end - start).days + 1
    mode   = "DRY RUN (no files changed)" if args.dry_run else "LIVE"
    print(f"\nGarmin Connect sync [{mode}]: {start} → {end}  ({n_days} day{'s' if n_days>1 else ''})\n")

    client = get_garmin_client()
    print()

    if args.dry_run:
        print(f"  {'DATE':<12} {'STEPS':>6}  {'SLEEP':>9}  {'WINDOW':>11}  "
              f"{'AVG HR':>6}  {'REST HR':>7}  {'WATER':>8}")
        print(f"  {'-'*12} {'-'*6}  {'-'*9}  {'-'*11}  {'-'*6}  {'-'*7}  {'-'*8}")
        existing_csv_vals = load_csv()

    updated = 0
    updated_dates = []
    for n in range(n_days):
        day     = start + timedelta(days=n)
        day_str = day.isoformat()

        if not args.dry_run:
            print(f"  {day_str} ... ", end="", flush=True)

        fresh = fetch_day(client, day, debug=(args.debug and n == 0))

        if args.dry_run:
            # Print API values alongside existing CSV values for comparison
            sm  = int(fresh.get("sleep_mins") or 0)
            csv_row = existing_csv_vals.get(day_str, {})
            csv_sm  = int(csv_row.get("sleep_mins") or 0)

            print(f"  {day_str:<12} "
                  f"{str(fresh.get('steps','—')):>6}  "
                  f"{(str(sm//60)+'h'+str(sm%60).zfill(2)+'m') if sm else '—':>9}  "
                  f"{(fresh.get('sleep_start','?')+'→'+fresh.get('sleep_end','?')) if fresh.get('sleep_start') else '—':>11}  "
                  f"{str(fresh.get('avg_hr','—')):>6}  "
                  f"{str(fresh.get('resting_hr','—')):>7}  "
                  f"{str(fresh.get('water_ml') or '—'):>8}")

            # Show diff vs existing CSV
            diffs = []
            for field in ("steps","sleep_mins","awake_mins","avg_hr","resting_hr","max_hr"):
                api_val = str(fresh.get(field) or "")
                csv_val = str(csv_row.get(field) or "")
                if api_val and csv_val and api_val != csv_val:
                    diffs.append(f"{field}: CSV={csv_val} → API={api_val}")
            if diffs:
                for d in diffs:
                    print(f"    ⚠ {d}")
        else:
            existing_row = existing.get(day_str, {"date": day_str})
            existing[day_str] = merge_into(existing_row, fresh, force=args.force)
            updated += 1
            # Must be the ISO string, not the date object: `existing` is keyed by
            # day_str, and push_to_postgres/push_to_sheets look rows up by this key.
            # Appending the date object silently pushed dates with every value NULL.
            updated_dates.append(day_str)

            row = existing[day_str]
            sm  = int(row.get("sleep_mins") or 0)
            wt  = row.get("weight_kg")
            print(
                f"steps={str(row.get('steps','—')):>6}  "
                f"sleep={sm//60}h{sm%60:02d}m "
                f"({row.get('sleep_start','?')}→{row.get('sleep_end','?')})  "
                f"HR avg={row.get('avg_hr','—')} rest={row.get('resting_hr','—')}  "
                f"weight={wt or '—'}kg  "
                f"water={row.get('water_ml') or '—'}ml"
            )

        time.sleep(1)  # polite delay between days

    if args.dry_run:
        print(f"\n  Dry run complete — garmin_log.csv unchanged.")
        print(f"  If data looks good, run without --dry-run to write it.\n")
    else:
        save_csv(existing)
        print(f"\n✓ {updated} day(s) written to {OUT_CSV.name}")
        if not args.no_db:
            push_to_postgres(existing, updated_dates)
        if args.sheets:
            push_to_sheets(existing, updated_dates, force=args.force)
        print()


if __name__ == "__main__":
    main()
