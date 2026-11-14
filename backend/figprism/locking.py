"""One writer pipeline across HTTP, CLI and scheduled sync processes."""

from contextlib import asynccontextmanager
from functools import wraps
import asyncio
import fcntl
from .config import get_settings


@asynccontextmanager
async def pipeline_lock():
    file = (get_settings().data_dir / ".pipeline.lock").open("a")
    acquired = False
    try:
        while not acquired:
            try:
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                await asyncio.sleep(0.2)
        yield
    finally:
        if acquired:
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)
        file.close()


def serialized(function):
    @wraps(function)
    async def wrapped(*args, **kwargs):
        async with pipeline_lock():
            return await function(*args, **kwargs)

    return wrapped
