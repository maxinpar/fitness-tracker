"""Stop /progress 500-ing. Full progress data is step 2."""
from pathlib import Path

p = Path(__file__).with_name("app.py")
s = p.read_text(encoding="utf-8")

s = s.replace(
    '    return render_template("progress.html", weight=weight, by_lift=by_lift)',
    '''    wk = current_week()
    return render_template(
        "progress.html", weight=weight, by_lift=by_lift,
        sessions_done=sessions_this_week(wk), target=TARGET_KG, start=START_KG)''')

p.write_text(s, encoding="utf-8")
import ast
ast.parse(s)
print("patched")
