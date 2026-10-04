"""Play a whole weekly floor through the public API, as a player would.

The unit checks in test_combat.py prove the rules; this proves the floor is
actually *playable* end to end — that a player can work their way from the
entrance to the boss through the doors the server opens, without touching a
database directly or claiming anything the server would not hand out.
"""

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/floor.db"
os.environ["SECRET_KEY"] = "x"

from fastapi.testclient import TestClient  # noqa: E402

from src.app.db import init_db  # noqa: E402
from src.app.main import app  # noqa: E402

init_db()
c = TestClient(app)
c.post("/login", data={"username": "delver", "password": "hunter22", "action": "register"})

# Earn potions the honest way, so the run is budgeted the way a real week is.
for i in range(8):
    c.post("/api/tasks", json={"title": f"chore {i}"})
for t in c.get("/api/tasks").json():
    c.post(f"/api/tasks/{t['id']}/complete", json={"note": "ok"})
print("potions earned:", c.get("/api/player").json()["potions_total"])


def play(idx):
    """Enter a room and fight it with a simple, decent policy."""
    r = c.post(f"/api/rooms/{idx}/enter")
    if r.status_code != 200:
        return None, 0
    f = r.json()["fight"]
    n = 0
    while f["state"] == "fight" and n < 400:
        if (f["hero"]["hp"] < f["hero"]["max_hp"] * 0.35
                and f["potions"].get("heal", 0) > 0 and f["turn"] > 2):
            action, potion = "potion", "heal"
        else:
            action = "power" if f["power_cd"] == 0 else "attack"
            potion = None
        rr = c.post(f"/api/rooms/{idx}/act", json={"action": action, "potion": potion})
        if rr.status_code != 200:
            return f"error:{rr.status_code}", n
        f = rr.json()["fight"]
        n += 1
    return f["state"], n


cleared = set()
for sweep in range(8):
    floor = c.get("/api/rooms").json()
    progressed = False
    for r in floor["rooms"]:
        if r["safe"] or r["cleared"]:
            continue
        state, turns = play(r["index"])
        if state == "won":
            cleared.add(r["index"])
            progressed = True
            print(f"  cleared {r['index']:2d} {r['name'][:30]:32s} {turns:3d} turns")
    if not progressed:
        break
    # Rest at the shrine whenever it becomes reachable.
    floor = c.get("/api/rooms").json()
    shrine = next((x for x in floor["rooms"]
                   if x["safe"] and x.get("restore") and not x["cleared"]
                   and not x["blocked"]), None)
    if shrine:
        rr = c.post(f"/api/rooms/{shrine['index']}/enter")
        got = rr.json().get("restored") if rr.status_code == 200 else "-"
        print(f"  shrine {shrine['index']}: {rr.status_code} restored={got}")

floor = c.get("/api/rooms").json()
combat = [x for x in floor["rooms"] if not x["safe"]]
boss = next(x for x in floor["rooms"] if x["kind"] == "boss")
print(f"\ncleared {len(cleared)}/{len(combat)} combat rooms")
print(f"checkpoint: {c.get('/api/player').json()['checkpoint']}")
print("RESULT: " + ("BOSS DEFEATED" if boss["index"] in cleared else "BOSS NOT REACHED"))
