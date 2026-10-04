# Task Dungeon (SFU StormHacks)

Your to-do list is a dungeon — but in v2 the list no longer *is* the map. Every player gets the same twelve-room dungeon, generated fresh each Monday and identical for everyone. There are no locked doors and nothing to unlock. Your real-life quests are preparation: finish one and it pays potions into a pack you carry into the next fight. The dungeon is beatable with potions you earned outside the app, or on nerve alone.

- **You type a quest title. That's the whole form.** No dropdown, no reward picker. [Jev](https://ai.hackclub.com/proxy/v1/jev/systemone) reads the title in one call and answers three questions at once:
  - **Which potion** — Heal, Rage, Haste, or Aegis
  - **How often you'd genuinely repeat it** — daily, monthly, or a one-off goal
  - **How much effort it is** — a continuous score on a five-rung scale
- **The count is never asked for.** The effort score is mapped onto a bounded range in `config.py` (`POTION_MIN`–`POTION_MAX`, currently 1–4). So no quest title, however worded, can buy a reward outside that range — writing "the hardest task imaginable" gets you the same ceiling as genuinely doing it. Retune those two numbers and every existing quest re-scales, because quests store the score rather than the count.
- **If Jev is unreachable**, the keyword rules pick the potion, the quest repeats daily, and it pays the floor. Failing low is deliberate: an outage must never be worth exploiting.
- **Depth** is the score. Furthest room cleared this week, on the leaderboard, next to your party. Health carries between fights; a defeat costs you the potions you drank and sends you back to your last cleared room, fully healed. Nothing else.

Every completion is timestamped by the server in a log your party can see and flag, so nobody can fake their way up.

## Nothing is a counter

There is no XP column, no level column, no potion-count column, and no "HP" field on the user. Depth is the furthest `BattleClear` row; your pack is completions minus potion-uses; your HP is the `hp_after` on your furthest cleared room. Every one of those is a sum or a max over append-only rows.

This is not just tidiness. It means the client cannot cheat by editing a number it was handed — the server recomputes from rows and simply disagrees. It is the strongest technical claim in the project, and it is enforced by the database rather than by application checks.

The one judgement the server *does* cache is the classifier's verdict on a quest — potion, repeat window, and effort score, all frozen when the quest is created so gameplay never waits on a network call. What it deliberately does not cache is the reward: the potion *count* is recomputed from the score every time, which is why the bounds in `config.py` are the only thing that decides what a quest is worth.

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
| `CLASSIFIER_API_KEY` | no | Enables Jev. Without it, quests pay the minimum via keyword rules alone. |

For local work, put these in a `.env` file at the repo root — it is gitignored, and `config.py` reads it as a fallback for the environment. On Render there is no file, so set them as real environment variables.

## Deploy (Render + mylost.tech)

1. Push this repo to GitHub, then in Render choose **New → Blueprint** and select the repo. `render.yaml` creates the web service, a Postgres database, and a random `SECRET_KEY`.
2. In the service's **Settings → Custom Domains**, add `mylost.tech` and create the DNS records Render shows at your domain registrar.
3. `SECRET_KEY` must be set to a real value. The fallback in `main.py` is regenerated on every process start, which logs everyone out whenever the service restarts.
4. `CLASSIFIER_API_KEY` should be set too, or the deployed build silently falls back to keyword categories while your local build does not — worth knowing before you demo it.