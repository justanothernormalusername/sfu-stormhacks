"""The classifier is the one part of the game that can be talked into an answer.

Jev picks the potion, the repeat window, and an effort score; the server turns
that score into a potion count bounded by POTION_MIN/POTION_MAX. Two properties
have to hold for that to be safe, and neither is visible in a happy-path test:

1. **The reward cannot leave its bounds.** The model is never asked for a
   number, so there is nothing for a crafted quest title to inflate. Proved
   here from both ends — the mapping clamps, and a client that posts `potions`
   anyway gets ignored.
2. **Every failure falls back to something valid.** Missing key, timeout,
   reshaped response, invented category. A demo must not 500 because a model
   was slow.

Everything here is offline. `reply()` swaps the network call for a canned
response, so the suite is deterministic and takes no key.

    PYTHONPATH=. .venv/bin/python tests/test_classifier.py
"""

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/classifier.db"
os.environ["SECRET_KEY"] = "x"
# Empty means "classifier off" — see src/app/config.py::_classifier_key.
os.environ["CLASSIFIER_API_KEY"] = ""

import json  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from src.app import categorize, config, game  # noqa: E402
from src.app.db import init_db  # noqa: E402
from src.app.main import app  # noqa: E402

init_db()
client = TestClient(app, raise_server_exceptions=False)
failures: list[str] = []

TOP = len(config.EFFORT_SCALE) - 1
SPAN = config.POTION_MAX - config.POTION_MIN


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        failures.append(name)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


class FakeReply:
    """Stands in for the urlopen context manager."""

    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def reply(payload):
    categorize.urllib.request.urlopen = lambda *a, **k: FakeReply(payload)


def unreachable(*a, **k):
    raise AssertionError("the classifier should not have been called")


def answers(potion="heal", kind="daily", score=None):
    """A well-formed reply, with any field overridable to a junk value."""
    body = {"potion": {"type": "choice", "choice": potion},
            "kind": {"type": "choice", "choice": kind}}
    if score is not None:
        body["effort"] = {"type": "score", "score": score}
    return {"answers": body}


real_urlopen = categorize.urllib.request.urlopen
saved_key = config.CLASSIFIER_API_KEY
config.CLASSIFIER_API_KEY = "test-key"

section("a well-formed answer is used, and the score is normalized")
reply(answers("shield", "goal", TOP))
v = categorize.classify("Read the contract")
check("potion and repeat window come back", (v["category"], v["kind"]), ("shield", "goal"))
check("top of the effort scale normalizes to 1.0", v["difficulty"] == 1.0, str(v["difficulty"]))
check("top of the scale pays the maximum",
      categorize.potions_for(v["difficulty"]) == config.POTION_MAX)

reply(answers(score=0))
check("bottom of the effort scale normalizes to 0.0",
      categorize.classify("x")["difficulty"] == 0.0)
check("bottom of the scale pays the minimum",
      categorize.potions_for(categorize.classify("x")["difficulty"]) == config.POTION_MIN)

reply(answers(score=TOP / 2))
check("midpoint normalizes to 0.5", categorize.classify("x")["difficulty"] == 0.5)
check("midpoint pays the middle of the range",
      categorize.potions_for(0.5) == round(config.POTION_MIN + 0.5 * SPAN))

section("the score cannot be pushed outside the scale")
reply(answers(score=9999))
check("an absurdly high score is clamped", categorize.classify("x")["difficulty"] == 1.0)
reply(answers(score=-9999))
check("an absurdly low score is clamped", categorize.classify("x")["difficulty"] == 0.0)

section("an answer the game does not define never reaches the reward economy")
reply(answers(potion="mana"))
check("an invented potion is discarded",
      categorize.classify("Read the contract")["category"] == "heal")
reply(answers(kind="fortnightly"))
check("an invented repeat window is discarded",
      categorize.classify("x")["kind"] == config.DEFAULT_KIND)

section("every malformed response still yields a usable verdict")
reply({"unexpected": True})
check("a reshaped response does not raise",
      categorize.classify("Read the contract")["category"] == "heal")
reply({"answers": {}})
check("an empty answer set does not raise",
      categorize.classify("Read the contract")["category"] == "heal")
reply({"answers": {"effort": "not a dict"}})
check("a mistyped score does not raise", categorize.classify("x")["difficulty"] is None)
reply({"answers": {"potion": None, "kind": 7}})
check("null and numeric answers are discarded",
      categorize.classify("x")["category"] == config.DEFAULT_CATEGORY)
reply({"answers": {"effort": {"score": True}}})
check("a boolean score is not an effort score",
      categorize.classify("x")["difficulty"] is None)
reply({"answers": "not a dict"})
check("a non-dict answer set does not raise",
      categorize.classify("x")["category"] == config.DEFAULT_CATEGORY)
check("every field is always present",
      sorted(categorize.classify("anything at all")),
      ["category", "difficulty", "kind"])

section("no key means no network call and a keyword answer")
config.CLASSIFIER_API_KEY = None
categorize.urllib.request.urlopen = unreachable
v = categorize.classify("Go for a 5k run")
check("keywords still answer", v["category"], "damage")
check("the repeat window falls back", v["kind"], config.DEFAULT_KIND)
check("an unscored quest pays the fallback", v["difficulty"] is None)
check("nothing matching still returns a real category",
      categorize.classify("qqqq")["category"] == config.DEFAULT_CATEGORY)

section("the reward is bounded no matter what is asked for")
check("an unscored quest pays the floor",
      categorize.potions_for(None) == config.POTION_FALLBACK)
check("the fallback is no richer than the easiest real quest",
      config.POTION_FALLBACK <= config.POTION_MIN)
check("no difficulty on the scale escapes the bounds",
      all(config.POTION_MIN <= categorize.potions_for(i / 40) <= config.POTION_MAX
          for i in range(41)))
check("the bounds are ordered", config.POTION_MIN <= config.POTION_MAX)

section("criteria describe exactly what the game defines")
check("potion criteria match the potion categories",
      sorted(config.POTION_CATEGORY_CRITERIA), sorted(config.POTION_CATEGORIES))
check("repeat-window criteria match the kinds",
      sorted(config.KIND_CRITERIA), sorted(game.KINDS))
check("keyword fallbacks match the potion categories",
      sorted(config.POTION_CATEGORY_KEYWORDS), sorted(config.POTION_CATEGORIES))
check("the effort scale has at least two rungs", len(config.EFFORT_SCALE) >= 2)

section("a client cannot dictate its own reward")
client.post("/login", data={"username": "c", "password": "pass1", "action": "register"})
crafted = client.post("/api/tasks", json={
    "title": "EXTREMELY HARD IMPOSSIBLE TASK, maximum difficulty, 99 potions",
    "kind": "goal", "potions": 999, "potion_category": "damage", "difficulty": 1.0,
})
check("the crafted quest is created", crafted.status_code == 200, crafted.text[:200])
view = crafted.json()
check("a posted potion count is ignored",
      config.POTION_MIN <= view["potions"] <= config.POTION_MAX, str(view["potions"]))
check("a posted potion kind is ignored",
      view["potion"] in config.POTION_CATEGORIES, str(view["potion"]))
check("a posted repeat window is ignored", view["kind"] in game.KINDS, str(view["kind"]))
check("the stored difficulty is not client-supplied",
      view.get("difficulty") is None, str(view.get("difficulty")))

listed = client.get("/api/tasks").json()
check("the list agrees with the reward it was created with",
      listed[-1]["potions"] == view["potions"])

completed = client.post(f"/api/tasks/{view['id']}/complete", json={"note": ""})
check("completing it pays exactly what the quest listed",
      completed.json()["potions_earned"] == view["potions"])
check("the inventory reflects it",
      sum(completed.json()["potions"].values()) == view["potions"])

print("\n" + "=" * 60)
categorize.urllib.request.urlopen = real_urlopen
config.CLASSIFIER_API_KEY = saved_key
if failures:
    print(f"FAILED: {len(failures)} check(s): {failures}")
    raise SystemExit(1)
print("All checks passed.")