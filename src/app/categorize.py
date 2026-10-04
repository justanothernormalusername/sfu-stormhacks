"""Decide what a task rewards: which potion, how many, and how often it repeats.

Everything here is a *judgement about the task*, made once when the task is
created and cached on its row, so nothing in the gameplay request path ever
waits on a network call.

Three questions go out in a single request, because the proxy takes a set of
named questions per call:

- **choice** — which potion flavour fits
- **choice** — how often someone would genuinely repeat this
- **score**  — how much effort it is, on an ordered scale

The model can only pick from criteria this file supplies, so it cannot invent a
potion kind or a repeat window. The potion *count* is not asked for at all: the
score is mapped onto a bounded range here, in config, which means the player
cannot write a task title that talks the model into a bigger reward, and a
teammate can retune the whole economy by changing two numbers.

Every failure path returns a usable answer. A missing key, a timeout, a
malformed response, or a value the game does not define falls back field by
field — the keyword rules for the category, a daily for the repeat window, and
the bottom of the range for the reward.

The repeat window in particular is only a *suggestion*. How often someone would
genuinely repeat a task is a fact about the player's intent, which a title
cannot carry — the model reads "Go for a 5k run" as a one-time goal at 53%
confidence, which would lock the quest forever. The player overrides it.
"""

import json
import re
import urllib.error
import urllib.request

from . import config

_WORDS = re.compile(r"[a-z]+")


def classify(title: str) -> dict:
    """Judge a task. Never raises, always returns every field.

    `difficulty` is normalized to 0..1 regardless of how the model expressed it,
    so a change to the length of EFFORT_SCALE does not silently rescale rewards.
    """
    answers = _from_classifier(title)
    return {
        "category": _category(answers, title),
        "kind": _valid(answers.get("kind"), config.KIND_CRITERIA)
        or config.DEFAULT_KIND,
        "difficulty": _normalized(answers.get("effort")),
    }


def _category(answers: dict, title: str) -> str:
    """One potion category, from whichever source is most trustworthy.

    A confident model answer wins. Otherwise the keyword table decides, and only
    if it too comes up empty does the default apply.

    This ordering is the fix for a real bias: the keyword table used to be
    consulted only when the entire call failed, and *its* miss answered
    DEFAULT_CATEGORY. With no key configured, two thirds of ordinary titles
    therefore became heal — the fallback was the common case, not the last resort.
    Now a miss stays a miss all the way here, where it is visible.
    """
    chosen = _valid(answers.get("potion"), config.POTION_CATEGORIES)
    if chosen and _confident(answers.get("potion_raw")):
        return chosen
    return _from_keywords(title) or config.DEFAULT_CATEGORY


def _confident(answer) -> bool:
    """Is this answer worth believing?

    The API returns a `probabilities` map over every option, and the parser used
    to throw it away — so an answer the model was barely sure of was accepted
    exactly like a confident one. Read the probability of the option actually
    chosen, and treat anything unparseable as unconfident: a malformed
    distribution must never read as certainty.

    Read `probabilities[choice]`, never the sibling `confidence` field. They
    disagree on a live call (0.86 vs 0.9), so `confidence` is on its own scale
    and cannot be thresholded against one.
    """
    if not isinstance(answer, dict):
        return False
    choice, probs = answer.get("choice"), answer.get("probabilities")
    if not isinstance(choice, str) or not isinstance(probs, dict):
        return False
    top = probs.get(choice)
    if isinstance(top, bool) or not isinstance(top, (int, float)):
        return False
    return top >= config.POTION_CONFIDENCE_MIN


def potions_for(difficulty: float | None) -> int:
    """How many potions a completion of this task pays.

    Derived from the cached score rather than stored, so POTION_MIN/POTION_MAX
    remain the single source of truth for the economy. A task with no score —
    created while the classifier was unreachable — pays the fallback.
    """
    if difficulty is None:
        return config.POTION_FALLBACK
    span = config.POTION_MAX - config.POTION_MIN
    return max(config.POTION_MIN, min(config.POTION_MAX,
                                      round(config.POTION_MIN + difficulty * span)))


def _valid(value: str | None, allowed) -> str | None:
    """Trust the answer only as far as the game defines it."""
    return value if value in allowed else None


def _from_keywords(text: str) -> str | None:
    """Match whole words, and admit it when nothing matched.

    Substring matching put "restaurant" in the heal bucket via "rest", and
    "meeting" there via "eat". Splitting into words fixes both, and costs
    nothing.

    Plural forms are folded in, because whole-word matching drops them: without
    this, "answer emails" and "pay the bills" miss an `email` and a `bill` that
    are in the table. Only a trailing "s" is stripped, which covers the ordinary
    cases without the false stems a real stemmer introduces.

    Returning None matters more than the fix. This used to answer
    DEFAULT_CATEGORY whenever nothing matched, which silently swallowed most real
    task titles — the caller now decides, so a miss stays visible.
    """
    words = set()
    for word in _WORDS.findall(text.lower()):
        words.add(word)
        if word.endswith("s") and len(word) > 3:
            words.add(word[:-1])
    for category, keys in config.POTION_CATEGORY_KEYWORDS.items():
        if words & set(keys):
            return category
    return None


def _normalized(raw) -> float | None:
    """Pull 0..1 out of a raw score, whatever shape it arrived in.

    The model interpolates across EFFORT_SCALE, so the score runs from 0 to
    len(scale) - 1. Dividing by that span is what makes the stored value
    independent of how many rungs the scale has.
    """
    # bool is an int subclass, so it has to be excluded explicitly — a JSON
    # `true` would otherwise normalize to a real effort score.
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    span = max(1, len(config.EFFORT_SCALE) - 1)
    return max(0.0, min(1.0, raw / span))


def _field(answers, name: str, key: str):
    """One field of one answer, or None if the response was not that shape.

    `answers.get(name, {})` is not enough on its own: a response carrying
    `"potion": null` returns None, and `None.get` raises AttributeError — which
    is not one of the exceptions the caller below catches, so a single null in
    the payload would 500 task creation instead of falling back.
    """
    answer = answers.get(name) if isinstance(answers, dict) else None
    return answer.get(key) if isinstance(answer, dict) else None


def _from_classifier(title: str) -> dict:
    """One request, three questions. Returns {} on any problem.

    A demo must never fail because an API was slow, unreachable, or changed
    shape — so every exception here is swallowed and the caller falls back.
    """
    key, model = config.CLASSIFIER_API_KEY, config.CLASSIFIER_MODEL
    if not key or not model:
        return {}

    body = {
        "model": model,
        "state": title,
        "questions": {
            "potion": {
                "type": "choice",
                "instructions": (
                    "Which potion should this real-life task reward? Judge what "
                    "doing the task actually does for the person afterwards, not "
                    "what it is about. A task about sleep that is really about a "
                    "deadline is haste, not heal. " + config.POTION_CATEGORY_TIEBREAK
                ),
                "criteria": config.POTION_CATEGORY_CRITERIA,
            },
            "kind": {
                "type": "choice",
                "instructions": (
                    "How often would someone genuinely repeat this, without being "
                    "asked? Pick the window they would actually keep up. When it "
                    "is genuinely unclear, prefer the window that allows repeats."
                ),
                "criteria": config.KIND_CRITERIA,
            },
            "effort": {
                "type": "score",
                "instructions": (
                    "How much real effort does doing this take, on a normal day "
                    "when nobody is motivating the person? Judge time and energy "
                    "together — a hard ten-minute task is not a long easy one."
                ),
                "criteria": config.EFFORT_SCALE,
            },
        },
    }
    request = urllib.request.Request(
        config.CLASSIFIER_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=config.CLASSIFIER_TIMEOUT) as response:
            payload = json.loads(response.read())
        answers = payload["answers"]
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError):
        return {}

    return {
        "potion": _field(answers, "potion", "choice"),
        # The whole answer object, so `_confident` can read the `probabilities`
        # the choice came with. The three plain fields above cannot carry it.
        "potion_raw": answers.get("potion") if isinstance(answers, dict) else None,
        "kind": _field(answers, "kind", "choice"),
        "effort": _field(answers, "effort", "score"),
    }
