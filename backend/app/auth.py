"""Password hashing and JWT sessions."""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException

from .db import Membership, SessionLocal, User

SECRET = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
ROLES = ("manager", "developer", "newcomer")


def hash_password(pw, salt=None):
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


def check_password(pw, stored):
    salt = stored.split("$")[0]
    return hmac.compare_digest(hash_password(pw, salt), stored)


def make_token(user):
    exp = datetime.now(timezone.utc) + timedelta(days=7)
    return jwt.encode({"sub": str(user.id), "exp": exp}, SECRET, algorithm="HS256")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(authorization: str = Header(default=""), db=Depends(get_db)):
    try:
        payload = jwt.decode(authorization.removeprefix("Bearer ").strip(), SECRET, algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except Exception:
        user = None
    if not user:
        raise HTTPException(401, "Sign in to continue.")
    return user


def role_in(db, user, project_id, allowed=ROLES):
    """Project membership check. Returns the caller's role or raises 403/404."""
    m = db.query(Membership).filter_by(user_id=user.id, project_id=project_id).first()
    if not m:
        raise HTTPException(404, "Project not found, or you are not a member of it.")
    if m.role not in allowed:
        raise HTTPException(403, f"Your role ({m.role}) cannot do this.")
    return m.role
