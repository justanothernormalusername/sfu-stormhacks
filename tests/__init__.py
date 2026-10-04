"""Test and analysis scripts.

These are plain runnable scripts rather than pytest — each one prints what it
found, and several of them (trace_hp, where_do_they_die, tune_boss) exist to answer
a balance question that was open when they were written, not to gate a commit.

Run them from the repo root with PYTHONPATH set so `src` and `tools` import:

    PYTHONPATH=. .venv/bin/python tests/test_combat.py
    PYTHONPATH=. .venv/bin/python tests/test_bugs.py
    PYTHONPATH=. .venv/bin/python tests/test_race.py
    PYTHONPATH=. .venv/bin/python tests/audit_floor.py
    PYTHONPATH=. .venv/bin/python tests/floor_run.py

or just `./run_tests.sh`, which runs the four that gate changes.
"""

import sys
from pathlib import Path

# Make `src` and `tools` importable however the script was invoked. Without this,
# running a file inside tests/ directly (rather than as `python -m tests.x`) puts
# tests/ on sys.path instead of the repo root, and `import src.app` fails.
ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)