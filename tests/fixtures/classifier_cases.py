"""The shared `(title, expected potion)` table.

Imported by both tiers of the classifier tests so they cannot drift apart:

- `tests/test_classifier_golden.py` runs it **offline**, against
  `categorize._from_keywords`. That is the path the game falls back to whenever
  the model is unsure, so it is worth pinning exactly.
- `tools/score_classifier.py` runs it **live**, against the real model. Only
  that tier can tell you whether a rewrite of `POTION_CATEGORY_CRITERIA`
  helped — the criteria are strings the model reads, so nothing offline can
  measure them.

**How the expected column was written.** From the mechanical definitions in
`config.POTION_EFFECTS`, not from whatever the classifier happens to say today.
A golden set recorded from the implementation asserts nothing and freezes every
bug in place. Read each row as "what potion should finishing this give you":

- **heal** — you end up with more health
- **damage** — your existing attacks hit harder
- **haste** — you get more actions in the same time
- **shield** — what comes at you lands softer

Two rows deliberately have **no** expected category. They are not failures to
classify; they are the shape of an honest miss. `_from_keywords` returning
`None` is the contract that stops a miss being laundered into
`DEFAULT_CATEGORY`, which is `heal` — the disease this whole change is about.
A table that never contains a miss cannot detect it coming back.

These are everyday titles, not adversarial ones. The point is coverage of
ordinary vocabulary, because coverage is the thing that was broken: before the
table was widened, 14 of these fell through to the default and read as heal.
"""

# A deliberate miss, plus the two that used to be caught by substring matching
# ("rest" inside "restaurant", "eat" inside "meeting"). None of the three may
# come back as a category.
MISSES = [
    "zzz qqq",
    "visit the restaurant on friday",
    "attend the meeting",
]

# (title, expected category), ordered as the categories appear in config.
CASES = [
    # --- heal: genuinely restorative -------------------------------------
    ("sleep eight hours", "heal"),
    ("make the bed", "heal"),
    ("stretch for 10 minutes", "heal"),
    ("eat the leftovers", "heal"),
    ("call the dentist", "heal"),
    # --- damage: force, or a hard stretch of focused work -----------------
    ("go for a 5k run", "damage"),
    ("read 30 pages", "damage"),
    ("bike to work", "damage"),
    ("mow the lawn", "damage"),
    ("ship the refactor", "damage"),
    # --- haste: more done in the same time --------------------------------
    ("answer emails", "haste"),
    ("do a load of laundry", "haste"),
    ("grocery shop", "haste"),
    ("clear my inbox", "haste"),
    # --- shield: hardening against what is coming ------------------------
    ("pay the bills", "shield"),
    ("feed the cat", "shield"),
    ("review the contract", "shield"),
    ("file the taxes", "shield"),
]

ALL = CASES