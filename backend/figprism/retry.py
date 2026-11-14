"""Bounded retries for idempotent transfers; error summaries exclude credentials."""

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import httpx
from .config import get_settings

TRANSIENT = {408, 425, 429, 500, 502, 503, 504}


def retry_delay(exc, attempt):
    fallback = min(2**attempt, 16)
    if not isinstance(exc, httpx.HTTPStatusError):
        return fallback
    value = exc.response.headers.get("Retry-After", "")
    try:
        return max(fallback, float(value))
    except ValueError:
        try:
            return max(
                fallback,
                (
                    parsedate_to_datetime(value) - datetime.now(timezone.utc)
                ).total_seconds(),
            )
        except (ValueError, TypeError, OverflowError):
            return fallback


async def retry(operation):
    for attempt in range(get_settings().pipeline.retry_attempts):
        try:
            return await operation()
        except (httpx.TransportError, httpx.HTTPStatusError, TimeoutError) as exc:
            if (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code not in TRANSIENT
            ):
                raise
            if attempt + 1 >= get_settings().pipeline.retry_attempts:
                raise
            delay = retry_delay(exc, attempt)
            # Do not retry earlier than a long provider cooldown; leave it to a later job.
            if delay > 120:
                raise
            await asyncio.sleep(delay)


def root_error(exc):
    while isinstance(exc, BaseExceptionGroup):
        exc = exc.exceptions[0]
    return exc


def error_message(exc):
    exc = root_error(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        return f"远端服务 HTTP {exc.response.status_code}，已保留成功进度，可重试"
    if isinstance(exc, (httpx.TransportError, TimeoutError)):
        return "远端连接超时或中断，已保留成功进度，可重试"
    if isinstance(exc, ValueError):
        return str(exc)[:300]
    return "处理失败，已保留成功进度，可重新提交任务"
