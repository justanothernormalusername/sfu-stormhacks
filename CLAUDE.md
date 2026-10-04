# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- Run dev server: `.venv/Scripts/python -m uvicorn src.app.main:app --reload` (Windows venv; run from repo root so `src.app` imports resolve)
- Deps: `.venv/Scripts/python -m pip install -r requirements.txt`. `tzdata` is required on Windows for `zoneinfo`.
- Reset local data: delete `dungeon.db` (tables are created on startup via `init_db`; there are no migrations, so schema changes need a fresh DB).

## Architecture

- All game rules live server-side in `src/app/game.py` and are enforced in `src/app/routes/api.py`: rooms unlock only if the task has a `Completion` in the current period, and XP comes only from `RoomClear` rows (one per completion). The Phaser client (`static/game/main.js`) resolves fights for feel but only renders API results. Keep it that way: the plan is to possibly swap Phaser for a Godot web export served at `/play`, so the API must stay engine-agnostic.
- `Completion` rows are append-only (never edit or delete them). Archiving a task sets `active=False` so the friends-visible log stays intact.
- Timestamps are stored as naive UTC (`NaiveDatetime`; SQLModel rejects naive values on plain `datetime` fields). Day/month boundaries use `APP_TZ` (default `America/Vancouver`) via `game.to_local`. Never compare against UTC midnight.
- HTML pages (`routes/pages.py`, `templates/`) are thin shells; their data comes from the JSON API via `static/app.js` (`api()`, `el()`). Render user text with `textContent`/`el()`, never `innerHTML`.
- Auth is a signed session cookie (`SessionMiddleware`, `SECRET_KEY` env var) with stdlib PBKDF2 password hashing in `auth.py`.

## Gotchas

- On Windows, Python's default file encoding is cp1252. Always pass `encoding="utf-8"` when scripting file edits; the templates contain emoji.
- Never commit API keys (the user routes Claude Code through OpenRouter via user-level env vars; use placeholders in any docs).
