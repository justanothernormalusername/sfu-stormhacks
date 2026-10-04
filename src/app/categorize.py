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
"""

import json
import urllib.error
import urllib.request

from . import config


def classify(title: str) -> dict:
    """Judge a task. Never raises, always returns every field.

    `difficulty` is normalized to 0..1 regardless of how the model expressed it,
    so a change to the length of EFFORT_SCALE does not silently rescale rewards.
    """
    answers = _from_classifier(title)
    return {
        "category": _valid(answers.get("potion"), config.POTION_CATEGORIES)
        or _from_keywords(f"{title} {config.DEFAULT_KIND}"),
        "kind": _valid(answers.get("kind"), config.KIND_CRITERIA)
        or config.DEFAULT_KIND,
        "difficulty": _normalized(answers.get("effort")),
    }


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


def _from_keywords(text: str) -> str:
    lowered = text.lower()
    for category, words in config.POTION_CATEGORY_KEYWORDS.items():
        if any(word in lowered for word in words):
            return category
    return config.DEFAULT_CATEGORY


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
                    "doing the task actually is, not how urgent it feels."
                ),
                "criteria": config.POTION_CATEGORY_CRITERIA,
            },
            "kind": {
                "type": "choice",
                "instructions": (
                    "How often would someone genuinely repeat this, without being "
                    "asked? Pick the window they would actually keep up."
                ),
                "criteria": config.KIND_CRITERIA,
            },
            "effort": {
                "type": "score",
                "instructions": (
                    "How much real effort does doing this take, on a normal day "
                    "when nobody is motivating the person?"
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
        "kind": _field(answers, "kind", "choice"),
        "effort": _field(answers, "effort", "score"),
    }