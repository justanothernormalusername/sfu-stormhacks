"""Score the live classifier against the golden set. Opt-in — never in the gate.

    CLASSIFIER_API_KEY=... PYTHONPATH=. .venv/bin/python tools/score_classifier.py

Two things only a real model can answer, and `tests/test_classifier_golden.py`
cannot touch either:

1. **Did the criteria rewrite help?** `POTION_CATEGORY_CRITERIA` are strings the
   model reads and picks between. Change them and nothing offline moves, so
   "it is better now" is currently unfalsifiable. Run this before a change and
   after it — a single after-run tells you nothing without the baseline.
2. **Where should `POTION_CONFIDENCE_MIN` sit?** The answer distribution this
   prints is what separates "the model is right and sure" from "the model is
   guessing". Print it, then choose a threshold that separates them rather than
   one that looks round.

Also prints how often the keyword table and the model disagree, which is the
population the confidence gate is actually deciding about.

Deliberately a standalone script, and deliberately NOT in `run_tests.sh`: the
test suites set `CLASSIFIER_API_KEY=""` so a developer's key cannot make them
make live network calls. A tool in the gate that ignores that would defeat the
point. Read this output as a report; the model is non-deterministic, so it must
never be the thing that fails a commit.
"""

import os
import sys

if not os.environ.get("CLASSIFIER_API_KEY"):
    sys.exit(
        "CLASSIFIER_API_KEY is not set.\n"
        "This script makes live calls on purpose. The test suites set it to an\n"
        "explicitly empty value to switch the classifier OFF — leave that alone."
    )

sys.path.insert(0, ".")

from src.app import categorize, config  # noqa: E402
from tests.fixtures.classifier_cases import CASES  # noqa: E402

print(f"model:  {config.CLASSIFIER_MODEL}")
print(f"url:    {config.CLASSIFIER_URL}")
print(f"gate:   POTION_CONFIDENCE_MIN = {config.POTION_CONFIDENCE_MIN}")
print(f"titles: {len(CASES)}\n")

rows = []
for title, expected in CASES:
    answers = categorize._from_classifier(title)
    raw = answers.get("potion_raw")
    got = categorize._valid(answers.get("potion"), config.POTION_CATEGORIES)
    probs = raw.get("probabilities") if isinstance(raw, dict) else None
    top = probs.get(got) if isinstance(probs, dict) and got else None
    rows.append((title, expected, got, top, categorize._from_keywords(title)))
    # Space out requests: the endpoint is a shared free proxy, and hammering it
    # would produce rate-limit noise that reads like classifier error.
    print(".", end="", flush=True)

print("\n")
header = f"{'title':<30} {'want':<7} {'model':<7} {'p':>5}  {'keywords':<7} "
print(header)
print("-" * len(header))
for title, expected, got, top, keyword in rows:
    mark = " " if got == expected else "X"
    conf = f"{top:.2f}" if isinstance(top, (int, float)) else "  - "
    print(f"{mark} {title:<28} {expected:<7} {str(got):<7} {conf:>5}  "
          f"{str(keyword):<7}")

by_category: dict[str, list[bool]] = {c: [] for c in config.POTION_CATEGORIES}
for _title, expected, got, _top, _kw in rows:
    by_category[expected].append(got == expected)

correct = sum(1 for _t, e, g, _p, _k in rows if e == g)
print(f"\nmodel agrees with the golden set: {correct}/{len(rows)}"
      f"  ({100 * correct / len(rows):.0f}%)")

print("\nper category:")
for category, outcomes in by_category.items():
    if outcomes:
        print(f"  {category:<8} {sum(outcomes)}/{len(outcomes)}")

# The distribution is what picks the gate. Sorted so a threshold can be read
# off it directly rather than guessed.
measured = sorted((p for _t, _e, _g, p, _k in rows
                   if isinstance(p, (int, float))), reverse=True)
print("\nconfidence on the chosen potion, highest first:")
print("  " + "  ".join(f"{p:.2f}" for p in measured))

# What the gate actually changes: cases where the keyword table disagrees with
# the model. Those are the only titles where POTION_CONFIDENCE_MIN has any say,
# so if this number is near zero the gate is doing nothing either way.
split = [r for r in rows if r[2] is not None and r[4] is not None and r[2] != r[4]]
print(f"\nmodel and keywords disagree on {len(split)} of {len(rows)} titles")
print(f"  of those, the model is right {sum(1 for r in split if r[2] == r[1])} times"
      f" and keywords are right {sum(1 for r in split if r[4] == r[1])} times")
print("\nThat last line is the gate's justification. If keywords win often,")
print("POTION_CONFIDENCE_MIN is set wrong and should move toward whichever")
print("side is winning.")