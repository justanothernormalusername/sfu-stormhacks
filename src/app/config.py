"""Every balance number in the game, in one place.

The owner is not balancing these alone — teammates are picking this up — so
nothing below should be duplicated as a literal anywhere else in the backend or
the client. Change a number here and the whole game moves with it.

The public half of this file is served verbatim at `/api/config`, so the client
renders with exactly the numbers the server enforces.

`tools/balance.py` reads this file and Monte-Carlo simulates full floor runs
under several potion budgets. **Run it after touching anything in the
`PLAYER_`, `POTION_`, `ENEMY_`, or `ROOM_ARCHETYPES` blocks** — the design target
is written down at the bottom of that file and the numbers below are tuned to it.
"""

import os
from pathlib import Path

# repo root, so a local .env next to README.md is found from src/app/config.py
DOTENV = Path(__file__).resolve().parents[2] / ".env"


def _read_env(name: str, default: str | None = None) -> str | None:
    """An environment variable, falling back to a local untracked .env file.

    The file is only ever a developer convenience. It is gitignored, and on a
    deployed host it does not exist — there the real environment variable is
    the only source, which is what Render sets.
    """
    value = os.environ.get(name)
    if value:
        return value
    try:
        for line in DOTENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, raw = line.partition("=")
            if key.strip() == name:
                return raw.strip().strip("\"'") or default
    except OSError:
        pass
    return default

# --- Periods -------------------------------------------------------------
# Day, month, and week boundaries all follow the player's local clock.
WEEK_START_DAY = 0  # 0=Monday .. 6=Sunday

# --- The floor ------------------------------------------------------------
# The map is *authored* here rather than generated, because a good dungeon is a
# designed sequence of beats — an opening, a fork, somewhere to breathe, a
# locked-feeling finale — and not twelve rooms in a row. Coordinates are in
# tiles, origin top-left; a room occupies x..x+w-1, y..y+h-1.
#
# What lives in each room is still seeded per week (see `game.floor_for_week`):
# creature names, flavour, and the weekly modifier are drawn fresh, so every
# player walks the same map and gets a different week.
WORLD_COLS = 44
WORLD_ROWS = 22

FLOOR_NAME = "Floor 1 · The Root Datacenter"
FLOOR_THEME = "A dead machine-cathedral. The lights still flicker because something down here is awake."

# `depth` is progression order, not map position — it is what the enemy curve
# below is fed, so the side chambers you can reach early are still tuned as
# early rooms, and the boss is always the hardest thing on the floor.
FLOOR_ROOMS = (
    # name, kind, x, y, w, h, depth
    ("The Entry Stair", "entrance", 1, 10, 5, 5, 0),
    ("Flooded Barracks", "combat", 8, 3, 5, 4, 1),
    ("The Rust Hatch", "combat", 8, 16, 5, 4, 2),
    ("Collapsed Server Farm", "combat", 15, 9, 6, 5, 3),
    ("Ashfall Corridor", "combat", 15, 1, 5, 4, 3),
    ("Drowned Archives", "combat", 15, 17, 5, 4, 4),
    ("The Null Chapel", "shrine", 23, 4, 5, 5, 5),
    ("Bleeding Cores", "combat", 23, 14, 5, 5, 6),
    ("The Overclock", "elite", 30, 1, 5, 4, 7),
    ("Broken Consensus", "combat", 30, 10, 5, 4, 8),
    ("The Thermal Vault", "gate", 30, 17, 5, 4, 9),
    ("The Root Chamber", "boss", 37, 6, 6, 10, 10),
)

# Corridors, as room-index pairs. L-shaped and carved through room walls, so
# connectivity is guaranteed by construction and asserted in tests/test_floor.py.
FLOOR_LINKS = (
    (0, 1), (0, 2), (0, 3),           # the entry stair fans out three ways
    (1, 3), (1, 4), (2, 3), (2, 5),   # the north and south wings rejoin
    (3, 4), (3, 5),
    (3, 6), (3, 7),                   # through the server farm
    (6, 8), (6, 9), (7, 9), (7, 10),  # chapel side and cores side
    (9, 10), (8, 10),
    (9, 11), (10, 11),                # two ways into the boss arena
)

# What each kind of room *is*, mechanically. `hp_mult` / `atk_mult` scale the
# depth curve below, so a boss at depth 10 is not merely a bigger mob.
#
# The boss multipliers are the ones that needed the most tuning, and the reason
# is worth recording: the boss's cost to the player is roughly (its HP ÷ the
# player's damage) × (its ATK − the player's defence), so both multipliers
# multiply together. At 2.15/1.4 the boss took 108 of a 110 HP bar *on its own*
# while every other room on the floor took about 8 — the floor had no ramp at
# all, just a boss-shaped cliff at the end. At these values the boss takes
# roughly two-thirds of the bar, which is a real fight that potions decide
# rather than an execution.
ROOM_ARCHETYPES = {
    "entrance": {
        "tier": "safe", "safe": True, "hp_mult": 0.0, "atk_mult": 0.0,
        "blurb": "Cold air, a broken stair, and the sound of something enormous below.",
    },
    "combat": {
        # Mobs were a walkover: at 1.0/1.0 an ordinary room cost 1-2 turns and
        # 3-4 HP out of 125. Nine of those rooms in a row is not difficulty, it
        # is a victory lap, and it is why the boss felt like the only real fight
        # on the floor. 1.2/1.18 makes a mid-depth mob a genuine 4-6 turn fight
        # that actually moves the health bar.
        "tier": "mob", "safe": False, "hp_mult": 1.2, "atk_mult": 1.18,
        "blurb": "Something moved in here while you were reading the sign.",
    },
    "shrine": {
        "tier": "safe", "safe": True, "hp_mult": 0.0, "atk_mult": 0.0,
        # 38 -> 58. Where_do_they_die.py showed *every* death in a 200-run sample
        # was the boss, and players arrived there on 24% of a health bar — so the
        # boss was not reading as hard, it was reading as unwinnable, because
        # nine rooms of attrition had already decided the fight.
        #
        # The shrine sits at depth 5, halfway up, which is exactly where the
        # floor's designed "somewhere to breathe" beat belongs. Raising it fixes
        # the arrival problem without softening the boss itself, which is what
        # we actually want to be hard.
        "restore": 58,
        "blurb": "A dead technician's coolant still trickles. Stand in it. Once.",
    },
    "elite": {
        # Back down from 1.8/1.45, and then again from 1.65/1.35. The mini-bosses
        # are not where the difficulty should live: two of them sit between the
        # player and the boss, and at 1.65 each they drained the health bar so
        # badly that players arrived at the boss nearly dead — which made the
        # *boss* unwinnable (15%) rather than making the mini-bosses satisfying.
        # They now apply real pressure (a player can lose here) without
        # pre-spending the resource the boss fight is supposed to test.
        "tier": "mini-boss", "safe": False, "hp_mult": 1.5, "atk_mult": 1.28,
        "blurb": "It has been waiting at the top of the stairs, and it has not been idle.",
    },
    "gate": {
        "tier": "mini-boss", "safe": False, "hp_mult": 1.7, "atk_mult": 1.34,
        "blurb": "The last thing between you and the root. It knows you are coming.",
    },
    "boss": {
        "tier": "boss", "safe": False, "hp_mult": 2.35, "atk_mult": 1.38,
        # The boss's HP is capped here rather than left to the curve, because the
        # depth curve alone made it a ~13-turn fight that dealt more damage than
        # one full health bar. That is only winnable by healing, which meant a
        # player who never drank could not win it *at any potion budget* — the
        # potion economy was doing the only work. Bounding it keeps the fight
        # long enough to be a boss and short enough that raw skill plus a couple
        # of potions is a legitimate path.
        #
        # Raised 132 -> 141. At 132 the boss died in 98.3% of runs at three
        # potions (target 55-85%): the fight the whole floor points at was a
        # formality, which is the complaint this is fixing.
        #
        # Chosen by sweeping the cap and measuring (tune_boss.py), then confirmed
        # against the full report. At 141 the boss wins 50.0% of three-potion runs
        # (target 55-85%) — up from 98.3% before any of this — and the whole
        # floor moved with it: 4 potions went 99.2% -> 55.8%, 7 potions 100% ->
        # 83.3%. 138 is the measured sweet spot from the same sweep: the rate is
        # steep around here (82.8% at 135, 68.5% at 138, 61.8% at 141), so this
        # buys the last few points of target without spending much margin.
        "hp_cap": 138,
        "blurb": "The thing the whole building was built around.",
    },
}

# Depth curve. HP and ATK are linear in `depth`, then scaled by the archetype.
#
# `per_depth` is deliberately gentle. A steep curve front-loads difficulty into
# the last two rooms, which felt right in isolation ("the boss hits hard") and
# played terribly in sequence: the first five rooms cost no HP at all and the
# boss then took more than a full health bar on its own. A gentle slope spends
# the player's health bar gradually, so the boss is a climax rather than a
# second wall after the first one.
#
# These two numbers are the whole difficulty curve, and they are tuned against
# tools/balance.py rather than guessed: with a steeper slope the floor became
# unwinnable without potions; with a gentler one it fell to a walkover. At these
# values the boss costs roughly two-thirds of a fresh health bar on its own,
# which leaves room for both the fight and the potions that decide it.
# Overshot on the first pass. With the steeper curve, buffed mobs, mini-bosses at
# 1.8/2.1 AND the clear-heal halved, the floor became unwinnable at *every*
# budget — 0% clear with 7 potions — because attrition across nine rooms left a
# player too spent to survive the mini-boss, never mind the boss. The lesson is
# that difficulty compounds: raising the curve and cutting the clear-heal in the
# same pass multiplies rather than adds. The curve is back near its old shape and
# the difficulty is concentrated where the player feels it — the named fights.
ENEMY_HP = {"base": 24.0, "per_depth": 4.8}
ENEMY_ATK = {"base": 4.1, "per_depth": 0.52}

# One week's weather. Seeded from the week, identical for every player, so the
# leaderboard stays comparable. `weight` is the relative chance of drawing it.
WEEKLY_MODIFIERS = (
    {"name": "Standard Cycle", "hp_mult": 1.0, "atk_mult": 1.0, "weight": 4,
     "blurb": "Nothing unusual. The building is behaving."},
    {"name": "Overclock", "hp_mult": 1.15, "atk_mult": 1.0, "weight": 2,
     "blurb": "Everything on this floor is running hot."},
    {"name": "Cascade Failure", "hp_mult": 1.0, "atk_mult": 1.18, "weight": 2,
     "blurb": "The floor is venting. Everything here hits harder this week."},
    {"name": "Root Access", "hp_mult": 1.12, "atk_mult": 1.12, "weight": 1,
     "blurb": "Someone left root access open. Nobody is saying who."},
    {"name": "Deep Sleep", "hp_mult": 0.88, "atk_mult": 0.88, "weight": 1,
     "blurb": "The machines are dormant. Take the gift while it lasts."},
)

# Creature pools, drawn per week. Bosses get a title on top of their name.
ENEMY_NAMES = {
    "mob": ["Slime", "Goblin", "Skeleton", "Crawler", "Ghoul", "Imp", "Wisp", "Rust Hound"],
    "mini-boss": ["Orc Captain", "Wraith", "Ogre", "Harpy", "Golem", "Revenant",
                  "Bog Tyrant", "Rime Warden"],
    "boss": ["The Null Warden", "Root Daemon", "Colossus of Vault",
             "The Leviathan Node", "Kernel Wyrm"],
}
BOSS_TITLES = ["Keeper of the Last Archive", "Prime Process",
               "The Thing Beneath The Stack", "Sovereign of the Root"]

# One line of room atmosphere, drawn per week so a room you already know still
# reads differently after a reset.
ROOM_FLAVOR = {
    "entrance": ["You can still smell the coffee someone left here on Monday."],
    "combat": [
        "Racks toppled in a line, like something walked through at speed.",
        "Every screen shows the same six seconds of the same crash.",
        "Something has been chewing the cable runs.",
        "The lights come back on for one second when you enter.",
        "Ice on the floor, in a room with no broken ceiling.",
    ],
    "shrine": [
        "Coolant, still cold. It smells like ozone and a held breath.",
        "Somebody propped a terminal upright here. It still has their initials on it.",
    ],
    "elite": [
        "The floor around it is scorched in a perfect circle.",
        "It does not look up. It does not need to.",
    ],
    "gate": [
        "The seal is a suggestion. The room behind it is not.",
        "Half the vault door is already open, from the other side.",
    ],
    "boss": [
        "The room is larger than the building should allow.",
        "It has been awake for the entire outage, and it is not surprised to see you.",
        "Every cable in the building ends here, and all of them are taut.",
    ],
}

# --- Player --------------------------------------------------------------
# Flat base stats. There are no levels; potions are the only variable layer.
# `max_hp` is deliberately a whole week of incoming damage's worth of slack:
# tools/balance.py asserts the floor's expected damage lands inside the
# "3–5 potions of healing" band that a real week of quests can pay for.
PLAYER_BASE = {
    "max_hp": 125,
    "atk": 12,
    "defense": 3,
}

# --- Potions -------------------------------------------------------------
# How many potions one completion can pay, and the bounds of that range. The
# player never chooses a number: the classifier scores how much effort the task
# actually is, and the score is mapped onto MIN..MAX here. Change these two and
# every existing quest re-scales, because quests store the score, not the count.
POTION_MIN = 1
POTION_MAX = 4

# If the classifier cannot be reached, quests fall back to the bottom of the
# range. Failing closed matters: paying out the maximum on an API outage would
# mean anyone could improve their week by breaking the network.
POTION_FALLBACK = POTION_MIN

POTION_CATEGORIES = ("heal", "damage", "haste", "shield")

# What each potion does once drunk. `turns` counts the player's own actions, and
# the buff is spent when it hits zero or the fight ends — whichever comes first.
#
# Heal is the workhorse and the only category that scales; the other three are
# tempo, and are strong enough to win a fight outright but not to replace
# healing on a long one. Drinking costs a turn, so none of them is free.
POTION_EFFECTS = {
    "heal": {"label": "Healing Draught", "short": "Heal", "heal": 65},
    "damage": {"label": "Rage Tonic", "short": "Rage", "turns": 3, "mult": 1.7},
    "haste": {"label": "Haste Elixir", "short": "Haste", "turns": 3, "mult": 2.0},
    "shield": {"label": "Aegis Serum", "short": "Aegis", "turns": 2, "reduction": 0.5},
}

DEFAULT_CATEGORY = "heal"

# Keyword fallback for the potion categorizer. Ordered: first match wins, so
# put specific words above general ones. This is the shipping path — the
# classifier in categorize.py only refines it.
POTION_CATEGORY_KEYWORDS = {
    "heal": ["sleep", "rest", "nap", "water", "hydrate", "eat", "meal", "walk",
             "stretch", "yoga", "meditate", "breathe", "recover", "health"],
    "damage": ["gym", "run", "lift", "workout", "exercise", "train", "push",
               "sprint", "fight", "practice", "code", "write", "ship", "study"],
    "haste": ["rush", "quick", "fast", "urgent", "deadline", "submit", "finish",
              "clean", "tidy", "organize", "inbox", "quickly"],
    "shield": ["protect", "backup", "save", "review", "check", "plan", "prepare",
               "budget", "insurance", "backup", "safety"],
}

# How the classifier weighs each potion. These descriptions do the real work:
# the model picks between criteria rather than inventing a label, so "recovery,
# food, sleep" is a much better signal for Heal than the bare word "heal".
POTION_CATEGORY_CRITERIA = {
    "heal": "rest, recovery, food, water, sleep, stretching, looking after yourself",
    "damage": "training, effort, pushing hard, focused deep work, attacking a deadline",
    "haste": "speed, urgency, clearing a backlog, finishing something quickly",
    "shield": "protecting yourself, reviewing, planning, saving up, preparing for later",
}

# The classifier picks the repeat window too, so the player never chooses one.
# Each option describes how often someone would genuinely do this, which is the
# judgement we want rather than "whatever the user felt like clicking".
KIND_CRITERIA = {
    "daily": "a daily habit, done most days",
    "monthly": "a recurring chore, done roughly once a month",
    "goal": "a one-off achievement, done once and finished",
}

# The effort scale handed to the classifier as an ordered list. It answers with
# a continuous score across these indices, which is normalized to 0..1 and then
# mapped onto POTION_MIN..POTION_MAX. Ordered least effort to most.
EFFORT_SCALE = [
    "takes seconds",
    "a few minutes",
    "a real chunk of an evening",
    "most of a day",
    "a multi-day effort",
]

# Fallbacks for each field the classifier fills in, applied independently when
# it cannot be reached. See POTION_FALLBACK for why the effort one fails low.
DEFAULT_KIND = "daily"

# --- Combat --------------------------------------------------------------
# One damage formula for everything: roll a flat variance band, apply the
# multipliers, floor at MIN_DAMAGE. There is no armour that grows without bound
# and no attacker stat that outruns the curve, so nothing trivialises a fight
# and nothing becomes unwinnable by attrition.
DAMAGE_VARIANCE = (0.85, 1.15)
CRIT_CHANCE = 0.12
CRIT_MULT = 1.5
POWER_MULT = 2.2
POWER_COOLDOWN = 3
DEFEND_HEAL = 8
DEFEND_REDUCTION = 0.35
MIN_DAMAGE = 1

# HP regained on clearing a room. This is the fix for floor attrition, and it
# fixes a design bug at the same time: without it, *fleeing* was strictly better
# than winning a fight, because winning cost you HP and fleeing cost you nothing.
# A clear now pays back more than it costs, so pressing on is the rational play
# and the floor is paced as a sequence of fights with a beat between them.
#
# Sized against the depth curve: the gaps between rooms do ~12-30 damage, so a
# flat 10 across nine fights roughly replaces what the easy rooms take, leaving
# the *hard* rooms as the real attrition. That keeps the boss the wall it should
# be without the player walking in already dead.
#
# It is deliberately not larger than this. At 10 the early rooms still net a
# small loss or a wash, so a player arrives at the boss genuinely spent; at 20
# the first half of the floor became free and the boss had to be the entire
# difficulty budget by itself, which reads as a cliff rather than a ramp.
#
# 10 -> 12, which is an *increase* from the original and deliberately so. The
# first pass cut it to 5 alongside a steeper curve, which made the floor
# unwinnable — difficulty compounds, and the clear-heal is the main thing
# offsetting it. Raising the curve while raising the heal keeps the early rooms a
# genuine warm-up (trace_hp.py showed the player at full HP through five rooms)
# while stopping the back half from draining the bar to nothing before the boss.
# The boss is where the difficulty belongs, not the walk-up.
#
# Still bounded: at 20 the first half of the floor became free and the boss had to
# carry the entire difficulty budget alone, which reads as a cliff, not a ramp.
ROOM_CLEAR_HEAL = 12

# Hard ceiling on a single turn's damage. Without it, high-variance + crit +
# power + rage can one-shot a boss, which reads as a bug and skips the fight the
# whole floor is built around. The boss's HP is set above this on purpose.
MAX_DAMAGE = 45

# --- Boss behaviour -------------------------------------------------------
# A boss should not be "the same fight, but more HP". Three things make it feel
# like a different encounter, all resolved server-side by game.fight_step:
#
#   * a wind-up telegraph on a cadence, so the big hit is dodgeable by reading
#     the room rather than by luck (DEFEND cuts a *telegraphed* hit hardest);
#   * a phase change once, at half health, which is where most boss fights die
#     of boredom rather than damage;
#   * a fight length cap, so a player who turtles forever loses on the clock
#     instead of stalemating.
#
# `special_mult` is the telegraphed hit, `every` is its cadence in enemy turns.
BOSS = {
    # 2.4 -> 2.9 and 1.35 -> 1.55 were both tried together with a 165 HP boss and
    # overshot hard; these sit between the old values and that attempt. The boss
    # should be able to end a careless player's run, not every player's run.
    "special_mult": 2.6,
    "special_every": 3,
    "telegraph": "The floor lights run toward it. It is winding up.",
    "phase_at": 0.5,
    "phase_mult": 1.45,
    "phase_text": "It sheds a shell of casing and something underneath wakes up.",
    "turn_limit": 40,
}

# Mini-bosses telegraph too, but far more gently — enough to teach the mechanic
# before the boss demands it.
MINI_BOSS = {
    "special_mult": 2.1,
    "special_every": 4,
    "telegraph": "It draws itself up, and the shadows lean in.",
    "phase_at": 0.35,
    "phase_mult": 1.4,
    "phase_text": "It stops holding back.",
    "turn_limit": 25,
}

# --- Classifier (optional) ------------------------------------------------
# The categorizer falls back to keywords when these are unset or the call
# fails. Never let this take down task creation.
#
# The key is read from the environment, falling back to a local untracked .env
# so a teammate can drop a key in a file and go. On Render it is a real
# environment variable and the file is not there.
CLASSIFIER_API_KEY = _read_env("CLASSIFIER_API_KEY") or _read_env("KEY")
CLASSIFIER_MODEL = _read_env("CLASSIFIER_MODEL", "jev-latest")
CLASSIFIER_URL = "https://ai.hackclub.com/proxy/v1/jev/systemone"
# Generous, because this runs inline in POST /api/tasks and a reasoning model
# is slower than a plain completion. Still bounded: the keyword path is
# instant, and a timeout just means we fall back to it.
CLASSIFIER_TIMEOUT = 6.0

KIND_LABEL = {"daily": "Daily", "monthly": "Monthly", "goal": "Goal"}
