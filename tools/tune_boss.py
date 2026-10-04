"""Sweep boss HP to hit the win-rate target, without re-running the whole report.

tools/balance.py takes ~100s per configuration because it plays every potion
budget and every policy. This plays only what matters for this decision — the
boss fight at a three-potion budget — across a range of HP caps, so the value
can be chosen from measured win rates instead of guessed and re-measured.

    PYTHONPATH=. .venv/bin/python tune_boss.py
"""

from datetime import datetime, timedelta

from src.app import config, game
from tools.balance import _split_potions, hero, play_room

WEEK = datetime(2026, 10, 5, 12, 0)
POTIONS = 3
RUNS = 400
LO, HI = 120, 165
TARGET = (0.55, 0.85)

base_cap = config.ROOM_ARCHETYPES["boss"]["hp_cap"]
if base_cap is None:
    # The sweep below assigns concrete numbers, so it is measuring a capped boss
    # even when the live game is unbounded. Say so rather than letting the
    # restored value quietly mean something different from what is deployed.
    print("note: BOSS_HP_CAP is currently unbounded; this sweep is measuring "
          "capped values only.")
elif base_cap != config.DEFAULT_BOSS_HP_CAP:
    print(f"note: BOSS_HP_CAP is overridden to {base_cap} "
          f"(default {config.DEFAULT_BOSS_HP_CAP}); sweeping anyway.")


def boss_at(hp_cap: int) -> dict:
    """A boss room whose enemy HP reflects `hp_cap`.

    The floor must be rebuilt for each cap: `floor_for_week` applies the cap when
    it draws the enemy, so reusing one already-built room silently pins every
    value at or above the current cap and makes the sweep look flat. That bug made
    the first run report an identical 71% for every cap from 138 to 165.
    """
    config.ROOM_ARCHETYPES["boss"]["hp_cap"] = hp_cap
    floor = game.floor_for_week(WEEK)
    room = next(r for r in floor["rooms"] if r["kind"] == "boss")
    return room


def win_rate(hp_cap: int, arrival_hp: int) -> float:
    room = boss_at(hp_cap)
    wins = 0
    for seed in range(RUNS):
        result = play_room(room, hero(hp=arrival_hp), _split_potions(POTIONS),
                           "reader", f"boss|{hp_cap}|{seed}")
        wins += result["state"] == "won"
    return wins / RUNS


# Average HP a player actually arrives with, from where_do_they_die.py. Using the
# real number matters: tuning the boss against a full health bar produces a cap
# that is far too generous in play.
ARRIVAL = int(input("arrival HP (default 36): ").strip() or 36)

print(f"boss win rate at {POTIONS} potions, arriving at {ARRIVAL}/{config.PLAYER_BASE['max_hp']} HP")
print(f"{'hp_cap':>7}  {'win rate':>9}  {'in target':>10}")
best = None
for cap in range(LO, HI + 1, 3):
    rate = win_rate(cap, ARRIVAL)
    ok = TARGET[0] <= rate <= TARGET[1]
    print(f"{cap:7d}  {rate:8.1%}  {'yes' if ok else '':>10}")
    if ok and best is None:
        best = cap

config.ROOM_ARCHETYPES["boss"]["hp_cap"] = base_cap
print(f"\nfirst cap in target band: {best}")