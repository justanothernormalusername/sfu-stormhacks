from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import categorize, config, game
from ..auth import current_user
from ..db import get_session
from ..models import BattleClear, Completion, Friendship, PotionUse, Task, User, utcnow

router = APIRouter(prefix="/api")


class TaskIn(BaseModel):
    title: str


class CompleteIn(BaseModel):
    note: str = ""


class FriendIn(BaseModel):
    username: str


class UseIn(BaseModel):
    room_index: int | None = None


class ClearIn(BaseModel):
    hp: int


class HpIn(BaseModel):
    hp: int


def friend_ids(session: Session, user: User) -> set[int]:
    rows = session.exec(select(Friendship).where(Friendship.user_id == user.id)).all()
    return {f.friend_id for f in rows}


def own_task(session: Session, user: User, task_id: int) -> Task:
    task = session.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(404, "Task not found")
    return task


def user_tasks(session: Session, user_id: int) -> dict[int, Task]:
    rows = session.exec(select(Task).where(Task.user_id == user_id, Task.active == True)).all()  # noqa: E712
    return {t.id: t for t in rows}


def current_hp(session: Session, user: User, start) -> int:
    """HP carried into the next fight.

    Derived from the checkpoint room's clear row rather than stored on the user,
    so there is still no mutable HP field to edit. A fresh week starts full.

    The checkpoint is the furthest room cleared, not the most recently cleared:
    they differ once you backtrack, and "how far in did I get" is the thing the
    HP is attached to. A defeat rewrites that row back to full via
    POST /api/rooms/{checkpoint}/hp, which is what restores you.
    """
    last = session.exec(
        select(BattleClear)
        .where(BattleClear.user_id == user.id, BattleClear.week_start == start)
        .order_by(BattleClear.room_index.desc())
    ).first()
    if last is None:
        return config.PLAYER_BASE["max_hp"]
    return max(1, min(config.PLAYER_BASE["max_hp"], last.hp_after))


def checkpoint_index(session: Session, user: User, start) -> int:
    """The furthest room cleared this week — where a defeat sends you back."""
    rows = session.exec(
        select(BattleClear.room_index).where(
            BattleClear.user_id == user.id, BattleClear.week_start == start
        )
    ).all()
    return max(rows) if rows else 0


def potion_inventory(session: Session, user: User, start) -> dict[str, int]:
    tasks = user_tasks(session, user.id)
    completions = session.exec(
        select(Completion).where(Completion.user_id == user.id, Completion.completed_at >= start)
    ).all()
    uses = session.exec(
        select(PotionUse).where(PotionUse.user_id == user.id, PotionUse.used_at >= start)
    ).all()
    return game.inventory(completions, tasks, uses, start)


def _task_view(task: Task) -> dict:
    """What the quest board shows for one quest.

    The reward is computed from the cached effort score rather than stored, so
    this always reflects the current POTION_MIN/POTION_MAX.
    """
    return {
        "id": task.id,
        "title": task.title,
        "kind": task.kind,
        "potion": task.potion_category or config.DEFAULT_CATEGORY,
        "potions": game.potions_for(task),
    }


def player_stats(session: Session, user: User) -> dict:
    start = game.week_start(utcnow())
    inventory = potion_inventory(session, user, start)
    return {
        "username": user.username,
        "max_hp": config.PLAYER_BASE["max_hp"],
        "hp": current_hp(session, user, start),
        "atk": config.PLAYER_BASE["atk"],
        "defense": config.PLAYER_BASE["defense"],
        "potions": inventory,
        "potions_total": sum(inventory.values()),
        "checkpoint": checkpoint_index(session, user, start),
    }


@router.get("/player")
def get_player(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return player_stats(session, user)


@router.get("/config")
def get_config(user: User = Depends(current_user)):
    """The public balance numbers, so the client renders with the same values the
    server enforces instead of keeping its own copies. Credentials are not
    exposed here — only the rules a player can legitimately see.
    """
    return {
        "player": config.PLAYER_BASE,
        "room_count": config.ROOM_COUNT,
        "potion_min": config.POTION_MIN,
        "potion_max": config.POTION_MAX,
        "potion_effects": config.POTION_EFFECTS,
        "potion_categories": list(config.POTION_CATEGORIES),
        "kind_labels": config.KIND_LABEL,
        "damage_variance": list(config.DAMAGE_VARIANCE),
        "crit_chance": config.CRIT_CHANCE,
        "crit_mult": config.CRIT_MULT,
        "power_mult": config.POWER_MULT,
        "power_cooldown": config.POWER_COOLDOWN,
        "defend_heal": config.DEFEND_HEAL,
        "defend_reduction": config.DEFEND_REDUCTION,
        "min_damage": config.MIN_DAMAGE,
    }


@router.get("/rooms")
def get_rooms(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """The shared dungeon for this week. Identical for every player; only the
    cleared flags differ."""
    start = game.week_start(utcnow())
    cleared = {r.room_index for r in session.exec(
        select(BattleClear).where(BattleClear.user_id == user.id, BattleClear.week_start == start)
    ).all()}
    rooms = game.rooms_for_week(start)
    for room in rooms:
        room["cleared"] = room["index"] in cleared
    return rooms


@router.get("/tasks")
def list_tasks(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Active quests with what each one is worth and whether it is already
    banked for its repeat window. Everything shown is read off the row cached at
    creation time, so this endpoint never calls the classifier."""
    now = utcnow()
    tasks = session.exec(select(Task).where(Task.user_id == user.id, Task.active == True)).all()  # noqa: E712
    completions = session.exec(select(Completion).where(Completion.user_id == user.id)).all()
    by_task: dict[int, list[Completion]] = {}
    for completion in completions:
        by_task.setdefault(completion.task_id, []).append(completion)
    return [
        {**_task_view(t),
         "done": game.completion_in_period(t, by_task.get(t.id, []), now) is not None}
        for t in tasks
    ]


@router.post("/tasks")
def create_task(body: TaskIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Task needs a title")
    title = title[:120]
    # Judged once here, never in the gameplay path. The player chooses neither
    # the potion nor the count — both come back from the classifier.
    verdict = categorize.classify(title)
    task = Task(user_id=user.id, title=title, kind=verdict["kind"],
                potion_category=verdict["category"], difficulty=verdict["difficulty"])
    session.add(task)
    session.commit()
    session.refresh(task)
    return _task_view(task)


@router.delete("/tasks/{task_id}")
def archive_task(task_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    # Archive instead of delete so the history log stays intact.
    task = own_task(session, user, task_id)
    task.active = False
    session.add(task)
    session.commit()
    return {"ok": True}


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: int, body: CompleteIn, user: User = Depends(current_user),
                  session: Session = Depends(get_session)):
    task = own_task(session, user, task_id)
    now = utcnow()
    completions = session.exec(select(Completion).where(Completion.task_id == task.id)).all()
    if game.completion_in_period(task, completions, now):
        raise HTTPException(409, "Already completed for this period")
    completion = Completion(task_id=task.id, user_id=user.id, completed_at=now, note=body.note[:280])
    session.add(completion)
    session.commit()
    session.refresh(completion)
    category = task.potion_category or config.DEFAULT_CATEGORY
    return {
        "completion": completion,
        "potions_earned": game.potions_for(task),
        "category": category,
        "potions": potion_inventory(session, user, game.week_start(now)),
    }


@router.post("/rooms/{room_index}/clear")
def clear_room(room_index: int, body: ClearIn, user: User = Depends(current_user),
               session: Session = Depends(get_session)):
    """Record a win. The room must exist on this week's map."""
    start = game.week_start(utcnow())
    rooms = game.rooms_for_week(start)
    if not 0 <= room_index < len(rooms):
        raise HTTPException(404, "No such room")
    if session.exec(
        select(BattleClear).where(
            BattleClear.user_id == user.id,
            BattleClear.week_start == start,
            BattleClear.room_index == room_index,
        )
    ).first():
        raise HTTPException(409, "Room already cleared this week")
    hp = max(1, min(config.PLAYER_BASE["max_hp"], body.hp))
    session.add(BattleClear(user_id=user.id, week_start=start, room_index=room_index, hp_after=hp))
    session.commit()
    return {"cleared": rooms[room_index]["index"], "player": player_stats(session, user)}


@router.post("/rooms/{room_index}/hp")
def report_hp(room_index: int, body: HpIn, user: User = Depends(current_user),
              session: Session = Depends(get_session)):
    """Carry HP out of a fight, written onto that room's clear row."""
    start = game.week_start(utcnow())
    clear = session.exec(
        select(BattleClear).where(
            BattleClear.user_id == user.id,
            BattleClear.week_start == start,
            BattleClear.room_index == room_index,
        )
    ).first()
    if clear is None:
        raise HTTPException(404, "Clear that room first")
    clear.hp_after = max(1, min(config.PLAYER_BASE["max_hp"], body.hp))
    session.add(clear)
    session.commit()
    return {"ok": True}


@router.post("/potions/{category}/use")
def use_potion(category: str, body: UseIn, user: User = Depends(current_user),
               session: Session = Depends(get_session)):
    """Spend one potion. Availability is derived, never sent by the client."""
    if category not in config.POTION_CATEGORIES:
        raise HTTPException(404, "No such potion")
    start = game.week_start(utcnow())
    if potion_inventory(session, user, start).get(category, 0) < 1:
        raise HTTPException(409, "You have none of those left this week")
    session.add(PotionUse(user_id=user.id, category=category, used_at=utcnow(),
                          room_index=body.room_index))
    session.commit()
    return {"ok": True, "potions": potion_inventory(session, user, start)}


@router.get("/log")
def get_log(username: str | None = None, user: User = Depends(current_user),
            session: Session = Depends(get_session)):
    target = user
    if username and username != user.username:
        target = session.exec(select(User).where(User.username == username)).first()
        if target is None or target.id not in friend_ids(session, user):
            raise HTTPException(403, "You can only view friends' logs")
    rows = session.exec(
        select(Completion, Task).join(Task, Task.id == Completion.task_id)
        .where(Completion.user_id == target.id).order_by(Completion.completed_at.desc())
    ).all()
    return [
        {"id": c.id, "task": t.title, "kind": t.kind, "completed_at": c.completed_at.isoformat() + "Z",
         "note": c.note, "flagged": c.flagged_by is not None,
         "potion": t.potion_category or config.DEFAULT_CATEGORY}
        for c, t in rows
    ]


@router.post("/completions/{completion_id}/flag")
def flag_completion(completion_id: int, user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    completion = session.get(Completion, completion_id)
    if completion is None or completion.user_id not in friend_ids(session, user):
        raise HTTPException(403, "You can only flag friends' entries")
    completion.flagged_by = user.id
    session.add(completion)
    session.commit()
    return {"ok": True}


@router.post("/friends")
def add_friend(body: FriendIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    friend = session.exec(select(User).where(User.username == body.username.strip())).first()
    if friend is None or friend.id == user.id:
        raise HTTPException(404, "No such user")
    for a, b in ((user.id, friend.id), (friend.id, user.id)):
        if session.get(Friendship, (a, b)) is None:
            session.add(Friendship(user_id=a, friend_id=b))
    session.commit()
    return {"ok": True}


@router.get("/leaderboard")
def leaderboard(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Furthest room cleared this week. Everyone plays the same map, so this is
    directly comparable — and it is still a sum over rows, not a stored number."""
    start = game.week_start(utcnow())
    board = []
    for uid in friend_ids(session, user) | {user.id}:
        u = session.get(User, uid)
        board.append({
            "username": u.username,
            "furthest_room": checkpoint_index(session, u, start),
            "is_you": uid == user.id,
        })
    return sorted(board, key=lambda r: (r["furthest_room"], r["username"]), reverse=True)
