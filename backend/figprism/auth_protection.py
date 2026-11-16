"""Server-side challenge verification and persistent authentication throttles."""
import hashlib
import math
import time
import sqlite3
import httpx
from fastapi import HTTPException
from .config import get_settings
from .db import connect


def rate_limit(scope, identity, maximum=10, period=60):
    now = time.time()
    key = hashlib.sha256(f"{scope}:{identity}".encode()).hexdigest()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM auth_rate_limits WHERE created_at<=?", (now-period,))
        row = db.execute("SELECT COUNT(*) AS n,MIN(created_at) AS first FROM auth_rate_limits WHERE key=?", (key,)).fetchone()
        if row['n'] >= maximum:
            return max(1, math.ceil(row['first'] + period - now))
        db.execute("INSERT INTO auth_rate_limits(key,created_at) VALUES(?,?)", (key, now))
    return 0


def verify_challenge(token, action):
    settings = get_settings().turnstile
    if not settings.enabled:
        return
    if not settings.site_key or not settings.secret_key.get_secret_value() or not settings.allowed_hostnames:
        raise HTTPException(503, "人机验证尚未配置完成，请联系管理员")
    if not token:
        raise HTTPException(403, "请先完成人机验证")
    digest = hashlib.sha256(token.encode()).hexdigest()
    with connect() as db:
        db.execute("DELETE FROM auth_challenge_uses WHERE expires_at<=?", (time.time(),))
        if db.execute("SELECT 1 FROM auth_challenge_uses WHERE digest=?", (digest,)).fetchone():
            raise HTTPException(403, "验证已使用，请重新验证")
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            response = client.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", json={
                "secret": settings.secret_key.get_secret_value(), "response": token,
            })
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "人机验证服务暂时不可用，请稍后重试")
    if (not isinstance(result, dict) or result.get("success") is not True
        or result.get("hostname") not in settings.allowed_hostnames
        or result.get("action") != action):
        raise HTTPException(403, "人机验证未通过或已过期，请重新验证")
    # Siteverify replay detection is eventually consistent; enforce it locally too.
    try:
        with connect() as db:
            db.execute("INSERT INTO auth_challenge_uses(digest,expires_at) VALUES(?,?)", (digest,time.time()+600))
    except sqlite3.IntegrityError:
        raise HTTPException(403, "验证已使用，请重新验证")


def protect_auth(data, action):
    verify_challenge(data.turnstile_token, action)
    wait = rate_limit("account", data.username.casefold())
    if wait:
        raise HTTPException(429, "该账号尝试过于频繁，请稍后重试", headers={"Retry-After":str(wait)})
