"""Decide which potion a task rewards.

The keyword rules below are the shipping path: deterministic, offline, and
instant. The optional classifier refines that guess, but it can only ever
narrow the result to one of POTION_CATEGORIES — it cannot invent a category,
and it cannot change how *many* potions are awarded. That keeps the reward
economy server-authoritative no matter what the model returns.

Call this once, when a task is created. The answer is cached on the task row,
so nothing in the gameplay request path ever waits on a network call.
"""

import json
import urllib.error
import urllib.request

from . import config


def category_for(title: str, kind: str) -> str:
    """Best-guess potion category for a task. Never raises."""
    fallback = _from_keywords(f"{title} {kind}")
    refined = _from_classifier(title, kind)
    return refined if refined in config.POTION_CATEGORIES else fallback


def _from_keywords(text: str) -> str:
    lowered = text.lower()
    for category, words in config.POTION_CATEGORY_KEYWORDS.items():
        if any(word in lowered for word in words):
            return category
    return config.DEFAULT_CATEGORY


def _from_classifier(title: str, kind: str) -> str | None:
    """Ask the classifier for a category. Returns None on any problem.

    Any missing config, network error, timeout, malformed response, or
    out-of-range answer falls through to the keyword result. A demo must never
    fail because an API was slow.
    """
    key, model = config.CLASSIFIER_API_KEY, config.CLASSIFIER_MODEL
    if not key or not model:
        return None

    options = ", ".join(config.POTION_CATEGORIES)
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You classify real-life tasks by which potion reward they "
                    f"should grant. Reply with exactly one word from: {options}."
                ),
            },
            {"role": "user", "content": f"Task: {title}\nType: {config.KIND_LABEL.get(kind, kind)}"},
        ],
    }
    request = urllib.request.Request(
        f"{config.CLASSIFIER_BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=config.CLASSIFIER_TIMEOUT) as response:
            payload = json.loads(response.read())
        text = payload["choices"][0]["message"]["content"].strip().lower()
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError):
        return None

    for category in config.POTION_CATEGORIES:
        if category in text:
            return category
    return None
