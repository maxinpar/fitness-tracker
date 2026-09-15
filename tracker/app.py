"""12-week tracker. Flask + Postgres. Phone and laptop."""
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, g, render_template, request, redirect, url_for

import access
import db

# Read .env before anything asks the environment a question.
load_dotenv(Path(__file__).with_name(".env"))

app = Flask(__name__)
TARGET_KG = 72.0
START_KG = 78.0
SESSION_NAMES = {"A": "Squat + Pull", "B": "Hinge + Push"}
PHOTOS = Path(__file__).parent / "static" / "exercises"


@app.before_request
def require_access():
    """The gate. Cloudflare Access when configured, open when it is not.

    Set CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD and every request must carry a
    token this app has verified itself — see access.py for why the header is
    verified rather than trusted, and why localhost gets no exemption. Leave
    them unset and the tracker is open on the LAN, as it was before the tunnel.
    """
    if not access.configured():
        return None
    try:
        g.access_email = access.identity(access.token_from(request))
    except access.Denied as denied:
        # The reason goes to the log, not to the browser: "that email is not on
        # the allow-list" tells whoever is trying exactly what to forge next.
        app.logger.warning("Access denied: %s", denied)
        return Response(
            "Not authorised. Sign in through Cloudflare Access.",
            403,
            {"Content-Type": "text/plain; charset=utf-8"},
        )
    return None


# ── helpers ───────────────────────────────────────────────────────────────────

def dm(d):
    """5 Sep. Portable — %-d is Linux only, %#d is Windows only."""
    return f"{d.day} {d:%b}"


def dow(d):
    """Sat 5 Sep."""
    return f"{d:%a} {d.day} {d:%b}"


def slug(name):
    return name.lower().replace(" ", "-").replace("+", "")


def photo_for(name):
    """Find a photo by filename. Drop the file in and it appears — no database edit."""
    for ext in ("jpg", "jpeg", "png", "webp"):
        f = f"{slug(name)}.{ext}"
        if (PHOTOS / f).exists():
            return f
    return None


def round_load(kg):
    """Round a suggested load to the nearest 2.5 kg."""
    return None if kg is None else round(float(kg) / 2.5) * 2.5


def current_week(on=None):
    """The plan row covering a date, or None outside the programme."""
    on = on or date.today()
    rows = db.query("select * from plan where start_date <= %s order by week_no desc limit 1", (on,))
    if not rows:
        return None
    wk = rows[0]
    if on > wk["start_date"] + timedelta(days=6) and wk["week_no"] == 12:
        return None
    return wk


def next_label(wk):
    """Which half is due. Only meaningful from week 9, when the plan splits."""
    if not wk or not wk["split"]:
        return None
    rows = db.query("select label from gym_session where label in ('A','B') "
                    "order by date desc, id desc limit 1")
    return "B" if rows and rows[0]["label"] == "A" else "A"


def todays_lifts(wk, label=None):
    """Planned exercises, plus everything else offered as an extra.

    Before week 9 the plan is full body, so session_label is ignored entirely.
    That is the bug that hid Cable Chest Press in week 1.
    """
    max_week = wk["max_from_week"] if wk else 1
    sets = wk["sets_per_lift"] if wk else 2
    pct = wk["load_pct"] if wk else 70
    split = bool(wk and wk["split"])

    rows = db.query("select * from exercise order by sort_order")
    planned, extra = [], []
    for r in rows:
        r["photo"] = photo_for(r["name"])
        r["suggested_kg"] = round_load(float(r["ref_kg"]) * pct / 100) if r["ref_kg"] else None
        r["sets"] = 1 if r["category"] == "warmup" else min(r["target_sets"], sets)
        in_plan = r["from_week"] <= max_week
        if in_plan and split and label and r["session_label"] not in (label, "BOTH"):
            in_plan = False
        (planned if in_plan else extra).append(r)
    return planned, extra


def latest_weight():
    rows = db.query("select date, weight_kg from daily where weight_kg is not null "
                    "order by date desc limit 1")
    return rows[0] if rows else None


def last_garmin_sync():
    """
    The most recent day Garmin actually filled in. Steps is the marker: Garmin
    always sets it, whereas weight can arrive from a manual check-in.
    Returns (date, days_ago) or (None, None) if Garmin has never written.
    """
    rows = db.query("select max(date) as last from daily where steps is not null")
    last = rows[0]["last"] if rows else None
    return last, ((date.today() - last).days if last else None)


app.jinja_env.filters["dm"] = dm
app.jinja_env.filters["dow"] = dow


@app.context_processor
def globals_():
    return {"SESSION_NAMES": SESSION_NAMES, "TARGET_KG": TARGET_KG}


# ── routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    wk = current_week()
    weight = latest_weight()
    sync_date, sync_age = last_garmin_sync()
    trend = [(dm(r["date"]), float(r["weight_kg"])) for r in db.query(
        "select date, weight_kg from daily where weight_kg is not null and date >= %s "
        "order by date", (date.today() - timedelta(days=120),))]
    done = db.query("select id, date, label from gym_session where date >= %s order by date",
                    (wk["start_date"] if wk else date.today(),))
    label = next_label(wk)
    planned, _ = todays_lifts(wk, label)
    return render_template("home.html", wk=wk, weight=weight, trend=trend, done=done,
                           label=label, planned=planned, start=START_KG,
                           sync_date=sync_date, sync_age=sync_age,
                           today=date.today().isoformat())


@app.route("/weigh", methods=["POST"])
def weigh():
    kg = request.form.get("weight_kg", "").strip()
    if kg:
        db.execute("insert into daily (date, weight_kg) values (%s, %s) "
                   "on conflict (date) do update set weight_kg = excluded.weight_kg",
                   (request.form.get("date") or date.today(), float(kg)))
    return redirect(url_for("home"))


@app.route("/log")
def log_form():
    wk = current_week()
    label = request.args.get("label") or next_label(wk)
    planned, extra = todays_lifts(wk, label)
    minutes = round(sum(float(l["est_minutes"] or 0) *
                        (l["sets"] / max(l["target_sets"], 1) if l["category"] != "warmup" else 1)
                        for l in planned))
    return render_template("log.html", wk=wk, label=label, planned=planned, extra=extra,
                           minutes=minutes, today=date.today().isoformat())


@app.route("/log", methods=["POST"])
def log_save():
    wk = current_week()
    sid = db.execute(
        "insert into gym_session (date, label, week_no, notes) values (%s,%s,%s,%s) returning id",
        (request.form["date"], request.form.get("label") or "-",
         wk["week_no"] if wk else None, request.form.get("notes") or None), returning=True)

    saved = 0
    for key, reps in request.form.items():
        if not key.startswith("reps_") or not reps.strip():
            continue
        _, ex_id, set_no = key.split("_")
        kg = request.form.get(f"kg_{ex_id}_{set_no}", "").strip()
        db.execute("insert into set_log (session_id, exercise_id, set_no, reps, kg) "
                   "values (%s,%s,%s,%s,%s)",
                   (sid, int(ex_id), int(set_no), int(reps), float(kg) if kg else None))
        saved += 1
    if not saved:
        db.execute("delete from gym_session where id = %s", (sid,))
        return redirect(url_for("log_form"))
    return redirect(url_for("journal"))


@app.route("/progress")
def progress():
    weight = [(dm(r["date"]), float(r["weight_kg"])) for r in db.query(
        "select date, weight_kg from daily where weight_kg is not null order by date")]
    lifts = db.query("""
      select e.name, s.date, max(l.kg) as top_kg
      from set_log l
      join gym_session s on s.id = l.session_id
      join exercise e on e.id = l.exercise_id
      where l.kg is not null
      group by e.name, e.sort_order, s.date
      order by e.sort_order, s.date""")
    by_lift = {}
    for r in lifts:
        by_lift.setdefault(r["name"], []).append((dm(r["date"]), float(r["top_kg"])))
    return render_template("progress.html", weight=weight, by_lift=by_lift, start=START_KG)


@app.route("/journal")
def journal():
    days = db.query("""
      select d.date, d.weight_kg, d.steps, d.sleep_mins, d.water_ml, d.resting_hr,
             s.id as session_id, s.label
      from daily d
      left join gym_session s on s.date = d.date
      where d.date >= %s
      order by d.date desc""", (date.today() - timedelta(days=60),))
    lifts = db.query("""
      select s.date, e.name, count(*) as sets,
             max(l.kg) as top_kg, max(l.reps) as top_reps
      from set_log l
      join gym_session s on s.id = l.session_id
      join exercise e on e.id = l.exercise_id
      group by s.date, e.name, e.sort_order order by s.date desc, e.sort_order""")
    by_date = {}
    for r in lifts:
        by_date.setdefault(r["date"], []).append(r)
    return render_template("journal.html", days=days, by_date=by_date)


@app.route("/session/<int:sid>")
def session_detail(sid):
    head = db.query("select * from gym_session where id = %s", (sid,))
    rows = db.query("select e.name, l.set_no, l.reps, l.kg from set_log l "
                    "join exercise e on e.id = l.exercise_id "
                    "where l.session_id = %s order by e.sort_order, l.set_no", (sid,))
    return render_template("session.html", head=head[0] if head else None, rows=rows)


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        for key, val in request.form.items():
            if not key.startswith("ref_"):
                continue
            ex_id = int(key.split("_")[1])
            reps = request.form.get(f"reps_{ex_id}", "").strip()
            db.execute("update exercise set ref_kg = %s, default_reps = %s where id = %s",
                       (float(val) if val.strip() else None,
                        int(reps) if reps else None, ex_id))
        return redirect(url_for("settings"))
    lifts = db.query("select * from exercise order by sort_order")
    for l in lifts:
        l["photo"] = photo_for(l["name"])
        l["slug"] = slug(l["name"])
    return render_template("settings.html", lifts=lifts)


@app.route("/checkin", methods=["GET", "POST"])
def checkin():
    wk = current_week()
    if request.method == "POST":
        db.execute(
            "insert into weekly "
            "(week_no, start_date, weight_kg, sleep_quality, alcohol_units, sessions_done, notes) "
            "values (%s,%s,%s,%s,%s,%s,%s) "
            "on conflict (week_no) do update set "
            "  weight_kg = excluded.weight_kg, sleep_quality = excluded.sleep_quality, "
            "  alcohol_units = excluded.alcohol_units, sessions_done = excluded.sessions_done, "
            "  notes = excluded.notes",
            (int(request.form["week_no"]), request.form["start_date"] or None,
             request.form["weight_kg"] or None, request.form["sleep_quality"] or None,
             request.form["alcohol_units"] or None, request.form["sessions_done"] or None,
             request.form.get("notes") or None))
        if request.form["weight_kg"]:
            db.execute("insert into daily (date, weight_kg) values (%s, %s) "
                       "on conflict (date) do update set weight_kg = excluded.weight_kg",
                       (date.today(), float(request.form["weight_kg"])))
        return redirect(url_for("home"))

    past = db.query("select * from weekly order by week_no desc limit 12")
    done = db.query("select count(*) as n from gym_session where date >= %s",
                    (wk["start_date"],))[0]["n"] if wk else 0
    return render_template("checkin.html", wk=wk, past=past, done=done)


if __name__ == "__main__":
    # 0.0.0.0 so the phone can reach it on the home Wi-Fi, and so cloudflared
    # can reach it when the tunnel is running.
    #
    # DEBUG IS OFF WHENEVER ACCESS IS CONFIGURED, and that is not a preference.
    # Werkzeug's debugger hands an interactive Python console to anyone who can
    # reach a traceback; behind a hostname on the public internet that is a way
    # in, whatever the gate in front of it says. Unset CF_ACCESS_AUD for local
    # work and the debugger comes back.
    debug = not access.configured() and os.environ.get("APP_DEBUG", "1") != "0"
    app.run(host="0.0.0.0", port=5055, debug=debug)
