# Task Dungeon (SFU StormHacks)

Your to-do list is a dungeon. Every quest you add (daily, monthly, or long-term goal) becomes a room with a monster inside, and the door only opens once you've done the task in real life. Clear rooms for XP and loot, skip your dailies and lose HP, and compete with friends on a weekly leaderboard. Every completion is timestamped by the server in a log your party can see and flag, so nobody can fake their way up.

- **Daily** quest → mob (10 XP), resets every day
- **Monthly** quest → mini-boss (50 XP), resets every month
- **Goal** → boss (200 XP), once

## Run locally

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m uvicorn src.app.main:app --reload
```

Open http://127.0.0.1:8000, click **New hero** to register, add quests on the Quest Board, then press **I did it** and head to the Dungeon.

## Stack

FastAPI + SQLModel (SQLite locally, Postgres in production), Jinja pages, and a [Phaser 3](https://phaser.io) game loaded from a CDN (no build step). Placeholder pixel art is drawn in code in `src/app/static/game/main.js` (`makeTextures`).

## Deploy (Render + .tech domain)

1. Push this repo to GitHub, then in Render choose **New → Blueprint** and select the repo. `render.yaml` creates the web service, a Postgres database, and a random `SECRET_KEY`.
2. In the service's **Settings → Custom Domains**, add your `.tech` domain and create the DNS records Render shows at your domain registrar.
