import importlib.util as u
for m in ["flask","psycopg2","garminconnect"]:
    print(m, "OK" if u.find_spec(m) else "MISSING")
