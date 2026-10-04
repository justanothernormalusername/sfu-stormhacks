#!/usr/bin/env bash
# Run the checks that gate a change.
#
# The combat rewrite moved every rule server-side, so "it imports" is not evidence
# of anything. These checks cover the claims that matter: the exploit is closed,
# edge cases return clean errors rather than 500s, concurrent requests cannot
# double-spend, the floor is connected, death and fleeing behave correctly, and
# the classifier's two real properties — the reward stays bounded, and a title
# maps to the potion a person would expect — both hold.
#
# test_classifier.py and test_classifier_golden.py were not in this gate until the
# classifier rewrite, which is most of why "it defaults too often to heal" sat
# there unnoticed: nothing in the suite asserted that any title produced the right
# answer. Keep both in here. They set CLASSIFIER_API_KEY to an explicitly empty
# value so a developer's key cannot make them make live calls.
#
# Deliberately not included: tools/balance.py and tools/score_classifier.py. Both
# are long or need a network. Run balance.py by hand after touching anything in the
# PLAYER_, POTION_, ENEMY_, or ROOM_ARCHETYPES blocks in config.py, and
# score_classifier.py when you change POTION_CATEGORY_CRITERIA.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH=.
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3

status=0
for suite in tests/test_combat.py tests/test_classifier.py tests/test_classifier_golden.py \
             tests/test_bugs.py tests/test_race.py tests/audit_floor.py tests/test_reset.py; do
  echo
  echo "=============================================================="
  echo "  $suite"
  echo "=============================================================="
  if ! "$PY" "$suite"; then
    status=1
    echo "^^^ FAILED: $suite"
  fi
done

if command -v node >/dev/null 2>&1; then
  node tests/test_spawns.cjs || status=1
else
  echo "Skipping scene transition checks: Node.js is not installed."
fi

echo
if [ "$status" -eq 0 ]; then
  echo "All suites passed."
else
  echo "One or more suites failed."
fi
exit "$status"
