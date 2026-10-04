"""Death resets the run; fleeing and task history survive as intended."""
import os
import tempfile
import unittest

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/reset.db"
os.environ["SECRET_KEY"] = "test-reset"
os.environ["CLASSIFIER_API_KEY"] = ""

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from src.app import config, game
from src.app.db import engine, init_db
from src.app.main import app
from src.app.models import BattleClear, Completion, Task, User, utcnow
from src.app.routes import api


class ResetTests(unittest.TestCase):
    def test_death_resets_only_the_players_run(self):
        init_db()
        client = TestClient(app)
        client.post("/login", data={"username": "resetter", "password": "hunter22",
                                    "action": "register"})
        start = game.week_start(utcnow())
        baseline = client.get("/api/rooms").json()
        target = next(r for r in baseline["rooms"] if not r["safe"] and not r["blocked"])
        a = target["index"]
        with Session(engine) as session:
            user = session.exec(select(User).where(User.username == "resetter")).one()
            other = User(username="unaffected", password_hash="unused")
            session.add(other)
            session.flush()
            other_id = other.id
            # A pack with every category, earned from completed tasks.
            for category in config.POTION_CATEGORIES:
                task = Task(user_id=user.id, title=f"quest {category}", kind="daily",
                            potion_category=category, difficulty=1)
                session.add(task)
                session.flush()
                session.add(Completion(user_id=user.id, task_id=task.id, note="keep me"))
            pending = Task(user_id=user.id, title="unfinished quest", kind="goal")
            session.add(pending)
            session.flush()
            pending_id = pending.id
            for room in baseline["rooms"]:
                if room["index"] not in (0, a):
                    session.add(BattleClear(user_id=user.id, week_start=start,
                                           room_index=room["index"], hp_after=50))
            session.add(BattleClear(user_id=other_id, week_start=start, room_index=a, hp_after=70))
            session.commit()
            user_id = user.id

        tasks_before = client.get("/api/tasks").json()
        log_before = client.get("/api/log").json()
        rooms_before = client.get("/api/rooms").json()
        player_before = client.get("/api/player").json()
        self.assertGreater(player_before["potions_total"], 0)

        # Fleeing preserves inventory, clears, shrine use, and task history.
        self.assertEqual(client.post(f"/api/rooms/{a}/enter").status_code, 200)
        fled = client.post(f"/api/rooms/{a}/act", json={"action": "flee"}).json()
        self.assertEqual(fled["fight"]["state"], "fled")
        self.assertIsNone(fled["resolved"])
        self.assertEqual(fled["player"], player_before)
        self.assertEqual(client.get("/api/rooms").json(), rooms_before)

        # Death must invalidate the active fight and the whole run.
        self.assertEqual(client.post(f"/api/rooms/{a}/enter").status_code, 200)
        key = (user_id, a, start.isoformat())
        with api._FIGHT_LOCK:
            fight = api._FIGHTS[key]
            fight["hero"]["hp"] = 1
            fight["enemy"]["hp"] = 10000
            fight["enemy"]["atk"] = 10000
            fight["profile"] = {}
        lost = client.post(f"/api/rooms/{a}/act", json={"action": "attack"}).json()
        self.assertEqual(lost["fight"]["state"], "lost")
        self.assertTrue(lost["resolved"]["reset"])
        player = lost["player"]
        self.assertEqual(player["hp"], player["max_hp"])
        self.assertEqual(player["furthest_room"], 0)
        self.assertNotIn("checkpoint", player)
        self.assertEqual(player["potions_total"], 0)
        self.assertEqual(client.get("/api/player").json(), player)
        self.assertEqual(client.get("/api/rooms").json(), baseline)
        self.assertEqual(client.get("/api/tasks").json(), tasks_before)
        self.assertEqual(client.get("/api/log").json(), log_before)
        self.assertEqual(client.get("/api/leaderboard").json()[0]["furthest_room"], 0)
        self.assertEqual(client.post(f"/api/rooms/{a}/act",
                                     json={"action": "attack"}).status_code, 409)
        with Session(engine) as session:
            other_clear = session.exec(select(BattleClear).where(BattleClear.user_id == other_id)).one()
            self.assertEqual(other_clear.hp_after, 70)

        # A fresh fight starts full; future task rewards still replenish the pack.
        fresh = client.post(f"/api/rooms/{a}/enter").json()["fight"]
        self.assertEqual(fresh["hero"]["hp"], player["max_hp"])
        self.assertEqual(fresh["enemy"]["hp"], target["enemy"]["hp"])
        self.assertFalse(any(fresh["buffs"].values()))
        self.assertEqual(sum(fresh["potions"].values()), 0)
        completed = client.post(f"/api/tasks/{pending_id}/complete", json={"note": "new run"})
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(client.get("/api/player").json()["potions_total"],
                         completed.json()["potions_earned"])


if __name__ == "__main__":
    unittest.main()
