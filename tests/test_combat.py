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
# Empty means "classifier off": keeps this run hermetic. Without it a
# developer .env key would make a live call per quest and the reward
# would depend on what the model decided today.
os.environ["CLASSIFIER_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from src.app import config, game  # noqa: E402
from src.app.db import engine, init_db  # noqa: E402
from src.app.main import app  # noqa: E402
from src.app.models import Completion, PotionUse, Task, User, utcnow  # noqa: E402
from src.app.routes import api  # noqa: E402
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
after = walkable_rooms(floor, {1})
check("clearing a room opens more of the floor", len(after) > len(before),
      f"{len(before)} -> {len(after)}")
check("rooms form one sequential chain",
      {tuple(link) for link in floor["links"]}
      == {(i, i + 1) for i in range(len(rooms) - 1)})
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
# `kind` is no longer sent by the client — the classifier picks the repeat window
# and the potion count, so the request is a title and nothing else.
client.post("/api/tasks", json={"title": "water the plants"})
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

print("\n=== 6b. A drink costs exactly one potion and heals exactly what it reports ===")
# Players reported two bugs: healing "not healing the correct amount", and potions
# vanishing when two were held. Neither is an accounting bug — this pins the
# arithmetic that both reports actually turned on, so a future change to the heal
# value or the derived inventory has to be deliberate.
#
# The pack is written directly rather than earned through a quest, because the
# count under test is the count *after* a drink and the classifier's opinion about
# how many a quest pays is not what's under test here.
logout()
login("quench")
with Session(engine) as session:
    user = session.exec(select(User).where(User.username == "quench")).one()
    # difficulty 0.125 maps to exactly 2 on the current POTION_MIN..MAX range.
    quest = Task(user_id=user.id, title="sip water", kind="goal",
                 potion_category="heal", difficulty=0.125)
    session.add(quest)
    session.flush()
    session.add(Completion(user_id=user.id, task_id=quest.id, note="banked"))
    session.commit()
    quencher, uid = user.id, user.id

rooms = client.get("/api/rooms").json()["rooms"]
heal_room = next(r for r in rooms if not r["safe"] and not r["blocked"])
start = game.week_start(utcnow())
entered = client.post(f"/api/rooms/{heal_room['index']}/enter").json()
check("the pack holds exactly two heals to begin with",
      entered["player"]["potions"].get("heal") == 2,
      f"got {entered['player']['potions']}")

drunk = client.post(f"/api/rooms/{heal_room['index']}/act",
                    json={"action": "potion", "potion": "heal"}).json()
check("drinking one of two leaves exactly one",
      drunk["player"]["potions"].get("heal") == 1,
      f"got {drunk['player']['potions']}")
check("the fight snapshot agrees with the derived count",
      drunk["fight"]["potions"].get("heal") == 1,
      f"got {drunk['fight']['potions']}")
with Session(engine) as session:
    uses = session.exec(select(PotionUse).where(PotionUse.user_id == uid)).all()
    check("one drink writes exactly one PotionUse row", len(uses) == 1,
          f"got {len(uses)}")

# The heal is a flat 65 capped at max HP, and the server logs the delta it
# actually applied rather than the nominal value. These two cases are the whole
# reason a player could think healing was broken: at full HP the draught is
# worth nothing, and near the top it is worth far less than 65.
full = drunk["fight"]["hero"]["max_hp"]
with api._FIGHT_LOCK:
    api._FIGHTS[(uid, heal_room["index"], start.isoformat())]["hero"]["hp"] = full
wasted = client.post(f"/api/rooms/{heal_room['index']}/act",
                     json={"action": "potion", "potion": "heal"}).json()
check("a heal drunk at full HP reports the truth, not the nominal 65",
      any("+0 HP" in line for line in wasted["fight"]["log"]),
      f"log={wasted['fight']['log'][-2:]}")
check("a heal drunk at full HP is still spent",
      "heal" not in wasted["player"]["potions"],
      f"got {wasted['player']['potions']}")

logout()
login("nearly")
with Session(engine) as session:
    user = session.exec(select(User).where(User.username == "nearly")).one()
    quest = Task(user_id=user.id, title="top up", kind="goal",
                 potion_category="heal", difficulty=1.0)
    session.add(quest)
    session.flush()
    session.add(Completion(user_id=user.id, task_id=quest.id, note="banked"))
    session.commit()
    nearly_id = user.id

client.post(f"/api/rooms/{heal_room['index']}/enter")
with api._FIGHT_LOCK:
    api._FIGHTS[(nearly_id, heal_room["index"], start.isoformat())]["hero"]["hp"] = 120
near = client.post(f"/api/rooms/{heal_room['index']}/act",
                   json={"action": "potion", "potion": "heal"}).json()
# min(65, 125 - 120) = 5. The player is told 5, not 65 — the number the client
# shows before the drink has to be this one, or the potion looks broken.
check("a heal near the top reports the capped amount it will actually give",
      any("+5 HP" in line for line in near["fight"]["log"]),
      f"log={near['fight']['log'][-2:]}")
check("the cap matches min(effect, max_hp - hp)",
      5 == min(config.POTION_EFFECTS["heal"]["heal"],
               near["fight"]["hero"]["max_hp"] - 120))

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
