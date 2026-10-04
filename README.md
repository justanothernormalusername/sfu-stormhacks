# Task Dungeon (SFU StormHacks)

Your to-do list is a dungeon — but in v2 the list no longer *is* the map. Every player gets the same twelve-room dungeon, generated fresh each Monday and identical for everyone. There are no locked doors and nothing to unlock. Your real-life quests are preparation: finish one and it pays potions into a pack you carry into the next fight. The dungeon is beatable with potions you earned outside the app, or on nerve alone.

- **Daily** quest → 1 potion, resets every day
- **Monthly** quest → 2 potions, resets every month
- **Goal** → 4 potions, once ever
- **Potions** → four kinds (Heal, Rage, Haste, Aegis). Which one a quest pays is decided by [Jev](https://ai.hackclub.com/proxy/v1/jev/systemone), a classifier that picks between developer-defined options rather than writing text — so it cannot invent a potion kind. Keywords are the deterministic fallback whenever the model is unset, slow, or down. It can only ever narrow the choice to a real potion kind; it never decides quantities.
- **Depth** is the score. Furthest room cleared this week, on the leaderboard, next to your party. Health carries between fights; a defeat costs you the potions you drank and sends you back to your last cleared room, fully healed. Nothing else.

Every completion is timestamped by the server in a log your party can see and flag, so nobody can fake their way up.

## Nothing is a counter

There is no XP column, no level column, no potion-count column, and no "HP" field on the user. Depth is the furthest `BattleClear` row; your pack is completions minus potion-uses; your HP is the `hp_after` on your furthest cleared room. Every one of those is a sum or a max over append-only rows.

This is not just tidiness. It means the client cannot cheat by editing a number it was handed — the server recomputes from rows and simply disagrees. It is the strongest technical claim in the project, and it is enforced by the database rather than by application checks.

## Run locally

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m uvicorn src.app.main:app --reload
```

Run it from the repo root so `src.app` imports resolve. Open http://127.0.0.1:8000, click **New hero** to register, add quests on the Quest Board, press **I did it**, then head to the Dungeon.

Every balance number — enemy HP and damage, potion effects, crit chance, room count, tier splits — lives in `src/app/config.py` and nowhere else. The server publishes them at `/api/config` and the client renders with those values, so changing one number there moves the whole game.

## Stack

FastAPI + SQLModel (SQLite locally, Postgres in production), Jinja pages, and a [Phaser 3](https://phaser.io) game loaded from a CDN (no build step). Placeholder pixel art is drawn in code in `src/app/static/game/main.js` (`makeTextures`). Game rules are pure and side-effect-free in `src/app/game.py`, so they can be tested without a server: `.venv/Scripts/python .smoke/check_rules.py`.

There are no migrations — tables are created on startup. Changing the schema means deleting `dungeon.db`.

### Configuration

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | **yes in production** | Signs the session cookie. The fallback is regenerated every process start, which logs everyone out on restart. |
| `DATABASE_URL` | no | Defaults to `sqlite:///./dungeon.db`. |
| `APP_TZ` | no | Defaults to `America/Vancouver`. Day and week boundaries follow it. |
| `CLASSIFIER_API_KEY` | no | Enables Jev. Without it, potion categories come from keyword rules alone. |

For local work, put these in a `.env` file at the repo root — it is gitignored, and `config.py` reads it as a fallback for the environment. On Render there is no file, so set them as real environment variables.

## Deploy (Render + mylost.tech)

1. Push this repo to GitHub, then in Render choose **New → Blueprint** and select the repo. `render.yaml` creates the web service, a Postgres database, and a random `SECRET_KEY`.
2. In the service's **Settings → Custom Domains**, add `mylost.tech` and create the DNS records Render shows at your domain registrar.
3. `SECRET_KEY` must be set to a real value. The fallback in `main.py` is regenerated on every process start, which logs everyone out whenever the service restarts.
4. `CLASSIFIER_API_KEY` should be set too, or the deployed build silently falls back to keyword categories while your local build does not — worth knowing before you demo it.