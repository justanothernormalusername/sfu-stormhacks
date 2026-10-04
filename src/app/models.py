from datetime import datetime, timezone
from typing import Optional

from pydantic import NaiveDatetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class Task(SQLModel, table=True):
    """A real-life quest. Completing one earns potions; it no longer gates a room."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    title: str
    # The repeat window, chosen by the classifier rather than the player.
    kind: str  # "daily" | "monthly" | "goal"
    # Both cached at creation time, so gameplay never calls an API.
    potion_category: Optional[str] = None
    # Classifier's effort score, normalized to 0..1. The potion *count* is
    # derived from this in config rather than stored, so retuning POTION_MIN /
    # POTION_MAX re-scales every existing quest. None means the classifier was
    # unreachable and the quest pays the fallback.
    difficulty: Optional[float] = None
    active: bool = True
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class Completion(SQLModel, table=True):
    """Append-only record of a real-life task being done. Never edited or deleted."""

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    completed_at: NaiveDatetime = Field(default_factory=utcnow)
    note: str = ""
    flagged_by: Optional[int] = Field(default=None, foreign_key="user.id")


class BattleClear(SQLModel, table=True):
    """A room in the weekly dungeon beaten in-game.

    Replaces the old RoomClear. The gate is gone, so a completion no longer
    implies a clear: the player can fight any room any number of times, and
    clears are scoped to a week rather than to a completion. The unique
    constraint is what makes one-clear-per-room-per-week a database guarantee
    rather than an application check.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    week_start: NaiveDatetime = Field(index=True)
    room_index: int
    # HP carried out of this fight. Current HP is derived from the most recent
    # clear, so there is still no mutable HP field to edit.
    hp_after: int
    cleared_at: NaiveDatetime = Field(default_factory=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "week_start", "room_index", name="uq_clear_per_room_week"),
    )


class PotionUse(SQLModel, table=True):
    """Append-only record of a potion consumed. Inventory is earned minus used,
    so nothing here is ever updated or deleted."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    category: str
    used_at: NaiveDatetime = Field(default_factory=utcnow, index=True)
    room_index: Optional[int] = None


class Friendship(SQLModel, table=True):
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    friend_id: int = Field(foreign_key="user.id", primary_key=True)
