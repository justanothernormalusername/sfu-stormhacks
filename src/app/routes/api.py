from contextlib import contextmanager
from threading import Lock
from uuid import uuid4

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


class ActIn(BaseModel):
    """One player action. Nothing else is accepted — deliberately.

    There is no `hp` field, and that is the point of the whole rewrite. The old
    client resolved the fight in JavaScript and then told the server how much HP
    it had left, so `POST /api/rooms/{i}/clear` with `{hp: 100}` was a valid
    request that took the boss. Damage, victory, and remaining HP are now the
    server's numbers, computed by the same pure reducer the balance simulator
    runs. A client that disagrees simply cannot express the disagreement.
    """

    action: str = "attack"          # attack | power | defend | heal | potion | flee
    potion: str | None = None       # required when action == "potion"


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
    """HP carried from the furthest clear; a fresh run starts at full health."""
    last = session.exec(
        select(BattleClear)
        .where(BattleClear.user_id == user.id, BattleClear.week_start == start)
        .order_by(BattleClear.room_index.desc())
    ).first()
    if last is None:
        return config.PLAYER_BASE["max_hp"]
    return max(1, min(config.PLAYER_BASE["max_hp"], last.hp_after))


def furthest_room_index(session: Session, user: User, start) -> int:
    """Run depth for the HUD and leaderboard, excluding safe rooms."""
    floor = game.floor_for_week(start)
    rows = session.exec(
        select(BattleClear.room_index).where(
            BattleClear.user_id == user.id, BattleClear.week_start == start
        )
    ).all()
    fought = [r for r in rows if not floor["rooms"][r]["safe"]]
    return max(fought) if fought else 0


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
        "furthest_room": furthest_room_index(session, user, start),
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
        # Derived from the authored floor rather than a separate constant, so
        # the number the HUD shows cannot drift from the map that was built.
        "room_count": len(config.FLOOR_ROOMS),
        # null means "unbounded" — the depth curve decides the boss's HP outright.
        # Published so the client can tell a deliberately uncapped boss from a bug.
        "boss_hp_cap": config.BOSS_HP_CAP,
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
    """The shared floor for this week, with this player's progress folded in.

    The map itself is identical for every player; only `cleared` differs. Rooms
    also carry `blocked`, which is true for rooms the player cannot walk into yet
    because they have no route there — the map is a graph, not a grid, so this is
    computed from FLOOR_LINKS rather than assumed.
    """
    start = game.week_start(utcnow())
    floor = game.floor_for_week(start)
    cleared = {r.room_index for r in session.exec(
        select(BattleClear).where(BattleClear.user_id == user.id, BattleClear.week_start == start)
    ).all()}
    walkable = walkable_rooms(floor, cleared)
    enterable = enterable_rooms(floor, cleared)
    for room in floor["rooms"]:
        room["cleared"] = room["index"] in cleared
        # `blocked` is the single flag the client needs, and it has to mean
        # exactly "the server will refuse to open a fight here" — i.e. the
        # complement of `enterable`, not of `walkable`. Those differ, and using
        # the wrong one is a real bug: rooms 1-3 are enterable from the entrance
        # (you fight them from where you stand) while not walkable until won, so
        # marking them blocked would draw three SEALED rooms the server happily
        # lets you fight, and the player could never clear the first fight.
        room["blocked"] = room["index"] not in enterable
        # `walkable` is kept separately because the map draws a cleared room as
        # somewhere you can stand.
        room["walkable"] = room["index"] in walkable
    return floor


def neighbours_of(floor: dict) -> dict[int, set[int]]:
    """The floor as a graph. The map is authored as links, not as a grid, so
    adjacency is read from FLOOR_LINKS rather than inferred from tile positions."""
    neighbours: dict[int, set[int]] = {r["index"]: set() for r in floor["rooms"]}
    for a, b in floor["links"]:
        neighbours[a].add(b)
        neighbours[b].add(a)
    return neighbours


def walkable_rooms(floor: dict, cleared: set[int]) -> set[int]:
    """Rooms the player can physically stand in.

    The dungeon is a graph whose doors open as you clear it, and there are two
    different questions here that are easy to conflate:

      * can I *stand* in this room — yes if it is safe (nothing to fight) or
        already cleared, and I can reach it by walking;
      * can I *fight* here — true for any room whose neighbour I can stand in.

    Distinguishing them is what makes the floor playable at all. An earlier
    version required every room on the path to be cleared, which deadlocked the
    whole map: the entrance is safe, so it never has a clear row, so the flood
    fill expanded through nothing and every other room was permanently sealed.
    The entrance being safe is the case that breaks the naive version.
    """
    neighbours = neighbours_of(floor)
    open_here = {r["index"] for r in floor["rooms"] if r["safe"] or r["index"] in cleared}
    entrance = floor["rooms"][0]["index"]
    walkable = {entrance}
    stack = [entrance]
    while stack:
        for neighbour in neighbours.get(stack.pop(), ()):
            if neighbour not in walkable and neighbour in open_here:
                walkable.add(neighbour)
                stack.append(neighbour)
    return walkable


def enterable_rooms(floor: dict, cleared: set[int]) -> set[int]:
    """Rooms whose fight the player may start: walkable, or next to somewhere
    they can stand. This is the set `enter` checks against."""
    neighbours = neighbours_of(floor)
    walkable = walkable_rooms(floor, cleared)
    reach = set(walkable)
    for room in walkable:
        reach |= neighbours.get(room, set())
    return reach


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


@router.post("/rooms/{room_index}/enter")
def enter_room(room_index: int, user: User = Depends(current_user),
               session: Session = Depends(get_session)) -> dict:
    start = game.week_start(utcnow())
    with fight_lock(user, room_index, start):
        return _enter_room(room_index, user, session, start)


def _enter_room(room_index: int, user: User, session: Session, start) -> dict:
    """Start a fight in a room, or use a safe room's effect.

    The client sends nothing but a room index. Enemy stats, the player's HP, and
    the fight seed are all decided here — which is the point. Previously the
    browser resolved the fight and then told the server how much HP it had left,
    so a player could post an arbitrary `hp` and take the boss for free.
    """
    floor = game.floor_for_week(start)
    if not 0 <= room_index < len(floor["rooms"]):
        raise HTTPException(404, "No such room")
    room = floor["rooms"][room_index]

    cleared = {r.room_index for r in session.exec(
        select(BattleClear).where(BattleClear.user_id == user.id, BattleClear.week_start == start)
    ).all()}
    if room_index in cleared:
        raise HTTPException(409, "You have already cleared that room this week")
    if room_index not in enterable_rooms(floor, cleared):
        raise HTTPException(403, "You cannot reach that room yet")

    # Safe rooms: the shrine restores once per visit and the entrance is a no-op.
    if room["safe"]:
        restored = 0
        if room.get("restore"):
            # Heal from the HP the run has actually reached, not from a full bar.
            # A player who walks past the shrine and doubles back is still carrying
            # the damage from the deepest fight, and `current_hp` reads exactly
            # that — so a top-up here has to start from it.
            before = current_hp(session, user, start)
            after = min(config.PLAYER_BASE["max_hp"], before + room["restore"])
            # Report what was actually healed. The remaining headroom can be less
            # than `restore`, and the client prints this number, so reporting the
            # nominal value would describe a heal the player did not receive.
            restored = after - before
            # A clear records shrine use until death or the weekly reset.
            session.add(BattleClear(user_id=user.id, week_start=start,
                                    room_index=room_index, hp_after=after))
            # HP lives on the furthest cleared row, so a shrine behind the frontier
            # would record a heal that nothing ever reads back. Carry the healed
            # value forward onto that row when the shrine is not itself the latest.
            last = session.exec(
                select(BattleClear).where(
                    BattleClear.user_id == user.id, BattleClear.week_start == start,
                    BattleClear.room_index > room_index,
                ).order_by(BattleClear.room_index.desc())
            ).first()
            if last is not None:
                last.hp_after = max(last.hp_after, after)
                session.add(last)
            session.commit()
        return {"room": room, "safe": True, "restored": restored,
                "player": player_stats(session, user)}

    seed = f"{user.id}|{start.isoformat()}|{room_index}|{uuid4().hex}"
    # Entry and actions share a lock so a new fight cannot race a run reset.
    state = game.new_fight(room, hero_stats(session, user, start),
                           potion_inventory(session, user, start), seed)
    record_fight_start(session, user, state, start)
    return {"room": room, "safe": False, "fight": public_fight(state),
            "player": player_stats(session, user)}


def hero_stats(session: Session, user: User, start) -> dict:
    return {
        "hp": current_hp(session, user, start),
        "max_hp": config.PLAYER_BASE["max_hp"],
        "atk": config.PLAYER_BASE["atk"],
        "defense": config.PLAYER_BASE["defense"],
    }


@router.post("/rooms/{room_index}/act")
def act(room_index: int, body: ActIn, user: User = Depends(current_user),
        session: Session = Depends(get_session)) -> dict:
    """Take one action in the current fight, and resolve the enemy's turn.

    The whole of combat happens here. The client sends an action name and
    renders the state that comes back; it never computes damage, never decides
    whether it won, and cannot claim HP it did not have.
    """
    start = game.week_start(utcnow())
    floor = game.floor_for_week(start)
    if not 0 <= room_index < len(floor["rooms"]):
        raise HTTPException(404, "No such room")
    room = floor["rooms"][room_index]
    if room["safe"]:
        raise HTTPException(409, "Nothing to fight in there")

    # The read-modify-write below has to be atomic. Two `act` requests landing at
    # once (a double-click, or a spammed key) would otherwise both load the same
    # turn-3 state, both resolve it, and both write their outcome — so a player
    # could spend one potion twice, or record a win the enemy never allowed. The
    # lock covers load -> step -> save, so the second request sees the first one's
    # result and is refused on its own terms (cooldown, no fight, already cleared).
    with fight_lock(user, room_index, start):
        state = load_fight(session, user, room_index, start)
        if state is None:
            raise HTTPException(409, "No fight in progress there")

        # Cooldown is enforced here, not in the client: the client is told
        # `power_cd` so it can grey the button out, but it is not what stops a
        # spammed request.
        if body.action == "power" and state["power_cd"] > 0:
            raise HTTPException(409, f"Power strike needs {state['power_cd']} more turn(s)")

        # A potion must be in the derived inventory, checked against the DB
        # rather than the fight snapshot, so a client cannot resurrect a potion it
        # already spent by replaying a stale state.
        potion = body.potion
        if body.action == "potion":
            if potion not in config.POTION_CATEGORIES:
                raise HTTPException(400, "No such potion")
            if potion_inventory(session, user, start).get(potion, 0) < 1:
                raise HTTPException(409, "You have none of those left this week")

        try:
            state = game.fight_step(state, body.action, potion)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

        # Potions are spent by writing a row, the moment they are drunk — not when
        # the fight ends. Otherwise a client that abandons a fight keeps the
        # potions it already used, and refreshing the page is an infinite heal.
        if body.action == "potion":
            session.add(PotionUse(user_id=user.id, category=potion, used_at=utcnow(),
                                  room_index=room_index))
            session.commit()

        resolved = None
        if state["state"] == "won":
            resolved = record_fight_win(session, user, state, start)
        elif state["state"] == "lost":
            resolved = record_fight_loss(session, user, state, start)

        save_fight(session, user, state, room_index, start)

    return {"fight": public_fight(state), "player": player_stats(session, user),
            "resolved": resolved}


# --- Fight state ----------------------------------------------------------
#
# An in-progress fight lives in the session cookie's signed sibling: a short-lived
# server-side dict keyed by user. It is deliberately NOT a database column.
#
# The reasoning: a fight is ephemeral and untrusted-adjacent. If HP lived in a
# column, a player could rewrite it, and the project's whole claim is that there
# is no mutable stat to edit. If fights were rows, every swing would be an
# insert and a defeat would need cleanup. Keeping them in memory means a restart
# simply drops an unfinished fight — the player walks back in, full HP, nothing
# lost — which is exactly the right failure mode for something that never
# mattered. Defeat deletes this run's clears; potion uses remain in the database.
#
# The seed is per-fight random, so two players in the same room get different
# fights, and a player cannot replay a sequence of lucky rolls.

_FIGHTS: dict[tuple[int, int, str], dict] = {}
_FIGHT_LOCK = Lock()
# One lock per player's week so a death cannot race another room's action or
# entry and restore progress from the run that just ended.
_FIGHT_LOCKS: dict[tuple[int, str], Lock] = {}


@contextmanager
def fight_lock(user: User, room_index: int, start):
    """Serialise combat and run resets for this player across all rooms."""
    key = (user.id, start.isoformat())
    with _FIGHT_LOCK:
        lock = _FIGHT_LOCKS.setdefault(key, Lock())
    with lock:
        yield


def _fight_key(user: User, room_index: int, start) -> tuple[int, int, str]:
    """Keyed by week as well as user and room.

    Scoping to the week matters for correctness, not tidiness: a fight left open
    on Sunday would otherwise still be in memory on Monday, letting a player
    resume a fight against last week's map — with the enemy's HP from a week ago
    and the potion window already refilled. `start` is part of the key, so the
    Monday reset drops every fight in progress, which is the intent.
    """
    return (user.id, room_index, start.isoformat())


def record_fight_start(session: Session, user: User, state: dict, start) -> None:
    with _FIGHT_LOCK:
        _FIGHTS[_fight_key(user, state["room_index"], start)] = state


def load_fight(session: Session, user: User, room_index: int, start) -> dict | None:
    with _FIGHT_LOCK:
        return _FIGHTS.get(_fight_key(user, room_index, start))


def save_fight(session: Session, user: User, state: dict, room_index: int, start) -> None:
    with _FIGHT_LOCK:
        key = _fight_key(user, room_index, start)
        # A resolved fight is dropped, so the next `enter` is a genuinely new
        # fight with a new seed rather than a replay of a won one.
        if state["state"] == "fight":
            _FIGHTS[key] = state
        else:
            _FIGHTS.pop(key, None)


def public_fight(state: dict) -> dict:
    """Strip the seed before the fight goes to the browser.

    The seed determines every damage roll. Handing it to the client would let a
    player compute the whole fight locally, see the outcome, and simply not send
    the losing turns — so it stays server-side. The client gets the state it needs
    to draw and nothing it needs to predict.
    """
    return {k: v for k, v in state.items() if k != "seed"}


def record_fight_win(session: Session, user: User, state: dict, start) -> dict:
    """Persist a won fight. `hp_after` is the server's own number."""
    room_index = state["room_index"]
    hp = max(1, min(config.PLAYER_BASE["max_hp"], state["hero"]["hp"]))
    existing = session.exec(
        select(BattleClear).where(
            BattleClear.user_id == user.id,
            BattleClear.week_start == start,
            BattleClear.room_index == room_index,
        )
    ).first()
    if existing:
        existing.hp_after = hp
        session.add(existing)
    else:
        session.add(BattleClear(user_id=user.id, week_start=start,
                                room_index=room_index, hp_after=hp))
    session.commit()
    return {"room_index": room_index, "hp_after": hp, "cleared": True}


def record_fight_loss(session: Session, user: User, state: dict, start) -> dict:
    """Reset dungeon progress and inventory, preserving quests and completions."""
    # Record the remaining pack as lost so old task completions cannot refill it.
    now = utcnow()
    for category, amount in potion_inventory(session, user, start).items():
        for _ in range(amount):
            session.add(PotionUse(user_id=user.id, category=category, used_at=now,
                                  room_index=state["room_index"]))
    clears = session.exec(select(BattleClear).where(
        BattleClear.user_id == user.id, BattleClear.week_start == start
    )).all()
    for clear in clears:
        session.delete(clear)
    session.commit()
    with _FIGHT_LOCK:
        for key in list(_FIGHTS):
            if key[0] == user.id:
                del _FIGHTS[key]
    return {"restored_to": config.PLAYER_BASE["max_hp"], "cleared": False,
            "reset": True}


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
            "furthest_room": furthest_room_index(session, u, start),
            "is_you": uid == user.id,
        })
    return sorted(board, key=lambda r: (r["furthest_room"], r["username"]), reverse=True)
