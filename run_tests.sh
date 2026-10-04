#!/usr/bin/env bash
# Run the checks that gate a change.
#
# The combat rewrite moved every rule server-side, so "it imports" is not evidence
# of anything. These checks cover the claims that matter: the exploit is closed,
# edge cases return clean errors rather than 500s, concurrent requests cannot
# double-spend, the floor is connected, and death and fleeing behave correctly.
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
for suite in tests/test_combat.py tests/test_bugs.py tests/test_race.py tests/audit_floor.py tests/test_reset.py; do
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
