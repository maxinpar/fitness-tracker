"""12-week tracker. Flask + Postgres. Desktop and phone.

Routes feed the Industry-design templates. The contract each template expects is
documented in design_handoff_fitness_tracker/README.md.
"""
import json
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, g, render_template, request, redirect, url_for

import access
import db
import prescriptions

load_dotenv(Path(__file__).with_name(".env"))

app = Flask(__name__)
TARGET_KG = 72.0
START_KG = 77.0
SESSION_NAMES = {"A": "Squat + Pull", "B": "Hinge + Push"}
PHOTOS = Path(__file__).parent / "static" / "exercises"

# Minutes per set. The row is slower than the rest. From the design handover.
PER_SET_ROW = 3.0
PER_SET_OTHER = 2.4


@app.before_request
def require_access():
    """Cloudflare Access when configured, open when it is not. See access.py."""
    if not access.configured():
        return None
    try:
        g.access_email = access.identity(access.token_from(request))
    except access.Denied as denied:
        app.logger.warning("Access denied: %s", denied)
        return Response("Not authorised. Sign in through Cloudflare Access.", 403,
                        {"Content-Type": "text/plain; charset=utf-8"})
    return None


def dm(d):
    """5 Sep. Portable — %-d is Linux only, %#d is Windows only."""
    return f"{d.day} {d:%b}"


def dow(d):
    """Sat 5 Sep."""
    return f"{d:%a} {d.day} {d:%b}"


def slug(name):
    return name.lower().replace(" ", "-").replace("+", "")


def photo_for(name):
    """Find a photo by filename. Drop the file in and it appears."""
    for ext in ("jpg", "jpeg", "png", "webp"):
        f = f"{slug(name)}.{ext}"
        if (PHOTOS / f).exists():
            return f
    return None


def round_load(kg):
    return None if kg is None else round(float(kg) / 2.5) * 2.5


app.jinja_env.filters["dm"] = dm
app.jinja_env.filters["dow"] = dow


# ── data ──────────────────────────────────────────────────────────────────────

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


def catalogue(wk, label=None):
    """Every exercise, flagged planned or not, shaped for log.js.

    Planned rows come from the frozen prescription table, so what a week asked
    for does not change when a reference load is edited later.
    """
    week_no = wk["week_no"] if wk else 1
    label = label if (wk and wk["split"]) else "-"

    presc = {r["exercise_id"]: r for r in db.query(
        "select * from prescription where week_no = %s and session_label = %s "
        "order by sort_order", (week_no, label))}

    pct = wk["load_pct"] if wk else 70
    sets_cap = wk["sets_per_lift"] if wk else 2

    out = []
    for e in db.query("select * from exercise order by sort_order"):
        p = presc.get(e["id"])
        warmup = e["category"] == "warmup"

        if p:
            sets = p["sets"]
            reps = p["default_reps"]
            kg = float(p["kg"]) if p["kg"] is not None else None
        else:
            sets = 1 if warmup else min(e["target_sets"], sets_cap)
            reps = e["default_reps"]
            kg = round_load(float(e["ref_kg"]) * pct / 100) if e["ref_kg"] else None

        out.append({
            "id": e["id"],
            "name": e["name"],
            "category": e["category"],
            "planned": p is not None,
            "sets": sets,
            # The row logs distance and time, not reps and weight.
            "reps": reps if reps is not None else (500 if warmup else 10),
            "kg": kg if kg is not None else (150 if warmup else None),
            "ref": float(e["ref_kg"]) if e["ref_kg"] is not None else None,
            "perSet": PER_SET_ROW if warmup else PER_SET_OTHER,
            "repStep": 100 if warmup else 1,
            "repUnit": "m" if warmup else "reps",
            "kgStep": 5 if warmup else 2.5,
            "kgUnit": "sec" if warmup else "kg",
            "photo": photo_for(e["name"]),
        })
    return out


def est_minutes(cat):
    """Sum over the planned exercises only, the way log.js recomputes it."""
    return round(sum(c["perSet"] * c["sets"] for c in cat if c["planned"]))


def latest_weight():
    rows = db.query("select date, weight_kg from daily where weight_kg is not null "
                    "order by date desc limit 1")
    return rows[0] if rows else None


def last_garmin():
    """The most recent day Garmin filled in. Steps is the marker."""
    rows = db.query("select * from daily where steps is not null order by date desc limit 1")
    if not rows:
        return None, None, None
    row = rows[0]
    return row, row["date"], (date.today() - row["date"]).days


GYM_DAYS = (0, 1, 3)          # Monday, Tuesday, Thursday
GOLF_DAYS = (5, 6)            # Saturday, Sunday


def week_days(wk):
    """The seven days of this week, each one labelled and given a status.

    Gym on Monday, Tuesday and Thursday. Golf at the weekend. A gym day in the
    past with nothing logged is missed, not pending.
    """
    if not wk:
        return []
    start = wk["start_date"]
    today = date.today()
    logged = {r["date"] for r in db.query(
        "select distinct date from gym_session where date >= %s and date <= %s",
        (start, start + timedelta(days=6)))}

    out = []
    for i in range(7):
        d = start + timedelta(days=i)
        gym = i in GYM_DAYS
        if not gym:
            status = "golf" if i in GOLF_DAYS else "rest"
        elif d in logged:
            status = "done"
        elif d < today:
            status = "missed"
        elif d == today:
            status = "today"
        else:
            status = "todo"
        out.append({"label": f"{d:%a}"[:3], "day": d.day, "date": d,
                    "gym": gym, "status": status, "is_today": d == today})
    return out


def next_gym_day(days):
    """The next gym day still to come, or None if the week is spent."""
    for d in days:
        if d["status"] in ("today", "todo"):
            return d
    return None


def sessions_this_week(wk):
    if not wk:
        return 0
    return db.query("select count(*) as n from gym_session where date >= %s and date <= %s",
                    (wk["start_date"], wk["start_date"] + timedelta(days=6)))[0]["n"]


@app.context_processor
def globals_():
    """base.html needs these on every page."""
    return {
        "SESSION_NAMES": SESSION_NAMES,
        "TARGET_KG": TARGET_KG,
        "start": START_KG,
        "wk": current_week(),
        "today_label": dow(date.today()),
        "toast": request.args.get("toast"),
    }


# ── routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    wk = current_week()
    weight = latest_weight()
    garmin, sync_date, sync_age = last_garmin()

    trend = [(dm(r["date"]), float(r["weight_kg"])) for r in db.query(
        "select date, weight_kg from daily where weight_kg is not null and date >= %s "
        "order by date", (date.today() - timedelta(days=120),))]
    weight_line = f"{trend[0][1]:.1f} → {trend[-1][1]:.1f}" if len(trend) > 1 else ""

    # On track against this week's target. None before there is anything to judge.
    on_track = None
    if weight and wk:
        on_track = float(weight["weight_kg"]) <= float(wk["target_weight_kg"]) + 0.3

    label = next_label(wk)
    cat = catalogue(wk, label)
    done = sessions_this_week(wk)
    days = week_days(wk)

    return render_template(
        "home.html",
        weight=weight, trend=trend, weight_line=weight_line, on_track=on_track,
        garmin=garmin, sync_date=sync_date, sync_age=sync_age,
        planned=[c for c in cat if c["planned"]], est_minutes=est_minutes(cat),
        label=label, next_session_no=min(done + 1, 3), sessions_done=done,
        week_days=days, next_gym=next_gym_day(days),
        today=date.today().isoformat())


@app.route("/weigh", methods=["POST"])
def weigh():
    raw = request.form.get("weight_kg", "").strip()
    try:
        kg = float(raw)
    except ValueError:
        return redirect(url_for("home", toast="Enter a weight in kg."))
    if not 40 <= kg <= 200:
        return redirect(url_for("home", toast="Enter a weight in kg."))

    db.execute("insert into daily (date, weight_kg) values (%s, %s) "
               "on conflict (date) do update set weight_kg = excluded.weight_kg",
               (date.today(), kg))
    return redirect(url_for(
        "home", toast=f"Logged {kg:.1f} kg — {kg - TARGET_KG:.1f} kg to target."))


@app.route("/log")
def log_form():
    wk = current_week()
    label = request.args.get("label") or next_label(wk)
    cat = catalogue(wk, label)
    return render_template(
        "log.html",
        planned=[c for c in cat if c["planned"]],
        catalogue_json=json.dumps(cat),
        est_minutes=est_minutes(cat),
        label=label, today=date.today().isoformat())


@app.route("/log", methods=["POST"])
def log_save():
    """log.js posts reps_<id>_<n> / kg_<id>_<n>, the same names the old form used."""
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
                   "values (%s,%s,%s,%s,%s) on conflict do nothing",
                   (sid, int(ex_id), int(set_no), int(float(reps)),
                    float(kg) if kg else None))
        saved += 1

    if not saved:
        db.execute("delete from gym_session where id = %s", (sid,))
        return redirect(url_for("log_form", toast="Nothing to save."))
    return redirect(url_for("journal", toast=f"Session saved — {saved} sets."))


@app.route("/plan")
def programme():
    """Two tables: the blocks, then the catalogue."""
    wk = current_week()
    rows = db.query("select * from plan order by week_no")

    blocks, order = {}, []
    for r in rows:
        b = r["block"]
        if b not in blocks:
            blocks[b] = {"block": b, "weeks": [], "sets": set(), "load": [],
                         "time": set(), "exercises": set(), "current": False}
            order.append(b)
        g_ = blocks[b]
        g_["weeks"].append(r["week_no"])
        g_["sets"].add(r["sets_per_lift"])
        g_["load"].append(r["load_pct"])
        g_["time"].add(r["est_minutes"])
        g_["exercises"].add(db.query(
            "select count(*) as n from exercise where from_week <= %s",
            (r["max_from_week"],))[0]["n"])
        if wk and r["week_no"] == wk["week_no"]:
            g_["current"] = True

    def span(values):
        lo, hi = min(values), max(values)
        return f"{lo}" if lo == hi else f"{lo}–{hi}"

    out = []
    for b in order:
        g_ = blocks[b]
        out.append({
            "block": b,
            "weeks": span(g_["weeks"]),
            "exercises": span(sorted(g_["exercises"])),
            "sets": span(sorted(g_["sets"])),
            "load": span(g_["load"]) + "%",
            "time": "~" + span(sorted(g_["time"])) + " min",
            "current": g_["current"],
        })

    return render_template("plan.html", blocks=out,
                           catalogue=db.query("select * from exercise order by sort_order"))


# ── step 2: these still serve the old data shape ─────────────────────────────
# Progress, Journal and Settings have new templates but old routes. They render
# without error; they do not yet show everything the design asks for.

@app.route("/progress")
def progress():
    wk = current_week()

    actual = [(dm(r["date"]), float(r["weight_kg"])) for r in db.query(
        "select date, weight_kg from daily where weight_kg is not null order by date")]

    # The glide path: each remaining week's target, ending at 72.0 on 6 Dec.
    plan_points = [(dm(r["start_date"] + timedelta(days=6)), float(r["target_weight_kg"]))
                   for r in db.query("select * from plan where week_no >= %s order by week_no",
                                     (wk["week_no"] if wk else 1,))]

    # Load actually lifted against what the week asked for.
    load_pct_actual, load_note = None, "No sets logged this week yet."
    if wk:
        rows = db.query(
            "select l.kg as done, p.kg as asked from set_log l "
            "join gym_session s on s.id = l.session_id "
            "join prescription p on p.exercise_id = l.exercise_id and p.week_no = s.week_no "
            "where s.date >= %s and l.kg is not null and p.kg is not null and p.kg > 0",
            (wk["start_date"],))
        if rows:
            ratio = sum(float(r["done"]) / float(r["asked"]) for r in rows) / len(rows)
            load_pct_actual = round(ratio * 100)
            load_note = f"Across {len(rows)} logged sets this week."

    # Is each lift going up?
    presc = {r["exercise_id"]: r for r in db.query(
        "select * from prescription where week_no = %s and session_label = %s",
        (wk["week_no"] if wk else 1, next_label(wk) or "-"))}
    history = {}
    for r in db.query(
            "select l.exercise_id, s.date, l.kg, l.reps from set_log l "
            "join gym_session s on s.id = l.session_id "
            "where l.kg is not null order by s.date"):
        history.setdefault(r["exercise_id"], []).append(r)

    lift_rows = []
    for e in db.query("select * from exercise order by sort_order"):
        pr = presc.get(e["id"])
        if pr:
            plan = f"{pr['sets']} × {pr['reps']}" + (f" · {pr['kg']:g} kg" if pr["kg"] else "")
        else:
            plan = f"from week {e['from_week']}"
        h = history.get(e["id"], [])
        last = f"{float(h[-1]['kg']):g} kg" if h else "—"
        best = f"{max(float(x['kg']) for x in h):g} kg" if h else "—"
        lift_rows.append({"name": e["name"], "plan": plan, "last": last, "best": best})

    # Photo weeks. Max copies the files in; the app only lines them up.
    shots = Path(__file__).parent / "static" / "progress"
    photo_weeks = []
    for w in (1, 4, 8, 12):
        row = db.query("select start_date from plan where week_no = %s", (w,))
        due = dm(row[0]["start_date"] + timedelta(days=6)) if row else ""
        have = any((shots / f"wk{w:02d}.{x}").exists() for x in ("jpg", "jpeg", "png", "webp"))
        photo_weeks.append({"week": w, "have": have, "due": due})

    return render_template(
        "progress.html", actual=actual, plan_points=plan_points,
        sessions_done=sessions_this_week(wk), load_pct_actual=load_pct_actual,
        load_note=load_note, lift_rows=lift_rows, photo_weeks=photo_weeks)


@app.route("/journal")
def journal():
    days = db.query(
        "select d.date, d.weight_kg, d.steps, d.sleep_mins, d.water_ml, d.resting_hr, "
        "       s.id as session_id, s.label, s.notes "
        "from daily d left join gym_session s on s.date = d.date "
        "where d.date >= %s order by d.date desc", (date.today() - timedelta(days=60),))

    lifts = db.query(
        "select s.date, e.name, count(*) as sets, max(l.kg) as top_kg "
        "from set_log l join gym_session s on s.id = l.session_id "
        "join exercise e on e.id = l.exercise_id "
        "group by s.date, e.name, e.sort_order order by s.date desc, e.sort_order")
    by_date = {}
    for r in lifts:
        by_date.setdefault(r["date"], []).append(r)

    today = date.today()
    for d in days:
        if d["session_id"]:
            d["tag"] = SESSION_NAMES.get(d["label"], "Full-body")
            parts = [f"{x['name']} {x['sets']}×" + (f"{float(x['top_kg']):g} kg"
                                                    if x["top_kg"] else "bodyweight")
                     for x in by_date.get(d["date"], [])]
            if d["notes"]:
                parts.append(d["notes"])
            d["detail"] = " · ".join(parts)
        else:
            wd = d["date"].weekday()
            if wd in GYM_DAYS and d["date"] < today:
                d["tag"], d["detail"] = "Missed", ""
            elif wd in GOLF_DAYS:
                d["tag"], d["detail"] = "Weekend", ""
            else:
                d["tag"], d["detail"] = "Rest", ""
    return render_template("journal.html", days=days)


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
        # Past weeks keep what they asked for; future weeks pick up the new load.
        wk = current_week()
        prescriptions.generate(wk["week_no"] if wk else 1)
        return redirect(url_for("settings", toast="Defaults saved."))

    lifts = db.query("select * from exercise order by sort_order")
    for l in lifts:
        l["photo"] = photo_for(l["name"])
        l["slug"] = slug(l["name"])
    _, sync_date, sync_age = last_garmin()

    targets = [
        {"label": "Target weight", "value": f"{TARGET_KG:.1f} kg by 6 Dec 2026"},
        {"label": "Steps per day", "value": "9,000"},
        {"label": "Protein per day", "value": "130–140 g"},
        {"label": "Eating window", "value": "12:00 – 20:00"},
        {"label": "Alcohol per week", "value": "4 standard drinks, none Mon–Thu"},
        {"label": "Session ceiling", "value": "45 minutes"},
    ]
    return render_template("settings.html", lifts=lifts, targets=targets,
                           sync_date=sync_date, sync_age=sync_age)


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
        return redirect(url_for("home", toast="Check-in saved."))

    return render_template("checkin.html",
                           past=db.query("select * from weekly order by week_no desc limit 12"),
                           done=sessions_this_week(wk))


if __name__ == "__main__":
    # DEBUG IS OFF WHENEVER ACCESS IS CONFIGURED. The Werkzeug debugger hands an
    # interactive Python console to anyone who can reach a traceback; behind a
    # public hostname that is a way in, whatever gate sits in front of it.
    debug = not access.configured() and os.environ.get("APP_DEBUG", "1") != "0"
    app.run(host="0.0.0.0", port=5055, debug=debug)
