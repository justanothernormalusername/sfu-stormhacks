"""Trace HP along a single run, room by room.

The clear rates stopped responding to the shrine change, which is suspicious: 58
should visibly move a health bar that was arriving at 30/125. This prints the HP
after every room on the critical path for one seed, so it is obvious whether the
shrine is being applied at all.
"""

from datetime import datetime

from src.app import config, game
from tools.balance import _split_potions, hero, play_room

WEEK = datetime(2026, 10, 5, 12, 0)
POTIONS = 4
SEED = 1

floor = game.floor_for_week(WEEK)
rooms = floor["rooms"]
path = sorted(range(len(rooms)), key=lambda i: rooms[i]["depth"])

hero_state = hero()
spent: dict[str, int] = {}
print(f"start: {hero_state['hp']}/{hero_state['max_hp']} HP, "
      f"{POTIONS} potions\n")
for idx in path:
    room = rooms[idx]
    before = hero_state["hp"]
    if room["safe"]:
        if room["restore"]:
            hero_state["hp"] = min(hero_state["max_hp"],
                                   hero_state["hp"] + room["restore"])
        print(f"  {room['name'][:26]:28s} SAFE   "
              f"{before:3d} -> {hero_state['hp']:3d} HP  (+{room['restore'] or 0})")
        continue
    budget = max(0, POTIONS - sum(spent.values()))
    potions = _split_potions(budget)
    state = play_room(room, hero_state, potions, "reader",
                      f"{SEED}|{WEEK:%Y-%m-%d}|{idx}")
    for category, offered in potions.items():
        left = max(0, offered - state["potions"].get(category, 0))
        spent[category] = spent.get(category, 0) + left
    hero_state["hp"] = (state["hero"]["hp"] if state["state"] == "won"
                        else config.PLAYER_BASE["max_hp"])
    print(f"  {room['name'][:26]:28s} {state['state'].upper():5s} "
          f"{before:3d} -> {hero_state['hp']:3d} HP  "
          f"({state['turn']} turns, potions left {sum(state['potions'].values())})")
    if state["state"] == "lost":
        break