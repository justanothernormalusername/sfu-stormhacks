"""Game rules. Everything that decides a room's contents, a potion's category,
or an unlock lives here, server-side, so the game client (Phaser now, maybe Godot
later) only renders results.

Every function here is pure — no database, no network — so the rules are
unit-testable on their own.
"""

import os
import random
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config
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

    The local Monday is found by walking back day-by-day rather than subtracting
    a timedelta, so each intermediate midnight is resolved by the tz database
    instead of by arithmetic that can land on a nonexistent local time.
    """
    local = to_local(now)
    midnight = datetime(local.year, local.month, local.day, tzinfo=TZ)
    for _ in range(local.weekday() - config.WEEK_START_DAY):
        midnight -= timedelta(days=1)
    return to_utc(midnight)


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


# --- The weekly dungeon ---------------------------------------------------

def tier_for_index(index: int) -> str:
    """Difficulty comes from position on the shared map, not from task kind —
    rooms no longer derive from tasks."""
    progress = index / max(1, config.ROOM_COUNT - 1)
    if progress < config.TIER_SPLIT[0]:
        return "mob"
    if progress < config.TIER_SPLIT[1]:
        return "mini-boss"
    return "boss"


def rooms_for_week(week_start_dt: datetime) -> list[dict]:
    """The shared dungeon for one week. Identical for every player.

    Seeded by the week so the map is stable within a week and different across
    weeks. Pure: same week_start always yields the same dungeon.
    """
    seed = random.Random(week_start_dt.isoformat())
    names = seed.sample(config.ROOM_NAMES, min(len(config.ROOM_NAMES), config.ROOM_COUNT))
    rooms = []
    for index in range(config.ROOM_COUNT):
        tier = tier_for_index(index)
        spec = config.ENEMY_TIERS[tier]
        rooms.append({
            "index": index,
            "name": names[index] if index < len(names) else f"Room {index + 1}",
            "enemy": {
                "name": seed.choice(spec["names"]),
                "tier": tier,
                "hp": spec["hp"],
                "atk": spec["atk"],
            },
        })
    return rooms


# --- Potions ---------------------------------------------------------------

def inventory(completions: list[Completion], tasks_by_id: dict[int, Task],
              uses: list, start: datetime) -> dict[str, int]:
    """Potions available this week, per category: earned minus used.

    Derived entirely from append-only rows. There is no counter to edit, so a
    client claiming a potion it did not earn simply disagrees with the sum.
    """
    earned: dict[str, int] = {}
    for c in completions:
        if c.completed_at < start:
            continue
        task = tasks_by_id.get(c.task_id)
        if task is None:
            continue
        category = task.potion_category or config.DEFAULT_CATEGORY
        amount = config.POTIONS_BY_KIND.get(task.kind, 0)
        earned[category] = earned.get(category, 0) + amount

    for use in uses:
        if use.used_at < start:
            continue
        earned[use.category] = earned.get(use.category, 0) - 1

    return {k: v for k, v in earned.items() if v > 0}


def potions_earned_for(completion: Completion, task: Task) -> int:
    """How many potions a single completion pays out, and in what category."""
    return config.POTIONS_BY_KIND.get(task.kind, 0)
