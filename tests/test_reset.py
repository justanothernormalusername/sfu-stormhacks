"""Death resets the run; fleeing and task history survive as intended."""
import os
import tempfile
import unittest
from datetime import timedelta

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
        targets = [r for r in baseline["rooms"] if not r["safe"] and not r["blocked"]][:2]
        a, b = [r["index"] for r in targets]
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
                if room["index"] not in (0, a, b):
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

        # Leave another room's fight open: death must invalidate both fights.
        self.assertEqual(client.post(f"/api/rooms/{a}/enter").status_code, 200)
        self.assertEqual(client.post(f"/api/rooms/{b}/enter").status_code, 200)
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
        for index in (a, b):
            self.assertEqual(client.post(f"/api/rooms/{index}/act",
                                         json={"action": "attack"}).status_code, 409)
        with Session(engine) as session:
            other_clear = session.exec(select(BattleClear).where(BattleClear.user_id == other_id)).one()
            self.assertEqual(other_clear.hp_after, 70)

        # A fresh fight starts full; future task rewards still replenish the pack.
        fresh = client.post(f"/api/rooms/{a}/enter").json()["fight"]
        self.assertEqual(fresh["hero"]["hp"], player["max_hp"])
        self.assertEqual(fresh["enemy"]["hp"], targets[0]["enemy"]["hp"])
        self.assertFalse(any(fresh["buffs"].values()))
        self.assertEqual(sum(fresh["potions"].values()), 0)
        completed = client.post(f"/api/tasks/{pending_id}/complete", json={"note": "new run"})
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(client.get("/api/player").json()["potions_total"],
                         completed.json()["potions_earned"])

    def test_weekly_progress_is_derived_and_outlives_death(self):
        """The progress bar measures real life, so a dungeon reset cannot touch it.

        It is derived rather than stored — target is the count of active quests,
        banked is the distinct active quests completed inside the week window —
        which means there is no column to keep in sync and nothing for the
        weekly reset to clear. Death is the real test: `record_fight_loss`
        deletes BattleClear rows and writes compensating PotionUse rows, so
        anything reading those tables would drop to zero here. This reads
        Completion, which is append-only, and so it should not move.
        """
        init_db()
        client = TestClient(app)
        client.post("/login", data={"username": "progress", "password": "hunter22",
                                    "action": "register"})
        start = game.week_start(utcnow())
        with Session(engine) as session:
            user = session.exec(select(User).where(User.username == "progress")).one()
            ids = []
            for i in range(4):
                task = Task(user_id=user.id, title=f"quest {i}", kind="daily",
                            potion_category="heal", difficulty=1)
                session.add(task)
                session.flush()
                ids.append(task.id)
            for task_id in ids[:3]:
                session.add(Completion(user_id=user.id, task_id=task_id, note="done"))
            # A completion from before the week window, which must not count.
            stale = Task(user_id=user.id, title="last week", kind="daily",
                         potion_category="heal", difficulty=1)
            session.add(stale)
            session.flush()
            session.add(Completion(user_id=user.id, task_id=stale.id, note="old",
                                   completed_at=start - timedelta(days=3)))
            # A second completion of an already-banked quest: one step, not two.
            session.add(Completion(user_id=user.id, task_id=ids[0], note="again",
                                   completed_at=start + timedelta(hours=1)))
            session.commit()
            stale_id = stale.id
            user_id = user.id

        weekly = client.get("/api/player").json()["weekly"]
        self.assertEqual(weekly["target"], 5)
        self.assertEqual(weekly["banked"], 3)
        self.assertEqual(weekly["pct"], 3 / 5)

        # Archiving lowers the target by one, so the bar cannot end up with a slot
        # that can never be filled again. It is progress through *this week's*
        # board, not an all-time tally.
        client.delete(f"/api/tasks/{stale_id}")
        weekly = client.get("/api/player").json()["weekly"]
        self.assertEqual(weekly["target"], 4)
        self.assertEqual(weekly["banked"], 3)

        # Now die, and the bar must not move. The fight is mutated in place under the
        # lock, because the JSON the client got back is a copy — editing it would
        # only edit the test's own dict.
        rooms = client.get("/api/rooms").json()
        room = next(r for r in rooms["rooms"] if not r["safe"] and not r["blocked"])
        self.assertEqual(client.post(f"/api/rooms/{room['index']}/enter").status_code, 200)
        with api._FIGHT_LOCK:
            key = (user_id, room["index"], start.isoformat())
            fight = api._FIGHTS[key]
            fight["hero"]["hp"] = 1
            fight["enemy"]["hp"] = 10000
            fight["enemy"]["atk"] = 10000
            fight["profile"] = {}
        lost = client.post(f"/api/rooms/{room['index']}/act",
                           json={"action": "attack"}).json()
        self.assertEqual(lost["fight"]["state"], "lost")
        self.assertTrue(lost["resolved"]["reset"])

        after = client.get("/api/player").json()
        self.assertEqual(after["potions_total"], 0)
        self.assertEqual(after["weekly"], weekly)
        # The log outlives the run too, and so does the bar's evidence for it.
        # Every completion row is still there — including the stale one, which
        # the bar ignores but the history keeps.
        self.assertEqual(len(client.get("/api/log").json()), 5)


if __name__ == "__main__":
    unittest.main()
