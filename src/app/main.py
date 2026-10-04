import os
import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .db import init_db
from .routes import api, pages

app = FastAPI(title="Task Dungeon")
# Set SECRET_KEY in production, otherwise everyone is logged out on each restart.
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
                   max_age=60 * 60 * 24 * 30)
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")
app.include_router(api.router)
app.include_router(pages.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
