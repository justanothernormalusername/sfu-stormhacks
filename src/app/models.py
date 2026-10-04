from datetime import datetime, timezone
from typing import Optional

from pydantic import NaiveDatetime

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    title: str
    kind: str  # "daily" | "monthly" | "goal"
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


class RoomClear(SQLModel, table=True):
    """A room beaten in-game. XP is only ever derived from these rows."""

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    completion_id: int = Field(foreign_key="completion.id", unique=True)
    xp: int
    cleared_at: NaiveDatetime = Field(default_factory=utcnow)


class Item(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str
    atk: int = 0
    defense: int = 0
    found_at: NaiveDatetime = Field(default_factory=utcnow)


class Friendship(SQLModel, table=True):
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    friend_id: int = Field(foreign_key="user.id", primary_key=True)
