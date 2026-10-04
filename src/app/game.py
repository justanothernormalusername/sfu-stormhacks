"""Game rules. Everything that grants XP, loot, or unlocks lives here, server-side,
so the game client (Phaser now, maybe Godot later) only renders results."""

import math
import os
import random
from datetime import date, datetime, timezone
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
