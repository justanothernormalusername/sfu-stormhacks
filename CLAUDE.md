# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- Run dev server: `.venv/Scripts/python -m uvicorn src.app.main:app --reload` (Windows venv; run from repo root so `src.app` imports resolve)
- Deps: `.venv/Scripts/python -m pip install -r requirements.txt`. `tzdata` is required on Windows for `zoneinfo`.
- Tests: `PYTHONPATH=. .venv/Scripts/python tests/test_combat.py` (and `test_classifier`, `test_bugs`, `test_race`, `floor_run`). They are plain runnable scripts, not pytest — each prints what it found and exits non-zero on failure.
- Retune the floor: `PYTHONPATH=. .venv/Scripts/python tools/balance.py` (Monte-Carlo). **Run it after touching anything in the `PLAYER_`, `POTION_`, `ENEMY_`, or `ROOM_ARCHETYPES` blocks in `config.py`.**
- Reset local data: delete `dungeon.db` (tables are created on startup via `init_db`; there are no migrations, so schema changes need a fresh DB).

## Architecture

- **All balance numbers live in `src/app/config.py` and nowhere else.** The public half is served verbatim at `/api/config`, so the client renders with exactly the numbers the server enforces. The file is grouped into `--- SECTION ---` banners with an index in its module docstring, and `BOSS_HP_CAP` is additionally overridable per-deploy from the environment or `.env` (`none` = unbounded).
- **`/api/config` reads config attributes *by name*, so a deleted or renamed constant does not fail at import — it 500s at request time**, on a URL the Phaser client fetches inside a `Promise.all` during boot, leaving `/play` stuck on "Loading dungeon..." while every other page works. It reads as a broken server rather than a missing number. `tests/test_bugs.py` cases 7 and 8 exist to catch exactly this.
- **`BOSS_HP_CAP` is a ceiling, not the value.** The depth curve produces ~194 HP for the boss, so while the cap binds, `ROOM_ARCHETYPES["boss"]["hp_mult"]` has no visible effect. Check which of the two is actually deciding before tuning either.
- **Almost nothing is stored; it is derived.** Run depth is the furthest cleared `BattleClear` (`furthest_room_index`, safe rooms excluded). The potion inventory is `Completions − PotionUses`, weekly — and a `PotionUse` row is written *the moment a potion is drunk*, not when the fight ends, so abandoning a fight cannot refund what was already spent. Current HP is `hp_after` on the furthest cleared row. A quest's potion *count* is recomputed from its cached effort score on every read, so retuning `POTION_MIN`/`POTION_MAX` re-scales every existing quest. Keep it that way: it is the strongest correctness claim in the project.
- **Death resets the run** (`record_fight_loss`): the week's `BattleClear` rows are deleted, in-progress fights dropped, and every remaining potion written out as a `PotionUse` so surviving `Completion` rows cannot refill the pack. Quests and completions are untouched — the friends-visible log outlives the run. Those compensating rows share the completions' week window, so they expire together and cannot resurrect a pack on Monday.
- The dungeon is an **authored** floor (`FLOOR_ROOMS`, `FLOOR_LINKS`, `ROOM_ARCHETYPES` in `config.py`), identical for every player in a given week; `game.floor_for_week` seeds creature names, flavour, and the weekly modifier per week. Rooms unlock by **reachability** from cleared rooms, not by task completion — tasks gate nothing.
- Tasks are preparation. `POST /api/tasks` sends only a title; `categorize.classify` decides the potion, the repeat window, and an effort score, and `game.potions_for` maps that score onto `POTION_MIN..POTION_MAX`. The model is **never asked for a number**, so no quest title can buy a reward above the max. Every field falls back independently (keywords / `DEFAULT_KIND` / `POTION_FALLBACK`), and `POTION_FALLBACK` is the floor rather than the max so an API outage cannot be exploited.
- Combat is server-side (`game.new_fight`, `game.fight_step`). The Phaser client (`static/game/main.js`) renders for feel but only ever displays API results, and the fight seed is never sent to it. Keep it that way: the plan is to possibly swap Phaser for a Godot web export served at `/play`, so the API must stay engine-agnostic.
- `fight_lock` is keyed on `(user, week)`, not `(user, room, week)` — deliberately one lock per player per week, so a death's deletes and potion writes cannot race another room's action and restore progress from the run that just ended.
- `Completion` rows are append-only (never edit or delete them). Archiving a task sets `active=False` so the friends-visible log stays intact.
- Timestamps are stored as naive UTC (`NaiveDatetime`; SQLModel rejects naive values on plain `datetime` fields). Day/month/week boundaries use `APP_TZ` (default `America/Vancouver`) via `game.to_local`. Never compare against UTC midnight.
- HTML pages (`routes/pages.py`, `templates/`) are thin shells; their data comes from the JSON API via `static/app.js` (`api()`, `el()`). Render user text with `textContent`/`el()`, never `innerHTML`.
- Auth is a signed session cookie (`SessionMiddleware`, `SECRET_KEY` env var) with stdlib PBKDF2 password hashing in `auth.py`.

## Gotchas

- `config.py` reads a local untracked `.env` as a fallback for env vars. The test suites set `CLASSIFIER_API_KEY=""` to switch the classifier off — an *explicitly empty* value wins over `.env` on purpose, so a developer's key cannot make the tests make live network calls and assert on whatever the model decided that day. Do not remove that.
- `SQLModel.metadata.create_all` creates missing **tables** but never adds **columns** to an existing one. There is no migration tool. A new column is a live-deploy hazard, not a local one — production has to be patched by hand (`ALTER TABLE ... ADD COLUMN`) before or with the deploy that starts reading it.
- On Windows, Python's default file encoding is cp1252. Always pass `encoding="utf-8"` when scripting file edits; the templates contain emoji.
- Never commit API keys (the user routes Claude Code through OpenRouter via user-level env vars; use placeholders in any docs).
