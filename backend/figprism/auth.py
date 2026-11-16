import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from .config import get_settings
from .db import connect

router = APIRouter(prefix="/api/auth", tags=["auth"])
hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(24))


class Credentials(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[\w.@-]+$")
    password: str = Field(min_length=10, max_length=128)


class Registration(Credentials):
    invite_code: str


def current_user(request: Request):
    token = request.cookies.get("figprism_session")
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            get_settings().secret_key.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "jti"]},
        )
        with connect() as db:
            row = db.execute(
                "SELECT u.id,u.username,u.role FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.jti=? AND u.id=? AND u.is_active=1 AND s.expires_at>?",
                (payload["jti"], payload["sub"], int(time.time())),
            ).fetchone()
        return dict(row) if row else None
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


def require_user(user=Depends(current_user)):
    if not user:
        raise HTTPException(401, "请先登录")
    return user


def require_admin(user=Depends(require_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


def create_user(username, password, role="user"):
    Credentials(username=username, password=password)
    with connect() as db:
        cur = db.execute(
            "INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
            (username, hasher.hash(password), role),
        )
        return cur.lastrowid


def start_session(response, user):
    settings = get_settings()
    jti = secrets.token_urlsafe(32)
    exp = int(time.time()) + 7 * 86400
    with connect() as db:
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        db.execute("INSERT INTO sessions VALUES(?,?,?)", (jti, user["id"], exp))
    token = jwt.encode(
        {"sub": str(user["id"]), "exp": exp, "jti": jti},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    response.set_cookie(
        "figprism_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=7 * 86400,
        path="/",
    )


@router.get("/me")
def me(user=Depends(current_user)):
    return {"user": user}


@router.post("/login")
def login(data: Credentials, response: Response):
    with connect() as db:
        user = db.execute(
            "SELECT * FROM users WHERE username=? AND is_active=1", (data.username,)
        ).fetchone()
    try:
        hasher.verify(user["password_hash"] if user else DUMMY_HASH, data.password)
    except VerificationError:
        raise HTTPException(401, "用户名或密码错误")
    if not user:
        raise HTTPException(401, "用户名或密码错误")
    start_session(response, user)
    return {"user": {k: user[k] for k in ("id", "username", "role")}}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("figprism_session")
    if token:
        try:
            payload = jwt.decode(
                token,
                get_settings().secret_key.get_secret_value(),
                algorithms=["HS256"],
            )
            with connect() as db:
                db.execute("DELETE FROM sessions WHERE jti=?", (payload["jti"],))
        except (jwt.PyJWTError, KeyError):
            pass
    response.delete_cookie("figprism_session", path="/")
    return {"ok": True}


@router.post("/register")
def register(data: Registration, response: Response):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        invite = db.execute(
            "SELECT * FROM invite_codes WHERE code=? AND used_count < max_uses AND expires_at>datetime('now')",
            (data.invite_code,),
        ).fetchone()
        if not invite:
            raise HTTPException(403, "邀请链接无效、已过期或使用次数已用完")
        if db.execute(
            "SELECT id FROM users WHERE username=?", (data.username,)
        ).fetchone():
            raise HTTPException(409, "用户名已存在")
        uid = db.execute(
            "INSERT INTO users(username,password_hash,role) VALUES(?,?,'user')",
            (data.username, hasher.hash(data.password)),
        ).lastrowid
        db.execute(
            "UPDATE invite_codes SET used_by=?,used_count=used_count+1 WHERE code=?",
            (uid, data.invite_code)
        )
    start_session(response, {"id": uid})
    return {"user": {"id": uid, "username": data.username, "role": "user"}}
