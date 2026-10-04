import random
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import game
from ..auth import current_user
from ..db import get_session
from ..models import Completion, Friendship, Item, RoomClear, Task, User, utcnow

router = APIRouter(prefix="/api")


class TaskIn(BaseModel):
    title: str
    kind: str


class CompleteIn(BaseModel):
    note: str = ""


class FriendIn(BaseModel):
    username: str


def friend_ids(session: Session, user: User) -> set[int]:
    rows = session.exec(select(Friendship).where(Friendship.user_id == user.id)).all()
    return {f.friend_id for f in rows}


def own_task(session: Session, user: User, task_id: int) -> Task:
    task = session.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(404, "Task not found")
    return task


def player_stats(session: Session, user: User) -> dict:
    tasks = session.exec(select(Task).where(Task.user_id == user.id)).all()
    completions = session.exec(select(Completion).where(Completion.user_id == user.id)).all()
    clears = session.exec(select(RoomClear).where(RoomClear.user_id == user.id)).all()
    items = session.exec(select(Item).where(Item.user_id == user.id)).all()
    xp = sum(c.xp for c in clears)
    level = game.level_for(xp)
    return {
        "username": user.username,
        "xp": xp,
        "level": level,
        "xp_this_level": game.xp_for_level(level),
        "xp_next_level": game.xp_for_level(level + 1),
        "hp": game.hp_for(tasks, completions, utcnow()),
        "max_hp": game.MAX_HP,
        "atk": 10 + 3 * level + sum(i.atk for i in items),
        "defense": sum(i.defense for i in items),
        "items": [{"name": i.name, "atk": i.atk, "defense": i.defense} for i in items],
    }


@router.get("/player")
def get_player(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return player_stats(session, user)


@router.get("/rooms")
def get_rooms(user: User = Depends(current_user), session: Session = Depends(get_session)):
    now = utcnow()
    tasks = session.exec(select(Task).where(Task.user_id == user.id, Task.active == True)).all()  # noqa: E712
    completions = session.exec(select(Completion).where(Completion.user_id == user.id)).all()
    cleared_ids = {c.completion_id for c in session.exec(select(RoomClear).where(RoomClear.user_id == user.id))}
    rooms = []
    for task in sorted(tasks, key=lambda t: (game.KINDS.index(t.kind), t.id)):
        done = game.completion_in_period(task, completions, now)
        rooms.append({
            "task_id": task.id,
            "title": task.title,
            "kind": task.kind,
            "unlocked": done is not None,
            "cleared": done is not None and done.id in cleared_ids,
            "enemy": game.enemy_for(task),
            "xp": game.XP_BY_KIND[task.kind],
        })
    return rooms


@router.get("/tasks")
def list_tasks(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return session.exec(select(Task).where(Task.user_id == user.id, Task.active == True)).all()  # noqa: E712


@router.post("/tasks")
def create_task(body: TaskIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    title = body.title.strip()
    if body.kind not in game.KINDS or not title:
        raise HTTPException(400, "Task needs a title and kind daily/monthly/goal")
    task = Task(user_id=user.id, title=title[:120], kind=body.kind)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


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
    return completion


@router.post("/rooms/{task_id}/clear")
def clear_room(task_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    task = own_task(session, user, task_id)
    completions = session.exec(select(Completion).where(Completion.task_id == task.id)).all()
    done = game.completion_in_period(task, completions, utcnow())
    if done is None:
        raise HTTPException(403, "Room is locked: complete the real task first")
    if session.exec(select(RoomClear).where(RoomClear.completion_id == done.id)).first():
        raise HTTPException(409, "Room already cleared this period")
    xp = game.XP_BY_KIND[task.kind]
    session.add(RoomClear(task_id=task.id, user_id=user.id, completion_id=done.id, xp=xp))
    loot = game.roll_loot(random.Random())
    if loot:
        name, atk, defense = loot
        session.add(Item(user_id=user.id, name=name, atk=atk, defense=defense))
    session.commit()
    return {
        "xp": xp,
        "loot": {"name": loot[0], "atk": loot[1], "defense": loot[2]} if loot else None,
        "player": player_stats(session, user),
    }


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
         "note": c.note, "flagged": c.flagged_by is not None}
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
    week_ago = utcnow() - timedelta(days=7)
    board = []
    for uid in friend_ids(session, user) | {user.id}:
        u = session.get(User, uid)
        clears = session.exec(select(RoomClear).where(RoomClear.user_id == uid)).all()
        board.append({
            "username": u.username,
            "weekly_xp": sum(c.xp for c in clears if c.cleared_at >= week_ago),
            "level": game.level_for(sum(c.xp for c in clears)),
            "is_you": uid == user.id,
        })
    return sorted(board, key=lambda r: r["weekly_xp"], reverse=True)
