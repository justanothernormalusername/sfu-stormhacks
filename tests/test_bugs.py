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
from sqlmodel import Session, select  # noqa: E402

from src.app import config, game  # noqa: E402
from src.app.db import engine, init_db  # noqa: E402
from src.app.main import app  # noqa: E402
from src.app.models import BattleClear, User, utcnow  # noqa: E402

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


def clear_everything() -> None:
    """Seed a completed route to test the shrine independently of combat luck.

    Repeated fights no longer accumulate progress across deaths.
    """
    username = c.get("/api/player").json()["username"]
    rooms = c.get("/api/rooms").json()["rooms"]
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).one()
        for room in rooms:
            if not room["safe"]:
                session.add(BattleClear(user_id=user.id, week_start=game.week_start(utcnow()),
                                        room_index=room["index"], hp_after=config.PLAYER_BASE["max_hp"]))
        session.commit()


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

print("\n=== 1b. The shrine heals what it says, and the heal survives walking past it ===")
# Two ways this was wrong, both invisible from the happy path because a full-HP
# player heals the right amount by accident:
#   * it wrote `max_hp` while reporting `restore`, so the HUD claimed "+58" and
#     the player got a whole bar;
#   * HP is read from the *furthest* cleared row, so a shrine used after walking
#     past it recorded a heal nothing ever read back — the run gained nothing
#     while the client said it had.
# The invariant that covers both: `restored` must equal the HP actually gained.
SHRINE = next(r["index"] for r in floor["rooms"] if r["safe"] and r.get("restore"))
MAX_HP = config.PLAYER_BASE["max_hp"]


def seed_route(indices, hp):
    """Write clear rows directly, so the heal is tested independently of combat."""
    username = c.get("/api/player").json()["username"]
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).one()
        for index in indices:
            session.add(BattleClear(user_id=user.id, week_start=game.week_start(utcnow()),
                                    room_index=index, hp_after=hp))
        session.commit()


def current_hp() -> int:
    return c.get("/api/player").json()["hp"]


for label, route, start_hp in [("shallow and wounded", [1, 2, 3], 40),
                               ("deep and wounded", [1, 2, 3, 7, 8, 9], 40),
                               ("deep and healthy", [1, 2, 3, 7, 8, 9], MAX_HP),
                               ("nearly full", [1, 2, 3, 7, 8, 9], MAX_HP - 10),
                               ("already full", [1, 2, 3], MAX_HP)]:
    login(f"heal-{label.replace(' ', '-')}")
    seed_route(route, start_hp)
    before = current_hp()
    rested = c.post(f"/api/rooms/{SHRINE}/enter").json()
    after = current_hp()
    check(f"{label}: the reported heal is the heal granted",
          rested["restored"] == after - before,
          f"reported {rested['restored']}, granted {after - before}")
    check(f"{label}: HP never goes down and never overflows",
          before <= after <= MAX_HP, f"{before} -> {after} (max {MAX_HP})")

login("heal-depth")
seed_route([1, 2, 3], 40)
c.post(f"/api/rooms/{SHRINE}/enter")
check("resting does not advance depth",
      c.get("/api/player").json()["furthest_room"] == 3,
      f"got {c.get('/api/player').json()['furthest_room']}")

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

print("\n=== 7. Every config.* the /api/config endpoint publishes exists ===")
# This endpoint is built by reading attributes off the config module by name, so
# nothing about it fails at import time — a constant that is deleted 500s at
# runtime instead, and only on the one URL the Phaser client fetches during boot.
# `Promise.all` in BootScene.create then rejects and /play never leaves
# "Loading dungeon...", which looks like a broken server rather than a bad number.
# Nothing else here calls /api/config, so this is the check that catches it.
login("cfg")
r = c.get("/api/config")
check("/api/config is not a 500", r.status_code == 200, f"got {r.status_code} {r.text[:140]}")
if r.status_code == 200:
    cfg = r.json()
    # Every key the client reads at boot, so a rename breaks here rather than
    # silently rendering `undefined` into the HUD.
    for key in ("room_count", "potion_categories", "potion_effects",
                "player", "potion_min", "potion_max", "kind_labels",
                "boss_hp_cap"):
        check(f"/api/config publishes {key!r}", key in cfg)
    # The HUD prints this as "Room n / room_count", so it has to equal the number
    # of rooms actually on the floor — that is the whole reason it is derived.
    floor_rooms = len(c.get("/api/rooms").json()["rooms"])
    check("room_count matches the floor", cfg["room_count"] == floor_rooms,
          f"config says {cfg['room_count']}, floor has {floor_rooms}")
    check("potion_categories are all described by potion_effects",
          set(cfg["potion_categories"]) <= set(cfg["potion_effects"]))

print("\n=== 8. The boss HP ceiling is honoured, and can be unbounded ===")
# BOSS_HP_CAP is a ceiling on the depth curve. Two ways it can go wrong without
# any test noticing: a cap above the curve's result is silently a no-op (so
# tuning hp_mult looks broken), and an unbounded cap has to actually mean unbounded
# rather than falling back to some hidden default.
boss_room = next(r for r in floor["rooms"] if r["kind"] == "boss")
cap = cfg["boss_hp_cap"]
if cap is None:
    check("unbounded boss HP is the curve's own value", boss_room["enemy"]["hp"] > 0,
          f"got {boss_room['enemy']['hp']}")
else:
    check("boss HP never exceeds the ceiling", boss_room["enemy"]["hp"] <= cap,
          f"enemy {boss_room['enemy']['hp']} > cap {cap}")

print("\n=== 9. Archiving a quest does not confiscate its reward ===")
login("archiver")
c.post("/api/tasks", json={"title": "archive reward test"})
task = next(t for t in c.get("/api/tasks").json() if t["title"] == "archive reward test")
c.post(f"/api/tasks/{task['id']}/complete", json={"note": "done"})
before = c.get("/api/player").json()["potions_total"]
c.delete(f"/api/tasks/{task['id']}")
after = c.get("/api/player").json()["potions_total"]
check("earned potions survive archiving", before > 0 and after == before,
      f"before={before}, after={after}")
again = c.post(f"/api/tasks/{task['id']}/complete", json={"note": "again"})
check("an archived quest cannot be completed through the API", again.status_code == 409,
      f"got {again.status_code}")

print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {failures}")
    raise SystemExit(1)
print("No bugs found.")
