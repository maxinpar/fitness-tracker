"""Step 2: give Journal, Progress and Settings the data their templates ask for."""
from pathlib import Path

p = Path(__file__).with_name("app.py")
s = p.read_text(encoding="utf-8")

start = s.index('@app.route("/progress")')
end = s.index('@app.route("/checkin"')

NEW = '''@app.route("/progress")
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


'''

s = s[:start] + NEW + s[end:]
p.write_text(s, encoding="utf-8")
import ast
ast.parse(s)
print("step 2 routes written")
