#!/usr/bin/env bash
# Run the checks that gate a change.
#
# The combat rewrite moved every rule server-side, so "it imports" is not evidence
# of anything. These four cover the claims that matter: the exploit is closed,
# edge cases return clean errors rather than 500s, concurrent requests cannot
# double-spend, and the authored floor is actually connected and walkable.
#
# Deliberately not included: tools/balance.py. It is a ~2 minute Monte-Carlo run
# with pass/fail bands, not a fast gate. Run it by hand after touching anything in
# the PLAYER_, POTION_, ENEMY_, or ROOM_ARCHETYPES blocks in config.py.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH=.
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3

status=0
for suite in tests/test_combat.py tests/test_bugs.py tests/test_race.py tests/audit_floor.py; do
  echo
  echo "=============================================================="
  echo "  $suite"
  echo "=============================================================="
  if ! "$PY" "$suite"; then
    status=1
    echo "^^^ FAILED: $suite"
  fi
done

echo
if [ "$status" -eq 0 ]; then
  echo "All suites passed."
else
  echo "One or more suites failed."
fi
exit "$status"