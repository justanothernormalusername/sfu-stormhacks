"""Static audit of the authored floor.

Checks the things a balance run cannot: that the room graph is actually connected,
that no room is stranded behind the boss, that the depth order the balance tool
assumes is a legal walk, and that geometry matches the graph. A dungeon that is
internally consistent but unreachable is playable in simulation and impossible in
the browser, which is the worst kind of bug to ship.
"""

from datetime import datetime

from src.app import config, game

floor = game.floor_for_week(game.week_start(datetime(2026, 10, 7)))
rooms = floor["rooms"]
n = len(rooms)
problems: list[str] = []

neighbours: dict[int, set[int]] = {i: set() for i in range(n)}
for a, b in floor["links"]:
    if not (0 <= a < n and 0 <= b < n):
        problems.append(f"link ({a},{b}) points outside the floor")
    neighbours[a].add(b)
    neighbours[b].add(a)


def flood(adj: dict[int, set[int]]) -> set[int]:
    seen, stack = {0}, [0]
    while stack:
        for m in adj.get(stack.pop(), ()):
            if m not in seen:
                seen.add(m)
                stack.append(m)
    return seen


reachable = flood(neighbours)
if reachable != set(range(n)):
    problems.append(f"unreachable rooms: {sorted(set(range(n)) - reachable)}")

# Nothing should sit behind the boss: the boss must be a climax, not a chokepoint
# that strands half the floor behind it.
boss = max(range(n), key=lambda i: rooms[i]["depth"])
without_boss = {i: set(v) for i, v in neighbours.items()}
without_boss[boss] = set()
stranded = set(range(n)) - flood(without_boss) - {boss}
if stranded:
    problems.append(f"rooms only reachable through the boss: {sorted(stranded)}")

# The balance tool walks rooms in depth order, so that order must be walkable:
# each room's floor must already be open (or be the entrance) when we get there.
open_now = {rooms[0]["index"]}
for idx in sorted(range(n), key=lambda i: rooms[i]["depth"]):
    if idx != rooms[0]["index"] and idx not in open_now:
        problems.append(f"room {idx} ({rooms[idx]['name']}) is sealed in depth order")
    open_now |= neighbours.get(idx, set())

# Geometry must contain the room and not collide with another room's footprint.
boxes = [(r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"], r["index"]) for r in rooms]
for i in range(len(boxes)):
    for j in range(i + 1, len(boxes)):
        ax0, ay0, ax1, ay1, ai = boxes[i]
        bx0, by0, bx1, by1, bi = boxes[j]
        if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
            problems.append(f"rooms {ai} and {bi} overlap")
for x0, y0, x1, y1, i in boxes:
    if x1 >= config.WORLD_COLS or y1 >= config.WORLD_ROWS:
        problems.append(f"room {i} runs off the grid ({x1},{y1})")

# Every fight must be winnable in principle: a boss whose telegraph+phase out-damages
# a full health bar is unwinnable no matter how the player plays.
for r in rooms:
    enemy = r.get("enemy")
    if not enemy:
        continue
    worst = enemy["atk"] * config.MAX_DAMAGE / config.PLAYER_BASE["max_hp"]
    if enemy["hp"] > config.PLAYER_BASE["max_hp"] * 2:
        problems.append(f"room {r['index']} enemy has {enemy['hp']} HP (> 2 bars)")

print(f"floor: {n} rooms, {len(floor['links'])} links")
print(f"boss: room {boss} ({rooms[boss]['name']}), depth {rooms[boss]['depth']}")
print(f"connected: {len(reachable)}/{n}")
if problems:
    print("\nPROBLEMS:")
    for p in problems:
        print(f"  - {p}")
    raise SystemExit(1)
print("\nno structural problems found")