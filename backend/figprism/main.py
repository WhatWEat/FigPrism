from collections import defaultdict, deque
from contextlib import asynccontextmanager
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .auth import router as auth_router
from .config import get_settings
from .db import init_db, connect
from .domains import all_domains


@asynccontextmanager
async def lifespan(app):
    init_db(recover_jobs=True)
    try:
        yield
    finally:
        from .api import stop_tasks

        await stop_tasks()


app = FastAPI(title="FigPrism API", lifespan=lifespan)
app.include_router(auth_router)
limits = defaultdict(deque)


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != get_settings().public_origin.rstrip("/"):
            return JSONResponse(
                {"detail": "来源校验失败"},
                status_code=403,
                headers={"Cache-Control": "private, no-store"},
            )
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "不允许跨站请求"}, status_code=403)
    if path in ("/api/auth/login", "/api/auth/register") and request.method == "POST":
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        q = limits[key]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= 10:
            return JSONResponse(
                {"detail": "尝试过于频繁，请稍后再试"},
                status_code=429,
                headers={"Retry-After": "60", "Cache-Control": "private, no-store"},
            )
        q.append(now)
        if len(limits) > 10000:
            for old in list(limits):
                if not limits[old] or limits[old][-1] < now - 60:
                    del limits[old]
    response = await call_next(request)
    if path.startswith(
        (
            "/api/auth",
            "/api/me",
            "/api/collections",
            "/api/ingest",
            "/api/admin",
            "/api/jobs",
        )
    ):
        response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.get("/api/health")
def health():
    with connect() as db:
        db.execute("SELECT 1")
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/domains")
def domains():
    return all_domains()


from .api import router as api_router

app.include_router(api_router)


from .ingest import JobQueueFull


@app.exception_handler(JobQueueFull)
async def queue_full(request, exc):
    return JSONResponse(
        {"detail": str(exc)},
        status_code=429,
        headers={"Cache-Control": "private, no-store", "Retry-After": "15"},
    )
