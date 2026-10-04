"""End-to-end check of the server-authoritative rewrite.

Runs against the real app with a real (temp) database, driving the same HTTP
calls the browser makes. The point is not unit coverage of game.fight_step —
tools/balance.py covers that — but proving the wiring: that a client cannot
claim HP it did not earn, that progress is gated on reachability, and that a
fight can actually be won through the API.
"""

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["SECRET_KEY"] = "test-secret"

from fastapi.testclient import TestClient  # noqa: E402

from src.app.db import init_db  # noqa: E402
from src.app.main import app  # noqa: E402
from src.app.routes.api import enterable_rooms, walkable_rooms  # noqa: E402

# init_db() is wired to the startup event, which TestClient only fires when used
# as a context manager. Calling it directly keeps these tests as plain top-level
# calls, which is what makes them readable.
init_db()

client = TestClient(app)
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        failures.append(name)


def login(username: str) -> None:
    # Auth is a form POST to /login (routes/pages.py), not a JSON API — an
    # `action` of "register" creates the account, then the cookie carries the
    # session for every /api/* call below.
    client.post("/login", data={"username": username, "password": "hunter22",
                                "action": "register"})


def logout() -> None:
    client.get("/logout")


def fight_room(index: int, limit: int = 250):
    """Enter a room and attack until it resolves, exactly as the UI would."""
    entered = client.post(f"/api/rooms/{index}/enter")
    if entered.status_code != 200:
        return entered, None
    fight = entered.json()["fight"]
    last = None
    turns = 0
    while fight["state"] == "fight" and turns < limit:
        body = {"action": "power" if fight["power_cd"] == 0 else "attack"}
        last = client.post(f"/api/rooms/{index}/act", json=body)
        if last.status_code != 200:
            return last, fight
        fight = last.json()["fight"]
        turns += 1
    return last, fight


print("\n=== 1. The exploit that motivated this is closed ===")
login("exploiter")
floor = client.get("/api/rooms").json()
rooms = floor["rooms"]
boss = next(r for r in rooms if r["kind"] == "boss")

# The old endpoint accepted an arbitrary hp. It should not exist at all.
r = client.post(f"/api/rooms/{boss['index']}/clear", json={"hp": 999})
check("POST /clear (the exploit) is gone", r.status_code == 404, f"got {r.status_code}")

r = client.post(f"/api/rooms/{boss['index']}/enter", json={"hp": 999})
check("enter ignores a forged hp in the body", r.status_code in (403, 409),
      f"got {r.status_code} {r.text[:120]}")

print("\n=== 2. The dungeon is gated, not a menu ===")
check("entrance is never blocked", rooms[0]["blocked"] is False)
check("rooms behind uncleared doors start blocked", any(r["blocked"] for r in rooms[1:]))
# The entrance is safe, so it can never be "cleared" — a naive flood fill that
# requires cleared rooms would seal the entire floor. Check the walkable set
# actually grows as fights are won.
before = walkable_rooms(floor, set())
after = walkable_rooms(floor, {0, 3})
check("clearing a room opens more of the floor", len(after) > len(before),
      f"{len(before)} -> {len(after)}")
check("the floor is completable", len(walkable_rooms(floor, set(range(len(rooms)))))
      == len(rooms))
check("blocked rooms are exactly the ones entry refuses",
      {r["index"] for r in rooms if r["blocked"]} == set(range(len(rooms))) - enterable_rooms(floor, set()))

print("\n=== 3. A room you cannot reach cannot be entered ===")
far = next(r for r in rooms if r["blocked"])
r = client.post(f"/api/rooms/{far['index']}/enter")
check("entering a sealed room is refused", r.status_code == 403, f"got {r.status_code}")
near = next(r for r in rooms if not r["safe"] and not r["blocked"])
r = client.post(f"/api/rooms/{near['index']}/enter")
check("entering the first reachable room is allowed", r.status_code == 200, f"got {r.status_code}")

print("\n=== 4. A fight can be won, and the win is the server's number ===")
login("fighter")
rooms = client.get("/api/rooms").json()["rooms"]
first = next(r for r in rooms if not r["safe"] and not r["blocked"])

entered = client.post(f"/api/rooms/{first['index']}/enter").json()
check("enter returns a fight", entered["fight"]["state"] == "fight")
check("the fight seed is not sent to the client", "seed" not in entered["fight"])

last, fight = fight_room(first["index"])
check("the fight resolves", fight["state"] in ("won", "lost"), f"state={fight['state']}")
if fight["state"] == "won":
    check("winning is recorded by the server", last.json()["resolved"]["cleared"] is True)
    check("the enemy is at zero", fight["enemy"]["hp"] == 0)
    r2 = client.post(f"/api/rooms/{first['index']}/enter")
    check("a cleared room cannot be re-entered", r2.status_code == 409, f"got {r2.status_code}")
else:
    print(f"  NOTE  baseline fight lost after {fight['turn']} turns (informational)")

print("\n=== 5. Actions outside a fight are rejected ===")
r = client.post(f"/api/rooms/{first['index']}/act", json={"action": "attack"})
check("acting with no fight in progress is refused", r.status_code == 409, f"got {r.status_code}")
r = client.post("/api/rooms/0/act", json={"action": "attack"})
check("acting in a safe room is refused", r.status_code == 409, f"got {r.status_code}")
print("\n=== 6. Potions are earned, spent exactly once, and never client-supplied ===")
logout()
login("alchemist")
client.post("/api/tasks", json={"title": "water the plants", "kind": "daily"})
task = next(t for t in client.get("/api/tasks").json() if t["title"] == "water the plants")
client.post(f"/api/tasks/{task['id']}/complete", json={"note": "did it"})
player = client.get("/api/player").json()
check("completing a real quest earns a potion", player["potions_total"] >= 1,
      f"total={player['potions_total']}")

rooms = client.get("/api/rooms").json()["rooms"]
target = next(r for r in rooms if not r["safe"] and not r["blocked"])
fight = client.post(f"/api/rooms/{target['index']}/enter").json()["fight"]
check("the fight starts holding the earned potions", sum(fight["potions"].values()) >= 1)

category = next(iter(fight["potions"]))
held = fight["potions"][category]
r = client.post(f"/api/rooms/{target['index']}/act",
                json={"action": "potion", "potion": category})
check("drinking a held potion succeeds", r.status_code == 200, r.text[:200])
after = r.json()["fight"]["potions"].get(category, 0)
check("the fight state counts it down", after == held - 1, f"{held} -> {after}")

r = client.post(f"/api/rooms/{target['index']}/act",
                json={"action": "potion", "potion": category})
check("drinking the last one twice is refused", r.status_code in (409, 400),
      f"got {r.status_code}")

print("\n=== 7. Cooldowns and bogus actions are refused ===")
# Establish a cooldown first: POWER_COOLDOWN turns follow a power strike, so
# only the turn right after one can be refused. (Asserting this immediately
# after a potion tested nothing, because power was genuinely available.)
state = client.post(f"/api/rooms/{target['index']}/act",
                    json={"action": "power"}).json()["fight"]
check("a power strike puts the skill on cooldown", state["power_cd"] > 0,
      f"power_cd={state['power_cd']}")
r = client.post(f"/api/rooms/{target['index']}/act", json={"action": "power"})
check("power strike on cooldown is refused", r.status_code == 409, f"got {r.status_code}")
r = client.post(f"/api/rooms/{target['index']}/act", json={"action": "cheat"})
check("an unknown action is refused", r.status_code in (409, 400), f"got {r.status_code}")
r = client.post(f"/api/rooms/{target['index']}/act",
                json={"action": "potion", "potion": "vitality"})
check("a potion that does not exist is refused", r.status_code in (400, 409),
      f"got {r.status_code}")

print("\n=== 8. Fleeing is free ===")
logout()
login("coward")
rooms = client.get("/api/rooms").json()["rooms"]
target = next(r for r in rooms if not r["safe"] and not r["blocked"])
client.post(f"/api/rooms/{target['index']}/enter")
before = client.get("/api/player").json()["potions_total"]
r = client.post(f"/api/rooms/{target['index']}/act", json={"action": "flee"})
check("fleeing succeeds", r.status_code == 200, r.text[:200])
check("fleeing resolves as fled", r.json()["fight"]["state"] == "fled")
check("fleeing spends no potions", client.get("/api/player").json()["potions_total"] == before)
r = client.post(f"/api/rooms/{target['index']}/act", json={"action": "attack"})
check("a fled fight cannot be resumed", r.status_code == 409, f"got {r.status_code}")

print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s): {failures}")
    raise SystemExit(1)
print("All checks passed.")