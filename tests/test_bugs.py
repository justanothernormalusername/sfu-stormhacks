"""Bugs a happy-path test never reaches.

Each case works on the first try and breaks on the second, or breaks when two
requests race. `raise_server_exceptions=False` is the point: it turns an
unhandled exception into a 500 the way a real client would see it, instead of
re-raising inside the test.

    PYTHONPATH=. .venv/bin/python bug_hunt.py
"""

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/bugs.db"
os.environ["SECRET_KEY"] = "x"

from fastapi.testclient import TestClient  # noqa: E402

from src.app.db import init_db  # noqa: E402
from src.app.main import app  # noqa: E402

init_db()
c = TestClient(app, raise_server_exceptions=False)
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name} {detail if not ok else ''}")
    if not ok:
        failures.append(name)


def login(name: str) -> None:
    c.post("/login", data={"username": name, "password": "hunter22",
                           "action": "register"})


def fight_to_end(index: int):
    r = c.post(f"/api/rooms/{index}/enter")
    if r.status_code != 200:
        return None
    f = r.json()["fight"]
    for _ in range(400):
        if f["state"] != "fight":
            return f
        x = c.post(f"/api/rooms/{index}/act",
                   json={"action": "power" if f["power_cd"] == 0 else "attack"})
        if x.status_code != 200:
            return None
        f = x.json()["fight"]
    return f


def clear_everything() -> None:
    """Beat the whole floor so every room, including the shrine, is reachable."""
    for _ in range(4):
        progressed = False
        for r in c.get("/api/rooms").json()["rooms"]:
            if r["safe"] or r["cleared"]:
                continue
            f = fight_to_end(r["index"])
            if f and f["state"] == "won":
                progressed = True
        if not progressed:
            return


print("\n=== 1. Using the shrine twice must not 500 ===")
login("shrine")
clear_everything()
floor = c.get("/api/rooms").json()
shrine = next(r for r in floor["rooms"] if r["safe"] and r.get("restore"))
check("shrine is reachable once the floor is cleared", not shrine["blocked"])
r1 = c.post(f"/api/rooms/{shrine['index']}/enter")
check("first rest succeeds", r1.status_code == 200, f"got {r1.status_code}")
r2 = c.post(f"/api/rooms/{shrine['index']}/enter")
# BattleClear has a unique constraint on (user, week, room), so a second shrine
# insert violates it. Unhandled, that surfaces as a 500, not a clean 409.
check("second rest is refused cleanly, not a 500",
      r2.status_code == 409, f"got {r2.status_code} {r2.text[:140]}")

print("\n=== 2. Acting on a room never entered is refused, not a 500 ===")
login("ghost")
r = c.post("/api/rooms/5/act", json={"action": "attack"})
check("act with no fight is a clean 409", r.status_code == 409,
      f"got {r.status_code} {r.text[:140]}")

print("\n=== 3. Out-of-range room indices ===")
login("range")
for bad in (-1, 999):
    r = c.post(f"/api/rooms/{bad}/enter")
    check(f"enter room {bad} is 404 not 500", r.status_code == 404,
          f"got {r.status_code}")
    r = c.post(f"/api/rooms/{bad}/act", json={"action": "attack"})
    check(f"act in room {bad} is 404 not 500", r.status_code == 404,
          f"got {r.status_code}")

print("\n=== 4. Fleeing gives the fight back with no clear recorded ===")
login("flee")
floor = c.get("/api/rooms").json()
room = next(r for r in floor["rooms"] if not r["safe"] and not r["blocked"])
c.post(f"/api/rooms/{room['index']}/enter")
c.post(f"/api/rooms/{room['index']}/act", json={"action": "flee"})
after = c.get("/api/rooms").json()["rooms"][room["index"]]
check("fleeing does not mark the room cleared", not after["cleared"])
again = c.post(f"/api/rooms/{room['index']}/enter")
check("a fled room can be re-entered", again.status_code == 200,
      f"got {again.status_code} {again.text[:140]}")

print("\n=== 5. Two rooms' fights do not collide ===")
login("tworooms")
floor = c.get("/api/rooms").json()
open_rooms = [r for r in floor["rooms"] if not r["safe"] and not r["blocked"]]
a, b = open_rooms[0], open_rooms[1]
c.post(f"/api/rooms/{a['index']}/enter")
c.post(f"/api/rooms/{b['index']}/enter")
fa = c.post(f"/api/rooms/{a['index']}/act", json={"action": "attack"}).json()["fight"]
fb = c.post(f"/api/rooms/{b['index']}/act", json={"action": "attack"}).json()["fight"]
check("room A's fight is independent of room B",
      fa["room_index"] == a["index"] and fb["room_index"] == b["index"],
      f"got {fa['room_index']}, {fb['room_index']}")
check("each fight advances on its own turn counter",
      fa["turn"] == 2 and fb["turn"] == 2, f"{fa['turn']}, {fb['turn']}")

print("\n=== 6. Weekly reset drops in-progress fights ===")
from datetime import datetime  # noqa: E402

from src.app.routes import api as api_mod  # noqa: E402

user_stub = type("U", (), {"id": 1})()
check("fight keys differ across weeks",
      api_mod._fight_key(user_stub, 1, datetime(2026, 10, 5))
      != api_mod._fight_key(user_stub, 1, datetime(2026, 10, 12)))

print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {failures}")
    raise SystemExit(1)
print("No bugs found.")