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


def answers(potion="heal", kind="daily", score=None, probabilities=None):
    """A well-formed reply, with any field overridable to a junk value."""
    body = {"potion": {"type": "choice", "choice": potion},
            "kind": {"type": "choice", "choice": kind}}
    if probabilities is not None:
        body["potion"]["probabilities"] = probabilities
    if score is not None:
        body["effort"] = {"type": "score", "score": score}
    return {"answers": body}


def sure(probability: float) -> dict:
    """A distribution where the chosen option has exactly this probability.

    Built explicitly so the confidence tests do not depend on how the fake
    score spreads its remaining mass — `probabilities[choice]` is the only
    number `POTION_CONFIDENCE_MIN` is ever compared against.
    """
    rest = (1.0 - probability) / (len(config.POTION_CATEGORIES) - 1)
    return {c: (probability if c == "heal" else rest) for c in config.POTION_CATEGORIES}


real_urlopen = categorize.urllib.request.urlopen
saved_key = config.CLASSIFIER_API_KEY
config.CLASSIFIER_API_KEY = "test-key"

section("a well-formed answer is used, and the score is normalized")
reply(answers("shield", "goal", TOP, probabilities=sure(0.95)))
v = categorize.classify("Review the contract")
check("potion and repeat window come back",
      (v["category"], v["kind"]) == ("shield", "goal"),
      f"got {(v['category'], v['kind'])}")
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
# Discarded, so the keyword rules decide instead — and here they say shield.
# This used to assert `heal`, which was the bug: the discard path quietly
# answered DEFAULT_CATEGORY, so an invented label cost the player their real
# verdict and paid them the default instead.
check("an invented potion is discarded and the keywords decide",
      categorize.classify("Review the contract")["category"] == "shield")
check("an invented potion never reaches the categories",
      categorize._valid("mana", config.POTION_CATEGORIES) is None)
reply(answers(kind="fortnightly"))
check("an invented repeat window is discarded",
      categorize.classify("x")["kind"] == config.DEFAULT_KIND)

section("a low-confidence answer is overruled by the keyword rules")
# The whole point of the gate. The API always sent `probabilities` and the
# parser threw them away, so a coin flip was cached exactly like a certain
# answer. These pin that the gate is load-bearing, not decorative.
reply(answers(potion="heal", probabilities=sure(0.99)))
check("a confident answer is believed",
      categorize.classify("Go for a 5k run")["category"] == "heal")
reply(answers(potion="heal", probabilities=sure(config.POTION_CONFIDENCE_MIN)))
check("the threshold itself counts as confident",
      categorize.classify("Go for a 5k run")["category"] == "heal")
reply(answers(potion="heal", probabilities=sure(0.2)))
check("an unsure answer is overruled, and the keywords win",
      categorize.classify("Go for a 5k run")["category"] == "damage")
reply(answers(potion="heal",
              probabilities={c: 0.25 for c in config.POTION_CATEGORIES}))
check("a flat four-way tie is not confidence",
      categorize.classify("Go for a 5k run")["category"] == "damage")
check("a title matching nothing falls to the default, not to a guess",
      categorize.classify("zzz qqq")["category"] == config.DEFAULT_CATEGORY)

section("a malformed distribution is never read as certainty")
# Fail-safe, not fail-open. A distribution we cannot read means we do not know
# how sure the model was, and the safe reading of "we do not know" is that the
# keywords decide. Treating it as confident would restore the old bug for any
# proxy that reshapes its answers.
reply(answers(potion="heal"))
check("no probabilities at all is not confidence",
      categorize.classify("Go for a 5k run")["category"] == "damage")
reply(answers(potion="heal", probabilities="not a dict"))
check("a non-dict distribution is not confidence",
      categorize.classify("Go for a 5k run")["category"] == "damage")
reply(answers(potion="heal", probabilities={"damage": 0.9, "heal": True}))
check("a boolean probability is not a probability",
      categorize.classify("Go for a 5k run")["category"] == "damage")
reply(answers(potion="heal", probabilities={"damage": 0.9}))
check("a distribution that omits the chosen option is not confidence",
      categorize.classify("Go for a 5k run")["category"] == "damage")

section("the gate moves the potion and never the reward")
# `kind` is the player's to override now, so the gate applies only to the
# potion category. Difficulty flows through untouched, which is what keeps
# confidence from being a lever on payout.
for probability in (0.0, 1.0):
    reply(answers(potion="damage", score=TOP, probabilities=sure(probability)))
    v = categorize.classify("Go for a 5k run")
    check(f"confidence {probability} leaves the effort score alone",
          v["difficulty"] == 1.0, str(v["difficulty"]))
    check(f"confidence {probability} leaves the reward at the maximum",
          categorize.potions_for(v["difficulty"]) == config.POTION_MAX)

section("every malformed response still yields a usable verdict")
reply({"unexpected": True})
check("a reshaped response does not raise",
      categorize.classify("Review the contract")["category"] == "shield")
reply({"answers": {}})
check("an empty answer set does not raise",
      categorize.classify("Review the contract")["category"] == "shield")
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
check("keywords still answer", v["category"] == "damage", str(v["category"]))
check("the repeat window falls back", v["kind"] == config.DEFAULT_KIND, v["kind"])
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

section("the player may correct the repeat window, and only that")
# The model guessed `goal` for a 5k run at 53% confidence, and `goal` is the one
# window that cannot be walked back: game.period_start returns datetime.min for
# it, so the quest can never be banked a second time. Letting the player fix it
# is the whole point — but it must stay a correction, not a new input to the
# reward.
reply(answers(potion="shield", kind="daily", score=TOP, probabilities=sure(0.95)))
quest = client.post("/api/tasks", json={"title": "Review the contract"}).json()
before = quest["potions"]

patched = client.patch(f"/api/tasks/{quest['id']}", json={"kind": "goal"})
check("a valid window is accepted", patched.status_code == 200, patched.text[:200])
check("the window actually changed", patched.json()["kind"] == "goal",
      patched.json()["kind"])
check("the reward did not move with it", patched.json()["potions"] == before,
      f"{before} -> {patched.json()['potions']}")
check("the potion did not move with it", patched.json()["potion"] == quest["potion"])
check("it persists", client.get("/api/tasks").json()[-1]["kind"] == "goal")

check("an invented window is refused cleanly",
      client.patch(f"/api/tasks/{quest['id']}", json={"kind": "fortnightly"}).status_code == 400)
check("a missing window is refused cleanly",
      client.patch(f"/api/tasks/{quest['id']}", json={}).status_code == 422)

# The other half of the anti-cheat property. The create body has no `kind`
# attribute for pydantic to bind to, so a posted one is dropped, not stored —
# which is why correcting the window needs its own route rather than a second
# create field.
forced = client.post("/api/tasks", json={"title": "Go for a 5k run", "kind": "goal",
                                        "potions": 99, "difficulty": 1.0}).json()
check("a posted window on create is still ignored",
      forced["kind"] in game.KINDS and forced["kind"] != "goal", forced["kind"])

section("one player cannot touch another's quest")
client.post("/logout")
client.post("/login", data={"username": "d", "password": "pass1", "action": "register"})
check("another player's quest is not found",
      client.patch(f"/api/tasks/{quest['id']}", json={"kind": "goal"}).status_code == 404)
check("and it is not reported as forbidden either, which would confirm it exists",
      client.patch(f"/api/tasks/{quest['id']}", json={"kind": "daily"}).status_code == 404)
client.post("/logout")
client.post("/login", data={"username": "c", "password": "pass1"})

print("\n" + "=" * 60)
categorize.urllib.request.urlopen = real_urlopen
config.CLASSIFIER_API_KEY = saved_key
if failures:
    print(f"FAILED: {len(failures)} check(s): {failures}")
    raise SystemExit(1)
print("All checks passed.")