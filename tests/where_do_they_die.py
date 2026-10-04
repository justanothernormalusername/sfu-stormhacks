"""Where do runs actually die?

The clear-rate numbers say the floor is too hard but not *where*. This walks the
critical path with the balance tool's own policy and reports which room kills
players and how much health they have left when they reach the boss — which is
the number that decides whether the boss difficulty is the real problem or just
the last straw after an attrited health bar.
"""

from collections import Counter
from datetime import datetime

from src.app import config, game
from tools.balance import _split_potions, hero, play_room

WEEK = datetime(2026, 10, 5, 12, 0)
POTIONS = 4
RUNS = 200

floor = game.floor_for_week(WEEK)
rooms = floor["rooms"]
path = sorted(range(len(rooms)), key=lambda i: rooms[i]["depth"])

deaths: Counter = Counter()
hp_at_boss: list[int] = []
reached = 0

for seed in range(RUNS):
    hero_state = hero()
    spent: dict[str, int] = {}
    for idx in path:
        room = rooms[idx]
        if room["safe"]:
            if room["restore"]:
                hero_state["hp"] = min(hero_state["max_hp"],
                                       hero_state["hp"] + room["restore"])
            continue
        budget = max(0, POTIONS - sum(spent.values()))
        potions = _split_potions(budget)
        state = play_room(room, hero_state, potions, "reader",
                          f"{seed}|{WEEK:%Y-%m-%d}|{idx}")
        for category, offered in potions.items():
            left = max(0, offered - state["potions"].get(category, 0))
            spent[category] = spent.get(category, 0) + left
        if state["state"] == "lost":
            deaths[f"{room['name']} (depth {room['depth']})"] += 1
            break
        hero_state["hp"] = state["hero"]["hp"]
        if room["kind"] == "boss":
            reached += 1
            hp_at_boss.append(hero_state["hp"])

print(f"deaths by room ({RUNS} runs, {POTIONS} potions):")
for name, count in deaths.most_common():
    print(f"  {count:4d}  {name}")
print(f"\nboss reached {reached}/{RUNS}")
if hp_at_boss:
    avg = sum(hp_at_boss) / len(hp_at_boss)
    print(f"HP on arrival at the boss: avg {avg:.0f} / {config.PLAYER_BASE['max_hp']}"
          f"  ({avg / config.PLAYER_BASE['max_hp']:.0%} of the bar)")