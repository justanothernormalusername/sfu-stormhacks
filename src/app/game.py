"""Game rules. Everything that decides a floor's contents, a room's contents, a
potion's category, or the outcome of a single turn of combat lives here,
server-side, so the game client only renders results.

Every function here is pure — no database, no network, no clock, no randomness
that is not derived from an explicit seed — so the rules are unit-testable on
their own, and so `tools/balance.py` can simulate a thousand weeks of dungeon
runs in a second to tune the numbers in config.py.

Combat in particular is a pure reducer: `fight_step(state, action) -> state`.
It carries no hidden state and reads nothing global, which is what makes it safe
to replay on the server instead of trusting the browser.
"""

import os
import random
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import categorize, config
from .models import Completion, Task

KINDS = ("daily", "monthly", "goal")
# Day/month/week boundaries follow the players' local clock, not UTC (UTC
# midnight is 5pm in Vancouver).
TZ = ZoneInfo(os.environ.get("APP_TZ", "America/Vancouver"))


def to_local(utc_naive: datetime) -> datetime:
    """Timestamps are stored as naive UTC; convert one to the game's local time."""
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(TZ)


def local_date(utc_naive: datetime) -> date:
    return to_local(utc_naive).date()


def period_start(kind: str, now: datetime) -> datetime:
    """Start (as naive UTC) of the window in which a completion counts for this task."""
    local = to_local(now)
    if kind == "daily":
        start = datetime(local.year, local.month, local.day, tzinfo=TZ)
    elif kind == "monthly":
        start = datetime(local.year, local.month, 1, tzinfo=TZ)
    else:
        return datetime.min  # goals: done once, ever
    return to_utc(start)


def week_start(now: datetime) -> datetime:
    """Start (as naive UTC) of the week containing `now`, at local midnight.

    The weekly dungeon and the weekly potion window both reset here.

    The local week-start is found by walking back day-by-day rather than
    subtracting a timedelta, so each intermediate midnight is resolved by the tz
    database instead of by arithmetic that can land on a nonexistent local time.
    The count is taken modulo 7 because it must wrap: with a Sunday week start, a
    Monday is *six* days back, not -1 (which an unguarded subtraction turns into
    a no-op and silently returns the wrong week).
    """
    local = to_local(now)
    midnight = datetime(local.year, local.month, local.day, tzinfo=TZ)
    back = (local.weekday() - config.WEEK_START_DAY) % 7
    for _ in range(back):
        midnight -= timedelta(days=1)
    return to_utc(midnight)


def week_start_label(start: datetime) -> str:
    """A short human label for a week boundary, for the HUD."""
    return to_local(start).strftime("%b %d")


def to_utc(local: datetime) -> datetime:
    """Convert an aware local datetime to the naive UTC we store.

    NOTE: the bundled tzdata (IANA 2026e) lists America/Vancouver's last
    fall-back transition as 2026-11-01 UTC-7 — summer time, the wrong sign — and
    its POSIX footer past that point is a bare "7". Every date from 2026-11-01
    onward therefore reports UTC-7 instead of UTC-8, which shifts the weekly
    reset by an hour. Zone-aware arithmetic below is correct for all dates up to
    the table's horizon; beyond it the offset is stale. Fix by upgrading tzdata
    (`pip install -U tzdata`), which carries the corrected rule.
    """
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def completion_in_period(task: Task, completions: list[Completion], now: datetime) -> Completion | None:
    start = period_start(task.kind, now)
    current = [c for c in completions if c.task_id == task.id and c.completed_at >= start]
    return max(current, key=lambda c: c.completed_at) if current else None


# --- The floor -------------------------------------------------------------

def _carve(grid: list[list[str]], x0: int, y0: int, x1: int, y1: int) -> None:
    for y in range(min(y0, y1), max(y0, y1) + 1):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            grid[y][x] = "."


def _carve_link(grid: list[list[str]], a: dict, b: dict) -> None:
    """Carve an L-shaped corridor between two room centres, room edges included.

    The midpoint is shared between the two legs so they meet rather than leaving
    a diagonal gap, and corridors are carved after room floors so a corridor
    always punches through a room wall instead of being swallowed by one.
    """
    ax, ay = a["cx"], a["cy"]
    bx, by = b["cx"], b["cy"]
    mid_x, mid_y = (ax + bx) // 2, (ay + by) // 2
    if ax == bx or ay == by:
        _carve(grid, ax, ay, bx, by)
    else:
        _carve(grid, ax, ay, mid_x, ay)
        _carve(grid, mid_x, ay, mid_x, by)
        _carve(grid, mid_x, by, bx, by)


def _enemies_for_room(seed: random.Random, arch: dict, depth: int,
                      modifier: dict) -> dict | None:
    """The occupant of a room, or None for a safe room.

    Stats come from the depth curve scaled by the archetype and then by this
    week's modifier, so difficulty is a function of where you are in the floor
    rather than of a flat per-tier table.
    """
    if arch["safe"]:
        return None
    hp = round((config.ENEMY_HP["base"] + config.ENEMY_HP["per_depth"] * depth)
               * arch["hp_mult"] * modifier["hp_mult"])
    atk = round((config.ENEMY_ATK["base"] + config.ENEMY_ATK["per_depth"] * depth)
                * arch["atk_mult"] * modifier["atk_mult"])
    # An archetype may cap its HP. This is what keeps a long fight from becoming
    # an unlosable-by-skill one: past a certain length, every turn the enemy acts
    # is more damage than the player can regenerate in the same time, and the
    # only "solution" is a potion — which means the potions stop being a choice
    # and become the answer. See ROOM_ARCHETYPES["boss"]["hp_cap"].
    cap = arch.get("hp_cap")
    return {
        "name": seed.choice(config.ENEMY_NAMES[arch["tier"]]),
        "tier": arch["tier"],
        "hp": max(1, min(hp, cap) if cap else hp),
        "atk": max(1, atk),
        "depth": depth,
    }


def floor_for_week(week_start_dt: datetime) -> dict:
    """The whole dungeon for one week. Identical for every player.

    The *layout* is authored in config.FLOOR_ROOMS — a dungeon is a designed
    sequence of beats, and a generator that shuffles twelve rooms in a row is not
    one. What this draws from the week seed is what a player shouldn't expect to
    be identical twice: creature names, flavour text, and the weekly modifier.
    So the map is a place you learn, and the week is a surprise.

    Returns the map plus every room's contents, so the client renders what the
    server decided and the tests can walk the layout without a browser.
    """
    seed = random.Random(f"{week_start_dt.isoformat()}|{config.FLOOR_NAME}")
    weights = [m["weight"] for m in config.WEEKLY_MODIFIERS]
    modifier = seed.choices(list(config.WEEKLY_MODIFIERS), weights=weights, k=1)[0]

    rooms: list[dict] = []
    for index, (name, kind, x, y, w, h, depth) in enumerate(config.FLOOR_ROOMS):
        arch = config.ROOM_ARCHETYPES[kind]
        enemy = _enemies_for_room(seed, arch, depth, modifier)
        room = {
            "index": index,
            "name": name,
            "kind": kind,
            "tier": arch["tier"],
            "safe": arch["safe"],
            "x": x, "y": y, "w": w, "h": h,
            "cx": x + w // 2, "cy": y + h // 2,
            "depth": depth,
            "flavor": seed.choice(config.ROOM_FLAVOR[kind]),
            "blurb": arch["blurb"],
            "restore": arch.get("restore"),
            "enemy": enemy,
        }
        if enemy and enemy["tier"] in ("boss", "mini-boss"):
            profile = config.BOSS if enemy["tier"] == "boss" else config.MINI_BOSS
            enemy["title"] = (seed.choice(config.BOSS_TITLES)
                              if enemy["tier"] == "boss" else None)
            enemy["profile"] = dict(profile)
        rooms.append(room)

    # Room floors first, corridors second, so a corridor always wins on a tie.
    grid = [["#"] * config.WORLD_COLS for _ in range(config.WORLD_ROWS)]
    for room in rooms:
        _carve(grid, room["x"], room["y"], room["x"] + room["w"] - 1, room["y"] + room["h"] - 1)
    for a, b in config.FLOOR_LINKS:
        _carve_link(grid, rooms[a], rooms[b])

    return {
        "name": config.FLOOR_NAME,
        "theme": config.FLOOR_THEME,
        "week_start": week_start_dt.isoformat(),
        "week_label": week_start_label(week_start_dt),
        "cols": config.WORLD_COLS,
        "rows": config.WORLD_ROWS,
        "grid": ["".join(row) for row in grid],
        "rooms": rooms,
        "links": [list(pair) for pair in config.FLOOR_LINKS],
        "modifier": {"name": modifier["name"], "blurb": modifier["blurb"]},
    }


def reachable_tiles(floor: dict) -> set[tuple[int, int]]:
    """Flood fill over open tiles from the entrance. Exported so tests can assert
    the layout is actually playable and not just internally consistent."""
    grid = floor["grid"]
    start = (floor["rooms"][0]["cx"], floor["rooms"][0]["cy"])
    seen, stack = {start}, [start]
    while stack:
        x, y = stack.pop()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (0 <= nx < floor["cols"] and 0 <= ny < floor["rows"]
                    and grid[ny][nx] != "#" and (nx, ny) not in seen):
                seen.add((nx, ny))
                stack.append((nx, ny))
    return seen


# --- Combat -----------------------------------------------------------------
# A fight is a plain dict that round-trips through JSON, so the server can hold
# it, send it to the client to render, and take it back — without the client
# being trusted to have computed any of it. `fight_step` is the only thing that
# mutates one, and it does so purely from its arguments.
#
# The whole reason combat moved server-side: when the browser resolved fights, the
# balance numbers in config.py were decoration. A player could send
# {hp: 100} to /api/rooms/1/clear and take the boss. Now the client asks "what
# happens if I attack", the server answers, and the same reducer runs in
# tools/balance.py — so tuning the numbers is tuning the actual game.

ACTIONS = ("attack", "power", "defend", "potion", "flee")


def new_fight(room: dict, hero: dict, potions: dict[str, int], seed: str) -> dict:
    """Open a fight in `room`. The returned state is the whole truth of it."""
    enemy = room.get("enemy")
    return {
        "room_index": room["index"],
        "room_name": room["name"],
        "room_kind": room["kind"],
        "turn": 1,
        "hero": {
            "hp": hero["hp"], "max_hp": hero["max_hp"],
            "atk": hero["atk"], "defense": hero["defense"],
        },
        "enemy": (dict(enemy) | {"max_hp": enemy["hp"]}) if enemy else None,
        "potions": {k: v for k, v in potions.items() if v > 0},
        "state": "fight",          # fight | won | lost | fled
        "power_cd": 0,
        "defended": False,         # this turn's incoming hit is reduced
        "buffs": {},               # category -> turns remaining
        "charged": False,          # enemy is winding up its telegraphed hit
        "phased": False,           # boss phase change has already fired
        "log": [],
        "seed": seed,
        "profile": (enemy or {}).get("profile") or {},
    }


def _roll(seed: str, turn: int, salt: str) -> random.Random:
    """Per-turn randomness, derived rather than stored.

    Keyed on (seed, turn, salt) instead of carried in the state, so replaying a
    fight from turn 1 reproduces it exactly and the state never grows a hidden
    field the client could disagree with.
    """
    return random.Random(f"{seed}|{turn}|{salt}")


def _damage(rng: random.Random, atk: int, mult: float = 1.0,
            defense: int = 0, reduction: float = 0.0) -> tuple[int, bool]:
    """The one damage formula. Returns (amount, was_crit).

    MIN_DAMAGE keeps a fight able to end, so defence can never make a fight
    literally unable to resolve. MAX_DAMAGE caps the other direction, so a lucky
    crit chain cannot one-shot the boss and skip the fight the floor is built
    around.
    """
    lo, hi = config.DAMAGE_VARIANCE
    crit = rng.random() < config.CRIT_CHANCE
    raw = atk * rng.uniform(lo, hi) * mult * (config.CRIT_MULT if crit else 1.0)
    raw -= defense
    if reduction:
        raw *= 1.0 - reduction
    return max(config.MIN_DAMAGE, min(config.MAX_DAMAGE, round(raw))), crit


def _enemy_mult(state: dict) -> float:
    """Bosses get harder once they are actually losing. Read from the fight's own
    profile so a mini-boss phases by its own number, not the boss's."""
    profile = state.get("profile") or {}
    return profile.get("phase_mult", 1.0) if state["phased"] else 1.0


def _buff_mult(state: dict) -> float:
    """Rage and Haste multiply the next `turns` of the player's attacks."""
    mult = 1.0
    for category in ("damage", "haste"):
        if state["buffs"].get(category):
            mult *= config.POTION_EFFECTS[category]["mult"]
    return mult


def _tick_buffs(state: dict) -> None:
    """Expire buffs at the *end* of a turn, so a 3-turn buff covers the three
    actions after it was drunk rather than the drink itself."""
    for category, turns in list(state["buffs"].items()):
        if turns <= 1:
            del state["buffs"][category]
        else:
            state["buffs"][category] = turns - 1


def fight_step(state: dict, action: str, potion: str | None = None) -> dict:
    """Apply one player action and resolve the enemy turn. Pure.

    `action` is one of ACTIONS. `potion` is the category, required for
    "potion". Every branch returns a new state dict; nothing is mutated in
    place and nothing outside the arguments is read, which is what lets the
    server replay a fight without trusting the client and lets the balance tool
    simulate millions of them.
    """
    if action not in ACTIONS:
        raise ValueError(f"unknown action: {action}")

    s = {**state}
    s["hero"] = dict(state["hero"])
    s["enemy"] = dict(state["enemy"]) if state["enemy"] else None
    s["potions"] = dict(state["potions"])
    s["buffs"] = dict(state["buffs"])
    s["log"] = list(state["log"])

    if s["state"] != "fight":
        return s  # already resolved; further actions are no-ops

    hero, enemy, turn, seed = s["hero"], s["enemy"], s["turn"], s["seed"]
    log = s["log"]
    profile = s.get("profile") or {}

    # --- Fleeing is free: no turn passes, nothing is spent.
    if action == "flee":
        s["state"] = "fled"
        log.append("You break off and leave it to it. Your potions are untouched.")
        return s

    # --- Player acts.
    if action == "potion":
        if potion not in config.POTION_CATEGORIES:
            raise ValueError(f"unknown potion: {potion}")
        if s["potions"].get(potion, 0) < 1:
            raise ValueError("no potions of that kind left")
        s["potions"][potion] -= 1
        effect = config.POTION_EFFECTS[potion]
        if "heal" in effect:
            # A heal you do not need is still spent — drinking costs a turn, so
            # the player has to decide when healing is worth giving up tempo for.
            before = hero["hp"]
            hero["hp"] = min(hero["max_hp"], hero["hp"] + effect["heal"])
            log.append(f"You drink the {effect['label']}. +{hero['hp'] - before} HP.")
        else:
            s["buffs"][potion] = effect["turns"]
            log.append(f"You drink the {effect['label']}. {effect['turns']} turns of "
                       f"{'extra strikes' if potion == 'haste' else 'raw force'}.")

    elif action == "defend":
        hero["hp"] = min(hero["max_hp"], hero["hp"] + config.DEFEND_HEAL)
        s["defended"] = True
        log.append(f"Brace. +{config.DEFEND_HEAL} HP and the next hit lands softer.")

    else:
        # attack / power — power is gated on cooldown, which the API also checks.
        mult = _buff_mult(s)
        if action == "power":
            mult *= config.POWER_MULT
            s["power_cd"] = config.POWER_COOLDOWN
        hits = 1 + (1 if s["buffs"].get("haste") else 0)
        for _ in range(hits):
            rng = _roll(seed, turn, "hero")
            dmg, crit = _damage(rng, hero["atk"], mult)
            enemy["hp"] = max(0, enemy["hp"] - dmg)
            log.append(f"{'Power strike' if action == 'power' else 'Strike'} for {dmg}"
                       f"{' — critical!' if crit else ''}."
                       + (" Haste adds a second blow." if hits > 1 else ""))
            if enemy["hp"] <= 0:
                break

        # Boss phase change: once, at its threshold, announced so the player can
        # read it as a beat rather than a silent difficulty spike.
        threshold = profile.get("phase_at")
        if (threshold and not s["phased"] and enemy["hp"] > 0
                and enemy["hp"] <= enemy["max_hp"] * threshold):
            s["phased"] = True
            log.append(profile.get("phase_text", "It changes."))
            log.append(f"Every hit it lands now hurts {int(profile.get('phase_mult', 1) * 100)}% more.")

    if enemy["hp"] <= 0:
        s["state"] = "won"
        log.append(f"{enemy['name']} goes down. {s['room_name']} is clear.")
        # Breathing room after a clear. See ROOM_CLEAR_HEAL for why this matters:
        # without it, fleeing beat winning, because only winning cost HP.
        if config.ROOM_CLEAR_HEAL:
            before = hero["hp"]
            hero["hp"] = min(hero["max_hp"], hero["hp"] + config.ROOM_CLEAR_HEAL)
            if hero["hp"] > before:
                log.append(f"You catch your breath. +{hero['hp'] - before} HP.")
        return s

    # --- The enemy turn.
    #
    # Telegraph first: if the fight has a profile and the cadence lines up, this
    # turn is the wind-up and the big hit lands next turn. That one-turn warning
    # is the entire skill expression of a boss fight — DEFEND costs a turn but
    # halves the hit, so reading the room beats mashing.
    every = profile.get("special_every")
    charged = bool(every) and (turn % every == 0)
    if charged and not s["charged"]:
        s["charged"] = True
        log.append(profile.get("telegraph", "It winds up."))
        return s  # the wind-up turn costs you nothing but a turn of your own

    if s["charged"]:
        s["charged"] = False
        mult = profile.get("special_mult", 1.0) * _enemy_mult(s)
        label = "The telegraphed hit lands"
    else:
        mult = _enemy_mult(s)
        label = f"{enemy['name']} attacks"

    rng = _roll(seed, turn, "enemy")
    reduction = config.DEFEND_REDUCTION if s["defended"] else 0.0
    if s["buffs"].get("shield"):
        effect = config.POTION_EFFECTS["shield"]
        reduction = max(reduction, effect["reduction"])
    dmg, crit = _damage(rng, enemy["atk"], mult, defense=hero["defense"],
                        reduction=reduction)
    hero["hp"] = max(0, hero["hp"] - dmg)
    log.append(f"{label} for {dmg}"
               f"{' — blocked' if s['defended'] else ''}"
               f"{' — critical!' if crit else ''}.")
    if hero["hp"] <= 0:
        s["state"] = "lost"
        log.append("You fall. The potions you drank are spent.")
        return s

    # Turn limit: a player who only defends forever loses on the clock instead of
    # stalemating. This is what stops DEFEND from being a dominant strategy.
    limit = profile.get("turn_limit")
    if limit and turn >= limit:
        s["state"] = "lost"
        log.append("It outlasts you. You cannot break it and it will not tire.")
        return s

    # --- Turn bookkeeping.
    if s["defended"]:
        log.append("Your guard drops.")
    s["defended"] = False
    _tick_buffs(s)
    if s["power_cd"]:
        s["power_cd"] -= 1
    s["turn"] = turn + 1
    return s

def inventory(completions: list[Completion], tasks_by_id: dict[int, Task],
              uses: list, start: datetime) -> dict[str, int]:
    """Potions available this week, per category: earned minus used.

    Derived entirely from append-only rows. There is no counter to edit, so a
    client claiming a potion it did not earn simply disagrees with the sum.

    `tasks_by_id` must contain **every** task the user has ever had, archived
    ones included. That is not a detail: a Completion is a permanent record of
    real work, and a completion whose task has since been archived still paid out
    at the time. Looking tasks up through an active-only map makes archiving a
    quest silently confiscate potions already earned — which is both a real bug
    and a betrayal of the game's one promise. (api.all_tasks_by_id is the caller
    that gets this right; `user_tasks` is for the quest board only.)
    """
    earned: dict[str, int] = {}
    for c in completions:
        if c.completed_at < start:
            continue
        task = tasks_by_id.get(c.task_id)
        if task is None:
            # Only reachable if the task row itself is gone, which nothing does.
            # Skipping rather than crediting keeps a missing row from inventing
            # potions out of nothing.
            continue
        category = task.potion_category or config.DEFAULT_CATEGORY
        amount = potions_for(task)
        earned[category] = earned.get(category, 0) + amount

    for use in uses:
        if use.used_at < start:
            continue
        earned[use.category] = earned.get(use.category, 0) - 1

    # Clamp at zero explicitly. A negative would mean a PotionUse row exists with
    # no matching earning, which the API refuses to create; flooring here keeps
    # such a row from surfacing to the player as a negative count.
    return {k: max(0, v) for k, v in earned.items() if v > 0}


def potions_for(task: Task) -> int:
    """How many potions one completion of this task pays.

    Derived from the classifier's cached effort score against the bounds in
    config, so the economy is retunable without touching stored data.
    """
    return categorize.potions_for(task.difficulty)
