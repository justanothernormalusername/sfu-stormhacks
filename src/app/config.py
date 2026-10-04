"""Every balance number in the game, in one place.

The owner is not balancing these alone — teammates are picking this up — so
nothing below should be duplicated as a literal anywhere else in the backend or
the client. Change a number here and the whole game moves with it.
"""

import os

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
# Quantity earned per completion, keyed by task kind. The weekly reset is the
# cap: a daily can pay out at most seven times a week.
POTIONS_BY_KIND = {"daily": 1, "monthly": 2, "goal": 4}

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
CLASSIFIER_API_KEY = os.environ.get("CLASSIFIER_API_KEY")
CLASSIFIER_MODEL = os.environ.get("CLASSIFIER_MODEL")
CLASSIFIER_BASE_URL = "https://openrouter.ai/api/v1"
CLASSIFIER_TIMEOUT = 2.0

KIND_LABEL = {"daily": "Daily", "monthly": "Monthly", "goal": "Goal"}
