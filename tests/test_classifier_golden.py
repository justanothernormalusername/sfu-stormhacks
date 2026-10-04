"""Does a title map to the potion a person would expect?

Every other classifier test proves that whatever verdict arrives is *used*
correctly — bounded, validated, stored. Not one of them proves that any verdict
is *right*. That gap is why "it defaults too often to heal" could sit there
undetected: an implementation that always answered `heal` would have passed
every other assertion in the suite.

So this suite pins the semantics instead. It runs **offline**, with the
classifier switched off, which means what it actually exercises is
`categorize._from_keywords` plus the config invariants. That is not a
weakness to apologise for — it is the path the game takes every time the model
is unsure, which after the confidence gate is a far more travelled road than it
used to be.

It cannot measure `POTION_CATEGORY_CRITERIA`, because those strings exist only
for the model to read. `tools/score_classifier.py` is the other half and it
needs a key. Two tiers, one table, from `tests/fixtures/classifier_cases.py`.

    PYTHONPATH=. .venv/bin/python tests/test_classifier_golden.py
"""

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/golden.db"
os.environ["SECRET_KEY"] = "x"
# Explicitly empty, which beats a developer's .env — see config._classifier_key.
# Do not remove this line: a real key here would make this suite make live
# network calls and assert on whatever the model decided today.
os.environ["CLASSIFIER_API_KEY"] = ""

from src.app import categorize, config, game  # noqa: E402
from tests.fixtures.classifier_cases import CASES, MISSES  # noqa: E402

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        failures.append(name)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


section("the game's own vocabularies agree with each other")
# These are not style nits. `/api/config` reads attributes by name, and the
# quest board indexes KIND_GLYPH with a kind coming out of the database — so a
# key set that drifts is a 500 on the page the game boots against, or a row
# that renders as `undefined`.
check("potion criteria cover exactly the potion categories",
      sorted(config.POTION_CATEGORY_CRITERIA) == sorted(config.POTION_CATEGORIES))
check("keyword fallbacks cover exactly the potion categories",
      sorted(config.POTION_CATEGORY_KEYWORDS) == sorted(config.POTION_CATEGORIES))
check("every kind vocabulary agrees with the game's kinds",
      sorted(config.KIND_CRITERIA) == sorted(config.KIND_LABEL)
      == sorted(config.KIND_GLYPH) == sorted(game.KINDS))
check("every potion effect covers exactly the potion categories",
      sorted(config.POTION_EFFECTS) == sorted(config.POTION_CATEGORIES))
check("no keyword is listed twice in one category",
      all(len(words) == len(set(words))
          for words in config.POTION_CATEGORY_KEYWORDS.values()))
check("every keyword is a real category",
      all(cat in config.POTION_CATEGORIES
          for cat in config.POTION_CATEGORY_KEYWORDS))
check("a keyword is never claimed by two categories",
      all(len({cat for cat, words in config.POTION_CATEGORY_KEYWORDS.items()
               if word in words}) <= 1
          for words in config.POTION_CATEGORY_KEYWORDS.values()
          for word in words),
      "a word in two lists makes the answer depend on declaration order")
check("every category has enough vocabulary to be reachable",
      all(len(words) >= 10 for words in config.POTION_CATEGORY_KEYWORDS.values()),
      str({c: len(w) for c, w in config.POTION_CATEGORY_KEYWORDS.items()}))

section("a title categorises the way a person would expect")
for title, expected in CASES:
    got = categorize._from_keywords(title)
    check(f"{title!r} -> {expected}", got == expected, f"got {got}")

section("a miss stays a miss, instead of quietly becoming the default")
# DEFAULT_CATEGORY is "heal". When _from_keywords answered it directly, every
# unrecognised title became a heal potion — which is exactly the bias this
# suite exists to pin shut. These rows fail if that behaviour ever returns,
# including via some new catch-all added to a keyword list.
for title in MISSES:
    got = categorize._from_keywords(title)
    check(f"{title!r} is not forced into a category", got is None, f"got {got}")
check("and classify() still returns a real category for a miss",
      categorize.classify("zzz qqq")["category"] == config.DEFAULT_CATEGORY)

section("whole words, not substrings")
# This was the original silent bug: `"rest" in "restaurant"` and
# `"eat" in "meeting"`, so a dinner out and a work meeting both paid heal.
# Covered behaviourally in MISSES above; these pin the mechanism.
check('"rest" does not match "restaurant"',
      categorize._from_keywords("visit the restaurant on friday") is None)
check('"eat" does not match "meeting"',
      categorize._from_keywords("attend the meeting") is None)
check("a word still matches when it really is the word",
      categorize._from_keywords("eat dinner") == "heal")
check("a plural still matches its singular",
      categorize._from_keywords("answer emails") == "haste")
check("a possessive is still its stem",
      categorize._from_keywords("clean the dog's kennel") is not None)

section("coverage is broad enough that titles do not all fall through")
# The failure mode was quantitative — 14 of 20 everyday titles matched nothing —
# so this is measured rather than spot-checked.
sample = [title for title, _ in CASES]
covered = sum(1 for title in sample if categorize._from_keywords(title) is not None)
check("every fixture title is covered", covered == len(sample),
      f"{covered}/{len(sample)}")
# Every category must be reachable, or one potion would be dead content.
reached = {categorize._from_keywords(t) for t, _ in CASES}
check("all four potions are reachable from the fixture",
      reached == set(config.POTION_CATEGORIES), str(sorted(reached)))

print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} check(s): {failures}")
    raise SystemExit(1)
print("All checks passed.")