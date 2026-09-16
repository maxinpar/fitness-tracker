"""What each template actually asks for. Read the contract, do not guess it."""
import re
from pathlib import Path

KNOWN = {"loop", "url_for", "request", "range", "dict", "SESSION_NAMES", "TARGET_KG",
         "start", "wk", "today_label", "toast", "self", "true", "false", "none"}

for name in ("journal.html", "progress.html", "settings.html", "session.html", "checkin.html"):
    p = Path(__file__).parent / "templates" / name
    src = p.read_text(encoding="utf-8")

    local = set(re.findall(r"{%-?\s*(?:for|set)\s+([a-zA-Z_][\w]*)", src))
    local |= set(re.findall(r"{%-?\s*for\s+\w+\s*,\s*([a-zA-Z_][\w]*)", src))

    used = set()
    for expr in re.findall(r"{{(.*?)}}|{%-?(.*?)-?%}", src, re.S):
        for part in expr:
            for m in re.findall(r"\b([a-zA-Z_][\w]*)\b(\.\w+)?", part):
                used.add(m[0])

    need = sorted(v for v in used - local - KNOWN if not v.islower() or True)
    need = [v for v in need if v not in {
        "if", "endif", "for", "endfor", "else", "elif", "in", "is", "not", "and", "or",
        "block", "endblock", "extends", "from", "import", "with", "set", "macro",
        "endmacro", "length", "format", "float", "int", "round", "min", "max", "upper",
        "lower", "join", "default", "safe", "map", "list", "attribute", "sort", "dm",
        "dow", "title", "body", "scripts", "head", "abs", "string", "trim", "replace",
        "selectattr", "sum", "tojson", "truncate", "first", "last", "reverse", "none",
        "enumerate", "items", "keys", "values", "get", "strftime", "count", "filter"}]
    # Only report things that look like data the route must pass.
    print(f"=== {name}")
    print("   ", ", ".join(need) if need else "(nothing)")
    print()
