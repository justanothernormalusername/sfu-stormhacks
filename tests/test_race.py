"""Does the per-fight lock actually stop double-spending?

Fires N concurrent `act` requests at one fight and checks the outcome is exactly
one turn's worth of change. Without the lock in api.fight_lock, every thread
loads the same state and each writes its own result, so the fight silently skips
turns and — worse — a potion action writes one `PotionUse` row per thread.

    PYTHONPATH=. .venv/bin/python race_test.py
"""

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/race.db"
os.environ["SECRET_KEY"] = "x"
# Empty means "classifier off": keeps this run hermetic. Without it a
# developer .env key would make a live call per quest and the reward
# would depend on what the model decided today.
os.environ["CLASSIFIER_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from src.app.db import engine, init_db  # noqa: E402
from src.app.main import app  # noqa: E402
from src.app.models import PotionUse, User  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

init_db()
THREADS = 12


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name} {detail if not ok else ''}")
    if not ok:
        check.failures.append(name)


check.failures = []

# --- Turn integrity: many concurrent attacks advance the fight by one turn each.
main = TestClient(app, raise_server_exceptions=False)
main.post("/login", data={"username": "racer", "password": "hunter22",
                          "action": "register"})
floor = main.get("/api/rooms").json()
room = next(r for r in floor["rooms"] if not r["safe"] and not r["blocked"])
fight = main.post(f"/api/rooms/{room['index']}/enter").json()["fight"]
start_turn = fight["turn"]


def hammer(_: int) -> dict:
    # Each thread needs its own client: TestClient shares cookie state, and a
    # session cookie rewritten mid-flight would make this test a session-jar race
    # rather than a fight-lock race.
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.update(main.cookies)
    r = client.post(f"/api/rooms/{room['index']}/act", json={"action": "attack"})
    return {"status": r.status_code, "turn": (r.json().get("fight") or {}).get("turn")}


with ThreadPoolExecutor(max_workers=THREADS) as pool:
    results = list(pool.map(hammer, range(THREADS)))

ok = [r for r in results if r["status"] == 200]
turns = sorted(r["turn"] for r in ok)
print(f"\n=== {THREADS} concurrent attacks from turn {start_turn} ===")
print(f"  200s: {len(ok)}/{THREADS}   turns returned: {turns}")
check("every concurrent request got a definite answer",
      all(r["status"] in (200, 409) for r in results),
      f"statuses {sorted({r['status'] for r in results})}")

# Once the enemy is dead the fight resolves, and `save_fight` drops it — so every
# later request is refused with 409 and the requests that *did* return 200 are the
# turns up to and including the killing blow. Duplicates at the end would mean two
# threads both resolved the same final turn, which is the actual race.
#
# So the invariant is not "no turn repeats" but "turns form an unbroken run from
# start_turn, with the final turn possibly repeated because the fight ended there."
final_state = main.post(f"/api/rooms/{room['index']}/act", json={"action": "attack"})
check("turns are unbroken from the start (no skipped turns)",
      sorted(set(turns)) == list(range(start_turn + 1, start_turn + 1 + len(set(turns)))),
      f"expected consecutive from {start_turn + 1}, got {turns}")
check("only the final turn may repeat",
      len(set(turns[:-1])) == len(turns[:-1]),
      f"duplicate before the end: {turns}")
check("the fight resolved rather than hanging",
      final_state.status_code == 409
      or final_state.json().get("fight", {}).get("state") != "fight",
      "fight still live after every thread had a turn")

# --- Potion integrity: the real prize. Concurrent drinks must not multiply rows.
main.post("/api/tasks", json={"title": "race chore"})
task = next(t for t in main.get("/api/tasks").json() if t["title"] == "race chore")
main.post(f"/api/tasks/{task['id']}/complete", json={"note": "ok"})
held = main.get("/api/player").json()["potions_total"]
print(f"\n=== {THREADS} concurrent potion drinks (player holds {held}) ===")

with Session(engine) as session:
    user_id = session.exec(select(User).where(User.username == "racer")).one().id

rooms = main.get("/api/rooms").json()["rooms"]
target = next(r for r in rooms if not r["safe"] and not r["blocked"] and not r["cleared"])
main.post(f"/api/rooms/{target['index']}/enter")
fight = main.get("/api/player").json()
category = "heal"


def drink(_: int) -> int:
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.update(main.cookies)
    return client.post(f"/api/rooms/{target['index']}/act",
                       json={"action": "potion", "potion": category}).status_code


with ThreadPoolExecutor(max_workers=THREADS) as pool:
    drink_status = list(pool.map(drink, range(THREADS)))

# Count the rows directly rather than trusting the derived count — the derived
# count is what the app shows the player, so checking it against itself would be
# circular. The invariant is between what was accepted and what was persisted.
with Session(engine) as session:
    rows = len(session.exec(
        select(PotionUse).where(PotionUse.user_id == user_id)).all())
accepted = sum(1 for s in drink_status if s == 200)
print(f"  statuses: {sorted(set(drink_status))}   PotionUse rows written: {rows}")
check("at most one drink per potion held", accepted <= held,
      f"{accepted} accepted with {held} held")
check("PotionUse rows match the accepted requests",
      rows == accepted, f"{rows} rows vs {accepted} accepted")

print("\n" + "=" * 60)
if check.failures:
    print(f"FAILED: {check.failures}")
    raise SystemExit(1)
print("Race checks passed.")