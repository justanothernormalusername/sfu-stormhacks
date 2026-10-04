"""Every balance number in the game, in one place.

The owner is not balancing these alone — teammates are picking this up — so
nothing below should be duplicated as a literal anywhere else in the backend or
the client. Change a number here and the whole game moves with it.
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
WEEK_START_DAY = 0  # Monday

# --- The weekly dungeon --------------------------------------------------
# The map is generated once per week and is identical for every player.
ROOM_COUNT = 12

# Fraction of the map at which each enemy tier begins. Earlier = easier.
TIER_SPLIT = (0.5, 0.8)

ENEMY_TIERS = {
    "mob": {
        "names": ["Slime", "Goblin", "Skeleton", "Bat", "Ghoul", "Imp"],
        "hp": 30,
        "atk": 5,
    },
    "mini-boss": {
        "names": ["Orc Captain", "Wraith", "Ogre", "Harpy", "Golem"],
        "hp": 70,
        "atk": 8,
    },
    "boss": {
        "names": ["Dragon", "Lich King", "Demon Lord", "Colossus"],
        "hp": 120,
        "atk": 12,
    },
}

# Names for the rooms themselves, drawn per week.
ROOM_NAMES = [
    "Flooded Barracks", "The Rust Hatch", "Collapsed Server Farm", "Ashfall Corridor",
    "Drowned Archives", "The Thermal Vault", "Broken Consensus", "The Null Chapel",
    "Fractured Kernel", "The Silent Queue", "Rotting Datacenter", "The Root Chamber",
    "Shattered Index", "The Overclock", "Bleeding Cores", "The Final Daemon",
]

# --- Player --------------------------------------------------------------
# Flat base stats. There are no levels; potions are the only variable layer.
PLAYER_BASE = {
    "max_hp": 100,
    "atk": 12,
    "defense": 2,
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
POTION_EFFECTS = {
    "heal": {"label": "Healing Draught", "short": "Heal", "heal": 35},
    "damage": {"label": "Rage Tonic", "short": "Rage", "turns": 3, "mult": 1.6},
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
DAMAGE_VARIANCE = (0.8, 1.2)
CRIT_CHANCE = 0.12
CRIT_MULT = 1.5
POWER_MULT = 2.2
POWER_COOLDOWN = 3
DEFEND_HEAL = 6
DEFEND_REDUCTION = 0.3
MIN_DAMAGE = 1

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
