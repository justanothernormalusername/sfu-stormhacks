# Task Dungeon (SFU StormHacks)

Your to-do list is a dungeon — but in v2 the list no longer *is* the map. Every player gets the same twelve-room dungeon, generated fresh each Monday and identical for everyone. There are no locked doors and nothing to unlock. Your real-life quests are preparation: finish one and it pays potions into a pack you carry into the next fight. The dungeon is beatable with potions you earned outside the app, or on nerve alone.

- **Daily** quest → 1 potion, resets every day
- **Monthly** quest → 2 potions, resets every month
- **Goal** → 4 potions, once ever
- **Potions** → four kinds (Heal, Rage, Haste, Aegis). Which one a quest pays is decided by a small classifier when you add it — keywords as a deterministic fallback, an optional model call to refine the guess. It can only ever narrow the choice to a real potion kind; it never decides quantities.
- **Depth** is the score. Furthest room cleared this week, on the leaderboard, next to your party. Health carries between fights; a defeat costs you the potions you drank and sends you back to your last cleared room, fully healed. Nothing else.

Every completion is timestamped by the server in a log your party can see and flag, so nobody can fake their way up.

## Nothing is a counter

There is no XP column, no level column, no potion-count column, and no "HP" field on the user. Depth is the furthest `BattleClear` row; your pack is completions minus potion-uses; your HP is the `hp_after` on your furthest cleared room. Every one of those is a sum or a max over append-only rows.

This is not just tidiness. It means the client cannot cheat by editing a number it was handed — the server recomputes from rows and simply disagrees. It is the strongest technical claim in the project, and it is enforced by the database rather than by application checks.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
SECRET_KEY=dev .venv/bin/python -m uvicorn src.app.main:app --reload
```

Run it from the repo root so `src.app` imports resolve. Open http://127.0.0.1:8000, click **New hero** to register, add quests on the Quest Board, press **I did it**, then head to the Dungeon.

Every balance number — enemy HP and damage, potion effects, crit chance, room count, tier splits — lives in `src/app/config.py` and nowhere else. The server publishes them at `/api/config` and the client renders with those values, so changing one number there moves the whole game.

## Combat is server-authoritative

The client sends an action name and renders what comes back. It never computes damage, never decides whether it won, and cannot claim HP it did not have — there is no `hp` field in the request body to claim with.

| Endpoint | What it does |
|---|---|
| `POST /api/rooms/{i}/enter` | Opens a fight. Enemy stats, your HP, and the fight seed are all decided server-side. |
| `POST /api/rooms/{i}/act` | One player action plus the enemy turn, resolved by `game.fight_step`. |

The seed never leaves the server, so a player cannot compute the fight locally and skip the turns they would have lost. Fights are held in memory keyed by `(user, room, week)` and mutated under a per-fight lock, so two concurrent requests cannot double-spend a potion or skip a turn.

Wins, defeats, and potion spends are written as append-only rows as they happen — not when a client says the fight ended.

## Tests and balance tooling

```bash
./run_tests.sh                                    # the four suites that gate a change
PYTHONPATH=. .venv/bin/python tests/floor_run.py # play a whole floor through the API
PYTHONPATH=. .venv/bin/python -m tools.balance   # Monte-Carlo clear rates by potion budget
```

`tools/balance.py` plays the real floor with the real rules and checks clear rates against design targets, exiting non-zero if a band is missed. **Run it after touching anything in the `PLAYER_`, `POTION_`, `ENEMY_`, or `ROOM_ARCHETYPES` blocks in `config.py`.** It takes about two minutes.

Two things worth knowing before you retune, both learned the hard way:

- **Difficulty compounds multiplicatively.** Raising the depth curve, buffing every archetype, *and* cutting `ROOM_CLEAR_HEAL` in one pass made the floor unwinnable at every potion budget. Change one lever, measure, repeat.
- **Tune the boss against the HP a player actually arrives with**, not a full bar. `tests/where_do_they_die.py` reports that number; tuning against 125 HP produces a boss that is unwinnable in practice.

`tools/tune_boss.py` sweeps the boss HP cap and prints measured win rates, so the value is chosen from data.

## Stack

FastAPI + SQLModel (SQLite locally, Postgres in production), Jinja pages, and a [Phaser 3](https://phaser.io) game loaded from a CDN (no build step). Placeholder pixel art is drawn in code in `src/app/static/game/main.js` (`makeTextures`). Game rules are pure and side-effect-free in `src/app/game.py`, so they can be tested without a server.

There are no migrations — tables are created on startup. Changing the schema means deleting `dungeon.db`.

Note: in-progress fights live in process memory, so **run a single worker**. Multiple workers would each hold a different copy of a fight, and a player's turn would land on a worker that has never heard of their fight.

## Deploy (Render + mylost.tech)

1. Push this repo to GitHub, then in Render choose **New → Blueprint** and select the repo. `render.yaml` creates the web service, a Postgres database, and a random `SECRET_KEY`.
2. In the service's **Settings → Custom Domains**, add `mylost.tech` and create the DNS records Render shows at your domain registrar.
3. `SECRET_KEY` must be set to a real value. The fallback in `main.py` is regenerated on every process start, which logs everyone out whenever the service restarts.