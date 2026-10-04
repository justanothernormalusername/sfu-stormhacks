"""Balance harness. Monte-Carlo plays whole floor runs and reports how the floor
behaves at each potion budget.

This exists because the boss was unwinnable and nobody noticed: with the browser
resolving fights, the numbers in config.py were decoration. Combat is now a pure
reducer in game.py, so this imports the *actual* rules and plays the *actual*
floor — the numbers below move the real game.

    .venv/bin/python -m tools.balance            # default report
    .venv/bin/python -m tools.balance --weeks 200 --seed 7

Every threshold below is a design target, not an observation. If a check fails,
the tool exits non-zero so CI catches an unbalanced floor.
"""

import argparse
import statistics
from datetime import datetime, timedelta

from src.app import config, game

# --- Design targets ---------------------------------------------------------
# The v2 premise is "hard without preparation, winnable with it". These numbers
# are what that actually means for a floor clear:
#
#   0 potions  -> a walk-in should *not* clear the floor. This is the entire
#                 reason potions exist, and it is the number that regressed.
#   2 potions  -> a real but not maximal week. Should clear most of the time.
#   4 potions  -> a committed week. Should be near-certain.
#   7 potions  -> every daily, all week. Should be a certainty, not a formality.
TARGETS = {
    0: (0.00, 0.15),
    2: (0.45, 0.90),
    4: (0.85, 0.99),
    7: (0.98, 1.00),
}
# The boss specifically: the fight the whole floor points at. A committed player
# with three potions should win most of the time but still lose sometimes — if
# the boss can never be beaten the floor is a wall, and if it is a formality the
# whole climb was pointless.
BOSS_TARGET = (0.55, 0.85)


def hero(hp: int | None = None, **over) -> dict:
    stats = {"max_hp": config.PLAYER_BASE["max_hp"], "atk": config.PLAYER_BASE["atk"],
             "defense": config.PLAYER_BASE["defense"]}
    stats.update(over)
    return {"hp": stats["max_hp"] if hp is None else hp, **stats}


def policy_fn(policy: str, state: dict) -> tuple[str, str | None]:
    """Pick an action. These encode what a *competent* player does, not a perfect
    one — the simulator should measure the floor, not an oracle."""
    hp, max_hp = state["hero"]["hp"], state["hero"]["max_hp"]
    potions = state["potions"]
    low = hp < max_hp * 0.35

    if policy == "spam_attack":
        return "attack", None
    if policy == "power_only":
        return ("power" if not state["power_cd"] else "attack"), None
    if policy == "cautious":
        if low and potions.get("heal"):
            return "potion", "heal"
        return ("power" if not state["power_cd"] else "attack"), None
    if policy == "reader":
        # The skill-expressive policy: read the telegraph, heal at the threshold,
        # spend power strikes when off cooldown. This is what the boss is tuned
        # around — a player who ignores the wind-up should do measurably worse.
        if state["charged"]:
            return ("potion", "heal") if potions.get("heal") else ("defend", None)
        if low and potions.get("heal"):
            return "potion", "heal"
        return ("power" if not state["power_cd"] else "attack"), None
    if policy == "turtle":
        # Everything defend. Should *lose* — this is the strategy the turn limit
        # exists to punish.
        return "defend", None
    raise ValueError(f"unknown policy: {policy}")


def play_room(room: dict, hero_state: dict, potions: dict[str, int],
              policy: str, seed: str) -> dict:
    """Fight one room. Returns the final fight state."""
    state = game.new_fight(room, hero_state, potions, seed)
    while state["state"] == "fight":
        action, potion = policy_fn(policy, state)
        try:
            state = game.fight_step(state, action, potion)
        except ValueError:
            # Policy asked for a potion the player no longer has; fall back to a
            # plain attack rather than crashing, so a bad policy shows up as a
            # worse clear rate instead of an exception.
            state = game.fight_step(state, "attack")
    return state


def _split_potions(budget: int) -> dict[str, int]:
    """Deal a remaining potion budget into a plausible pack.

    Roughly half healing, the rest tempo. `damage` is weighted a little above
    `haste`/`shield` because rage scales hardest and is the first thing a player
    reaches for. A budget of 0-1 is a single heal, which is the realistic floor
    for someone who did almost nothing.
    """
    pack = {"heal": 0, "damage": 0, "haste": 0, "shield": 0}
    if budget <= 0:
        return pack
    heal = max(1, round(budget * 0.5))
    pack["heal"] = heal
    pack["damage"] = round((budget - heal) * 0.5)
    pack["haste"] = round((budget - heal) * 0.3)
    pack["shield"] = budget - heal - pack["damage"] - pack["haste"]
    return {k: max(0, v) for k, v in pack.items()}


def run_floor(week: datetime, potions_total: int, policy: str, seed_base: int) -> dict:
    """Walk the floor's critical path, fighting as we go.

    The critical path is the floor's rooms in `depth` order, ignoring the
    optional branches — because "how far did you get this week" is exactly the
    question the leaderboard asks, so it must be the question the balance tool
    asks too.
    """
    floor = game.floor_for_week(week)
    rooms = floor["rooms"]
    path = sorted(range(len(rooms)), key=lambda i: rooms[i]["depth"])
    boss_index = max(range(len(rooms)), key=lambda i: rooms[i]["depth"])

    hero_state = hero()
    spent: dict[str, int] = {}
    results = []
    for index in path:
        room = rooms[index]
        if room["safe"]:
            if room["restore"]:
                hero_state["hp"] = min(hero_state["max_hp"],
                                        hero_state["hp"] + room["restore"])
            results.append({"index": index, "name": room["name"], "state": "safe",
                            "hp": hero_state["hp"], "turn": 0})
            continue

        # Potions are one shared weekly pool spent in encounter order — this is
        # the real constraint. A pool that refilled per room would make the floor
        # trivially long and the whole potion economy meaningless.
        #
        # Split across categories the way a real week's pack is: mostly healing,
        # with some offence and utility. Handing the entire budget to `heal` would
        # flatter the floor, because the player then never faces the tempo
        # decision that makes the boss interesting.
        budget = max(0, potions_total - sum(spent.values()))
        potions = _split_potions(budget)
        state = play_room(room, hero_state, potions, policy,
                          f"{seed_base}|{week:%Y-%m-%d}|{index}")
        for category, offered in potions.items():
            left = max(0, offered - state["potions"].get(category, 0))
            spent[category] = spent.get(category, 0) + left

        # A defeat drops you to full at your last cleared room; a win carries the
        # damage forward. Mirrors what the API does with BattleClear.hp_after.
        hero_state["hp"] = (state["hero"]["hp"] if state["state"] == "won"
                            else config.PLAYER_BASE["max_hp"])
        results.append({"index": index, "name": room["name"], "state": state["state"],
                        "hp": state["hero"]["hp"], "turn": state["turn"]})
        if state["state"] == "lost":
            break

    return {
        "floor": floor,
        "results": results,
        "cleared": all(r["state"] in ("won", "safe") for r in results),
        "boss_down": any(r["index"] == boss_index and r["state"] == "won"
                         for r in results),
        "rooms_cleared": sum(1 for r in results if r["state"] in ("won", "safe")),
    }


def simulate(weeks: int, seed: int, potions: int, policy: str, day: datetime) -> dict:
    """Play `weeks` runs across 7 distinct floors and average the results."""
    clear = boss = 0
    reach: list[int] = []
    turns: dict[str, list[int]] = {}
    for i in range(weeks):
        # 7 distinct weekly floors, then repeated — matches a real week cycle
        # without needing `weeks` distinct maps.
        week = day + timedelta(days=7 * (i // 7))
        out = run_floor(week, potions, policy, seed + i)
        clear += out["cleared"]
        boss += out["boss_down"]
        reach.append(out["rooms_cleared"])
        for r in out["results"]:
            turns.setdefault(r["name"], []).append(r["turn"])
    return {
        "clear_rate": clear / weeks,
        "boss_rate": boss / weeks,
        "avg_rooms": statistics.mean(reach),
        "turns": {k: statistics.mean(v) for k, v in turns.items()},
    }


def check(label: str, value: float, band: tuple[float, float]) -> bool:
    lo, hi = band
    ok = lo <= value <= hi
    print(f"  [{'ok  ' if ok else 'FAIL'}] {label:<36} {value:6.1%}   target {lo:.0%}-{hi:.0%}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weeks", type=int, default=250,
                        help="runs per scenario (250 = ~35 runs over each of 7 floors; "
                             "raise to 2000+ to see through sampling noise)")
    parser.add_argument("--seed", type=int, default=20261004)
    parser.add_argument("--day", type=lambda s: datetime.fromisoformat(s),
                        default=datetime(2026, 10, 5, 12, 0),
                        help="a datetime inside the first simulated week")
    parser.add_argument("--policy", default="reader",
                        choices=("spam_attack", "power_only", "cautious", "reader", "turtle"))
    args = parser.parse_args()

    # The bands are asserted for *competent* play only, which is what `--policy`
    # selects. A policy that never heals (`spam_attack`) or never attacks
    # (`turtle`) is supposed to fail — those runs are diagnostic, not a verdict.
    # `--policy reader` is the reference: it heals when low, spends power on
    # cooldown, and reads the boss telegraph, which is roughly a good player.
    assertable = args.policy in ("reader", "cautious")

    hero_stats = config.PLAYER_BASE
    print("=" * 74)
    print("TASK DUNGEON — floor balance report")
    print("=" * 74)
    print(f"player     hp={hero_stats['max_hp']}  atk={hero_stats['atk']}  "
          f"def={hero_stats['defense']}")
    print(f"enemy hp   base={config.ENEMY_HP['base']:.0f} +{config.ENEMY_HP['per_depth']:.1f}/depth, "
          f"scaled by archetype and the week's modifier")
    print(f"potions    heal={config.POTION_EFFECTS['heal']['heal']}  "
          f"rage=x{config.POTION_EFFECTS['damage']['mult']}  "
          f"haste=x{config.POTION_EFFECTS['haste']['mult']}  "
          f"aegis=-{int((1 - config.POTION_EFFECTS['shield']['reduction']) * 100)}%")
    print(f"runs       {args.weeks} per scenario, policy={args.policy!r}, "
          f"seed={args.seed}\n")

    floor = game.floor_for_week(args.day)
    print(f"FLOOR: {floor['name']}  ·  this week's modifier: {floor['modifier']['name']}")
    print(f"       {floor['modifier']['blurb']}\n")
    print(f"  {'room':<24} {'depth':>5} {'kind':<10} {'hp':>5} {'atk':>5}")
    for room in floor["rooms"]:
        enemy = room["enemy"]
        print(f"  {room['name']:<24} {room['depth']:>5} {room['tier']:<10} "
              f"{(enemy['hp'] if enemy else '-'):>5} {(enemy['atk'] if enemy else '-'):>5}")

    print("\nFLOOR CLEAR RATE by weekly potion income")
    print("-" * 74)
    ok = True
    turns: dict[str, float] = {}
    for potions, band in sorted(TARGETS.items()):
        result = simulate(args.weeks, args.seed, potions, args.policy, args.day)
        if assertable:
            ok &= check(f"{potions} potions in the pack", result["clear_rate"], band)
        else:
            # Diagnostic mode: report without asserting, since the bands describe
            # competent play and this policy is not competent play.
            print(f"  [ --  ] {potions} potions in the pack"
                  f"{'':>22}{result['clear_rate']:>7.1%}   (diagnostic, not asserted)")
        if potions == 3:
            turns = result["turns"]
        print(f"{'':>8}avg rooms cleared: {result['avg_rooms']:.1f} / {len(floor['rooms'])}"
              f"     boss down: {result['boss_rate']:.0%}")

    print("\nBOSS FIGHT at 3 potions (the fight the floor points at)")
    print("-" * 74)
    boss_result = simulate(args.weeks, args.seed, 3, args.policy, args.day)
    if assertable:
        ok &= check("boss defeated", boss_result["boss_rate"], BOSS_TARGET)
    else:
        print(f"  [ --  ] boss defeated"
              f"{'':>27}{boss_result['boss_rate']:>7.1%}   (diagnostic, not asserted)")

    if turns:
        print("\nAVERAGE LENGTH OF FIGHT, by room (turns)")
        print("-" * 74)
        for room in floor["rooms"]:
            avg = turns.get(room["name"])
            label = room["name"] if avg else f"{room['name']} (safe)"
            print(f"  {label:<24} {avg if avg else '-':>5}")

    print("\nSKILL GRADIENT at 4 potions (does playing well matter?)")
    print("-" * 74)
    for policy in ("turtle", "spam_attack", "power_only", "cautious", "reader"):
        result = simulate(max(40, args.weeks // 4), args.seed, 4, policy, args.day)
        print(f"  {policy:<14} floor cleared {result['clear_rate']:>6.1%}"
              f"     boss down {result['boss_rate']:>6.1%}"
              f"     rooms {result['avg_rooms']:>4.1f}/{len(floor['rooms'])}")

    print("\n" + "=" * 74)
    print("BALANCED" if ok else "OUT OF BALANCE — adjust config.py and re-run")
    print("=" * 74)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())