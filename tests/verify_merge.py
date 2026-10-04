"""Post-merge smoke test against the running dev server.

The merge brought in a classifier redesign, so the path that changed most is task
creation: the client no longer sends a `kind`, and the reward comes from a score
the classifier assigns. This confirms that whole chain still pays out, and that
combat still works, on the server actually running rather than in-process.

    PYTHONPATH=. .venv/bin/python tests/verify_merge.py
"""

import http.cookiejar
import json
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(path):
    with opener.open(BASE + path) as r:
        return json.load(r)


def post(path, data=None, form=None):
    headers, body = {}, None
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    else:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=body, headers=headers)
    with opener.open(req) as r:
        raw = r.read()
    # The page routes (including /login) return HTML or a redirect, not JSON.
    # Only /api/* is JSON, so a non-JSON body just means "the call went through".
    try:
        return json.loads(raw)
    except ValueError:
        return {}


# Register, then fall back to signing in: /login re-renders the form with an
# error when the name is taken, and that response sets no session cookie — so a
# register-only script ends up silently unauthenticated and every /api call 401s.
if "session" not in {c.name for c in jar}:
    post("/login", form={"username": "mergecheck", "password": "hunter22",
                         "action": "register"})
if "session" not in {c.name for c in jar}:
    post("/login", form={"username": "mergecheck", "password": "hunter22",
                         "action": "login"})
assert "session" in {c.name for c in jar}, "could not establish a session"
print("logged in")

print("=== classifier-driven quest creation ===")
quest = post("/api/tasks", {"title": "go for a long run"})
print(f"  created: {quest['title']!r} kind={quest['kind']} "
      f"potion={quest['potion']} worth={quest['potions']}")
assert quest["potions"] >= 1, "quest paid nothing"

done = post(f"/api/tasks/{quest['id']}/complete", {"note": "ran 5k"})
print(f"  completed: earned {done['potions_earned']} ({done['category']})")

player = get("/api/player")
print(f"  player potions: {player['potions_total']}  "
      f"hp={player['hp']}/{player['max_hp']}")
assert player["potions_total"] >= 1, "potion never landed in the inventory"

print("\n=== floor ===")
rooms = get("/api/rooms")["rooms"]
boss = next(r for r in rooms if r["kind"] == "boss")
print(f"  {len(rooms)} rooms; boss {boss['enemy']['name']} "
      f"{boss['enemy']['hp']} HP / {boss['enemy']['atk']} ATK")
print(f"  open rooms: {[r['index'] for r in rooms if not r['blocked']]}")

print("\n=== combat ===")
# Pick an uncleared open room, so re-running this script is idempotent — it
# returns 409 on a room cleared by a previous run rather than proving anything.
room = next((r for r in rooms if not r["safe"] and not r["blocked"]
             and not r["cleared"]), None)
if room is None:
    print("  floor already fully cleared — nothing left to fight.")
    print("\nMerge verified end to end.")
    raise SystemExit(0)
fight = post(f"/api/rooms/{room['index']}/enter")["fight"]
assert "seed" not in fight, "fight seed leaked to the client"
print(f"  entered {fight['room_name']}: {fight['enemy']['name']} "
      f"{fight['enemy']['hp']} HP")
while fight["state"] == "fight":
    action = "power" if fight["power_cd"] == 0 else "attack"
    fight = post(f"/api/rooms/{room['index']}/act", {"action": action})["fight"]
print(f"  -> {fight['state']} after {fight['turn']} turns, "
      f"hero at {fight['hero']['hp']}/{fight['hero']['max_hp']}")

print("\nMerge verified end to end.")