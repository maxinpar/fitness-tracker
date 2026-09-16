"""Put the week on the home screen: which days are gym days, and what is next."""
from pathlib import Path

here = Path(__file__).parent

# ── the route: build the seven days ──────────────────────────────────────────
app = here / "app.py"
s = app.read_text(encoding="utf-8")

s = s.replace(
    "def sessions_this_week(wk):",
    '''GYM_DAYS = (0, 1, 3)          # Monday, Tuesday, Thursday
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


def sessions_this_week(wk):''')

s = s.replace(
    "    label = next_label(wk)\n    cat = catalogue(wk, label)\n    done = sessions_this_week(wk)",
    "    label = next_label(wk)\n    cat = catalogue(wk, label)\n    done = sessions_this_week(wk)\n"
    "    days = week_days(wk)")

s = s.replace(
    '        label=label, next_session_no=min(done + 1, 3), sessions_done=done,\n'
    '        today=date.today().isoformat())',
    '        label=label, next_session_no=min(done + 1, 3), sessions_done=done,\n'
    '        week_days=days, next_gym=next_gym_day(days),\n'
    '        today=date.today().isoformat())')

app.write_text(s, encoding="utf-8")
import ast
ast.parse(s)
print("app.py: week_days added")

# ── the template: a week strip above the Today card ──────────────────────────
home = here / "templates" / "home.html"
h = home.read_text(encoding="utf-8")

STRIP = '''  {# ── the week ─────────────────────────────────────────────────────────── #}
  {% if week_days %}
  <div class="card blueprint" style="gap:8px">
    <i class="corner tl"></i><i class="corner tr"></i><i class="corner bl"></i><i class="corner br"></i>
    <div class="card-head">
      <span class="card-kicker">This week</span>
      <span class="mono text-muted" style="font-size:12px">
        {{ sessions_done }} of 3 done</span>
    </div>

    <div class="week-strip">
      {% for d in week_days %}
      <div class="wd wd-{{ d.status }}{% if d.is_today %} wd-now{% endif %}">
        <span class="wd-day mono">{{ d.label|upper }}</span>
        <span class="wd-num mono">{{ '%02d'|format(d.day) }}</span>
        <span class="wd-mark">
          {%- if d.status == 'done' %}&check;
          {%- elif d.status == 'missed' %}&times;
          {%- elif d.status == 'golf' %}&bull;
          {%- elif d.gym %}&mdash;
          {%- endif -%}
        </span>
      </div>
      {% endfor %}
    </div>

    <div class="mono text-muted" style="font-size:12px">
      {%- if next_gym and next_gym.is_today -%}
        GYM TODAY &middot; {{ planned|length }} EXERCISES &middot; ~{{ est_minutes }} MIN
      {%- elif next_gym -%}
        NEXT GYM: {{ next_gym.label|upper }} {{ next_gym.day }} &middot;
        {{ planned|length }} EXERCISES &middot; ~{{ est_minutes }} MIN
      {%- else -%}
        NO GYM DAYS LEFT THIS WEEK
      {%- endif -%}
    </div>
    <div class="text-muted" style="font-size:11px">
      Gym Monday, Tuesday, Thursday. Golf at the weekend.</div>
  </div>
  {% endif %}

'''

anchor = '  <div class="card blueprint" style="gap:8px">\n'
i = h.index(anchor, h.index("Weight &middot; 120 days"))
h = h[:i] + STRIP + h[i:]
home.write_text(h, encoding="utf-8")
print("home.html: week strip inserted")
