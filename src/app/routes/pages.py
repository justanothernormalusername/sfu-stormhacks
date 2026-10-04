from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from ..auth import current_user_optional, hash_password, verify_password
from ..db import get_session
from ..models import User

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


def page(name: str, request: Request, user: User | None, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, name, {"user": user, **ctx})


def login_required(user: User | None):
    return None if user else RedirectResponse("/login", status_code=303)


@router.get("/")
def home(user: User | None = Depends(current_user_optional)):
    return RedirectResponse("/play" if user else "/login", status_code=303)


@router.get("/login")
def login_page(request: Request, user: User | None = Depends(current_user_optional)):
    return page("login.html", request, user, error=None)


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...),
          action: str = Form("login"), session: Session = Depends(get_session)):
    username = username.strip()
    existing = session.exec(select(User).where(User.username == username)).first()
    if action == "register":
        if not username or len(password) < 4:
            return page("login.html", request, None, error="Pick a username and a password of 4+ characters.")
        if existing:
            return page("login.html", request, None, error="That username is taken.")
        existing = User(username=username[:32], password_hash=hash_password(password))
        session.add(existing)
        session.commit()
        session.refresh(existing)
    elif existing is None or not verify_password(password, existing.password_hash):
        return page("login.html", request, None, error="Wrong username or password.")
    request.session["user_id"] = existing.id
    return RedirectResponse("/tasks" if action == "register" else "/play", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/tasks")
def tasks_page(request: Request, user: User | None = Depends(current_user_optional)):
    return login_required(user) or page("tasks.html", request, user)


@router.get("/friends")
def friends_page(request: Request, user: User | None = Depends(current_user_optional)):
    return login_required(user) or page("friends.html", request, user)


@router.get("/log")
def log_page(request: Request, username: str | None = None,
             user: User | None = Depends(current_user_optional)):
    return login_required(user) or page("log.html", request, user, target=username or (user and user.username))


@router.get("/play")
def play_page(request: Request, user: User | None = Depends(current_user_optional)):
    return login_required(user) or page("play.html", request, user)
