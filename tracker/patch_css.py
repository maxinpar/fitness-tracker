from pathlib import Path

p = Path(__file__).parent / "templates" / "base.html"
s = p.read_text(encoding="utf-8")
link = "<link rel=\"stylesheet\" href=\"{{ url_for('static', filename='tracker.css') }}\">"
if "week.css" in s:
    print("already linked")
else:
    s = s.replace(
        link,
        link + "\n<link rel=\"stylesheet\" href=\"{{ url_for('static', filename='week.css') }}\">")
    p.write_text(s, encoding="utf-8")
    print("week.css linked:", "week.css" in p.read_text(encoding="utf-8"))
