# Task Dungeon (SFU StormHacks)

Play Here: https://mylost.tech/play

Your to-do list is a dungeon — but in v2 the list no longer _is_ the map. Every player gets the same twelve-room dungeon, generated fresh each Monday and identical for everyone. There are no locked doors and nothing to unlock. Your real-life quests are preparation: finish one and it pays potions into a pack you carry into the next fight. The dungeon is beatable with potions you earned outside the app, or on nerve alone.

- **You type a quest title. That's the whole form.** No dropdown, no reward picker. [Jev](https://ai.hackclub.com/proxy/v1/jev/systemone) reads the title in one call and answers three questions at once:
  - **Which potion** — Heal, Rage, Haste, or Aegis
  - **How often you'd repeat it** — daily, monthly, or a one-off goal. This one is only a suggestion: how often *you* repeat something isn't something a title can say, so you pick the window on the quest board and the model's guess is just preselected.
  - **How much effort it is** — a continuous score on a five-rung scale
- **The count is never asked for.** The effort score is mapped onto a bounded range in `config.py` (`POTION_MIN`–`POTION_MAX`, currently 1–5). So no quest title, however worded, can buy a reward outside that range — writing "the hardest task imaginable" gets you the same ceiling as genuinely doing it. Retune those two numbers and every existing quest re-scales, because quests store the score rather than the count.
- **If Jev is unsure or unreachable**, the keyword rules pick the potion, the quest repeats daily, and it pays the floor. This is the normal path, not just the failure one — Jev returns a probability for every option, and anything under `POTION_CONFIDENCE_MIN` is overruled by the keyword table rather than accepted on a coin flip. Failing low on the *count* is deliberate: an outage must never be worth exploiting.
- **Depth** is the score. Furthest room cleared in your current run, on the leaderboard, next to your party. Health carries between fights. Death resets cleared rooms, shrines, active fights, and all potions, then returns you to the entrance hall fully healed. Quests and their completion history stay intact. Fleeing returns you to the central hallway outside the room and keeps your run progress.

Every completion is timestamped by the server in a log your party can see and flag, so nobody can fake their way up.

## Nothing is a counter

There is no XP column, no level column, no potion-count column, and no "HP" field on the user. Depth is the furthest `BattleClear` row; your pack is completions minus potion-uses; your HP is the `hp_after` on your furthest cleared room. Death removes the current run's clears and records remaining potions as lost without deleting task completions.

This is not just tidiness. It means the client cannot cheat by editing a number it was handed — the server recomputes from rows and simply disagrees. It is the strongest technical claim in the project, and it is enforced by the database rather than by application checks.

The one judgement the server _does_ cache is the classifier's verdict on a quest — potion, repeat window, and effort score, all frozen when the quest is created so gameplay never waits on a network call. What it deliberately does not cache is the reward: the potion _count_ is recomputed from the score every time, which is why the bounds in `config.py` are the only thing that decides what a quest is worth.

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

The seed never leaves the server, so a player cannot compute the fight locally and skip the turns they would have lost. Fights are held in memory keyed by `(user, room, week)` and mutated under a lock for each player's week, so concurrent requests cannot double-spend a potion or restore another room's fight after death.

Wins, defeats, and potion spends are persisted as they happen — not when a client says the fight ended.

## Tests and balance tooling

```bash
./run_tests.sh                                 # API suites and scene checks (Node.js)
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

### Configuration

| Variable             | Required              | Purpose                                                                                                        |
| -------------------- | --------------------- | -------------------------------------------------------------------------------------------------------------- |
| `SECRET_KEY`         | **yes in production** | Signs the session cookie. The fallback is regenerated every process start, which logs everyone out on restart. |
| `DATABASE_URL`       | no                    | Defaults to `sqlite:///./dungeon.db`.                                                                          |
| `APP_TZ`             | no                    | Defaults to `America/Vancouver`. Day and week boundaries follow it.                                            |
| `CLASSIFIER_API_KEY` | no                    | Enables Jev. Without it, quests pay the minimum via keyword rules alone.                                       |
| `BOSS_HP_CAP`        | no                    | Ceiling on the boss's HP. A number clamps it; `none` removes the ceiling and lets the depth curve decide. Defaults to `138`. |

For local work, put these in a `.env` file at the repo root — it is gitignored, and `config.py` reads it as a fallback for the environment. On Render there is no file, so set them as real environment variables.

### Every balance number lives in one file

`src/app/config.py` is the only place a tuning number is written down. It is grouped into `--- SECTION ---` banners with an index in the module docstring, so Ctrl-F on a name (or reading the index) gets you to the knob. Nothing is duplicated in the backend or the client: the server publishes the public half at `/api/config` and the client renders with those values.

The boss's HP has two knobs, and they are not interchangeable:

| Want | Change |
| ---- | ------ |
| Harder boss, longer fight | `BOSS_HP_CAP` (or `ROOM_ARCHETYPES["boss"]["hp_mult"]` **only if the cap is not binding**) |
| Harder boss, hits harder | `ROOM_ARCHETYPES["boss"]["atk_mult"]`, `BOSS["special_mult"]`, `BOSS["phase_mult"]` |

`BOSS_HP_CAP` is a *ceiling* on the depth curve, not a replacement for it. The curve currently produces ~194 HP for the boss, so `hp_mult` changes have no visible effect while the cap is 138 — that is the single most confusing thing about tuning this fight. Unbounded is a supported mode (`BOSS_HP_CAP=none`), and `/api/config` publishes the current value as `boss_hp_cap` (`null` when unbounded) so the client can tell the difference.

After changing anything in the `PLAYER`, `POTION`, `ENEMY`, `ROOM_ARCHETYPES`, `COMBAT` or `BOSS` sections, run `PYTHONPATH=. .venv/bin/python -m tools.balance` — it Monte-Carlos the floor and fails if the clear rates leave the design target.

### Run a single worker

In-progress fights live in process memory, so the app must run as **one** worker. Multiple workers would each hold a different copy of a fight, and a player's turn would land on a worker that has never heard of it — the symptom is a "No fight in progress there" error on a fight the player is plainly in the middle of.

## Deploy (Render + mylost.tech)

1. Push this repo to GitHub, then in Render choose **New → Blueprint** and select the repo. `render.yaml` creates the web service, a Postgres database, and a random `SECRET_KEY`.
2. In the service's **Settings → Custom Domains**, add `mylost.tech` and create the DNS records Render shows at your domain registrar.
3. `SECRET_KEY` must be set to a real value. The fallback in `main.py` is regenerated on every process start, which logs everyone out whenever the service restarts.
4. `CLASSIFIER_API_KEY` should be set too, or the deployed build silently falls back to keyword categories while your local build does not — worth knowing before you demo it.
