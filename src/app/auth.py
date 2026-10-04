import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from .db import get_session
from .models import User

ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS)
    return hmac.compare_digest(check.hex(), digest)


def current_user_optional(request: Request, session: Session = Depends(get_session)) -> User | None:
    user_id = request.session.get("user_id")
    return session.get(User, user_id) if user_id else None


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    return user
