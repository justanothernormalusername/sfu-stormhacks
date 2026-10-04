"""Game rules. Everything that grants XP, loot, or unlocks lives here, server-side,
so the game client (Phaser now, maybe Godot later) only renders results."""

import math
import os
import random
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import Completion, Task

KINDS = ("daily", "monthly", "goal")
XP_BY_KIND = {"daily": 10, "monthly": 50, "goal": 200}
ENEMY_BY_KIND = {
    "daily": {"tier": "mob", "names": ["Slime", "Goblin", "Skeleton", "Bat"], "hp": 30, "atk": 5},
    "monthly": {"tier": "mini-boss", "names": ["Orc Captain", "Wraith", "Ogre"], "hp": 70, "atk": 8},
    "goal": {"tier": "boss", "names": ["Dragon", "Lich King", "Demon Lord"], "hp": 120, "atk": 12},
}
MAX_HP = 100
MISSED_DAILY_DAMAGE = 10
RECENT_COMPLETION_HEAL = 5
# Day/month boundaries follow the players' local clock, not UTC (UTC midnight is 5pm in Vancouver).
TZ = ZoneInfo(os.environ.get("APP_TZ", "America/Vancouver"))
LOOT_TABLE = [
    ("Rusty Sword", 2, 0), ("Wooden Shield", 0, 2), ("Iron Sword", 4, 0),
    ("Chainmail", 0, 4), ("Flame Blade", 7, 0), ("Dragon Scale", 0, 7),
]


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
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def completion_in_period(task: Task, completions: list[Completion], now: datetime) -> Completion | None:
    start = period_start(task.kind, now)
    current = [c for c in completions if c.task_id == task.id and c.completed_at >= start]
    return max(current, key=lambda c: c.completed_at) if current else None


def level_for(xp: int) -> int:
    return math.floor(math.sqrt(xp / 25)) + 1


def xp_for_level(level: int) -> int:
    return 25 * (level - 1) ** 2


def missed_dailies(tasks: list[Task], completions: list[Completion], now: datetime, days: int = 7) -> int:
    """Count daily tasks skipped on each of the last `days` days (not counting today)."""
    today = local_date(now)
    done = {(c.task_id, local_date(c.completed_at)) for c in completions}
    missed = 0
    for task in tasks:
        if task.kind != "daily" or not task.active:
            continue
        for offset in range(1, days + 1):
            day = today - timedelta(days=offset)
            if day >= local_date(task.created_at) and (task.id, day) not in done:
                missed += 1
    return missed


def hp_for(tasks: list[Task], completions: list[Completion], now: datetime) -> int:
    """Skipped dailies in the last week hurt; any quest done in the last week heals."""
    week_ago = local_date(now) - timedelta(days=7)
    recent = sum(1 for c in completions if local_date(c.completed_at) > week_ago)
    hp = MAX_HP - MISSED_DAILY_DAMAGE * missed_dailies(tasks, completions, now) + RECENT_COMPLETION_HEAL * recent
    return max(0, min(MAX_HP, hp))


def enemy_for(task: Task) -> dict:
    spec = ENEMY_BY_KIND[task.kind]
    # Seeded by task id so the same room always holds the same monster.
    name = random.Random(task.id).choice(spec["names"])
    return {"name": name, "tier": spec["tier"], "hp": spec["hp"], "atk": spec["atk"]}


def roll_loot(rng: random.Random | None = None) -> tuple[str, int, int] | None:
    rng = rng or random.Random()
    if rng.random() < 0.6:
        return rng.choice(LOOT_TABLE)
    return None
