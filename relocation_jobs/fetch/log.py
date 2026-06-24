from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
from typing import Any

LOGGER_NAME = "relocation_jobs.fetch"
_configured = False

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

_fetch_log_context: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "fetch_log_context",
    default={},
)


def _body_preview_limit() -> int:
    raw = (os.environ.get("FETCH_LOG_BODY_LIMIT") or "2000").strip()
    try:
        return max(200, min(int(raw), 20000))
    except (TypeError, ValueError):
        return 2000


def configure_fetch_logging() -> None:
    global _configured
    if _configured:
        return
    level_name = (os.environ.get("FETCH_LOG_LEVEL") or "INFO").strip().upper()
    level = _LEVELS.get(level_name, logging.INFO)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [FETCH] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
    logger.propagate = False
    _configured = True


def bind_fetch_log_context(**fields) -> None:
    current = dict(get_fetch_log_context())
    current.update({key: value for key, value in fields.items() if value is not None})
    _fetch_log_context.set(current)


def get_fetch_log_context() -> dict:
    return dict(_fetch_log_context.get())


def clear_fetch_log_context() -> None:
    _fetch_log_context.set({})


def _context_line(**fields) -> str:
    parts: list[str] = []
    if fields.get("run_id") is not None:
        parts.append(f"run={fields['run_id']}")
    if fields.get("scope"):
        parts.append(f"scope={fields['scope']}")
    if fields.get("country"):
        parts.append(f"country={fields['country']}")
    if fields.get("company"):
        name = str(fields["company"])
        parts.append(f'company="{name}"' if " " in name else f"company={name}")
    if fields.get("user_id") is not None:
        parts.append(f"user={fields['user_id']}")
    if fields.get("ats_type"):
        parts.append(f"ats={fields['ats_type']}")
    if fields.get("concurrency") is not None:
        parts.append(f"workers={fields['concurrency']}")
    if fields.get("attempt_id") is not None:
        parts.append(f"attempt={fields['attempt_id']}")
    step = fields.get("index")
    total = fields.get("total")
    if step is not None and total is not None:
        parts.append(f"progress={step}/{total}")
    elif total is not None:
        parts.append(f"total={total}")
    if fields.get("exit_code") is not None:
        parts.append(f"exit={fields['exit_code']}")
    if fields.get("new_jobs") is not None:
        parts.append(f"new_jobs={fields['new_jobs']}")
    return " ".join(parts)


def _preview_body(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, (dict, list)):
        try:
            text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            text = str(body)
    elif isinstance(body, (bytes, bytearray)):
        try:
            text = body.decode("utf-8", errors="replace")
        except Exception:
            return f"<bytes len={len(body)}>"
    else:
        text = str(body)
    collapsed = " ".join(text.split())
    limit = _body_preview_limit()
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[:limit]}…({len(collapsed)} chars)"


def log_event(message: str, *, level: int = logging.INFO, **context) -> None:
    configure_fetch_logging()
    merged = {**get_fetch_log_context(), **context}
    ctx = _context_line(**merged)
    line = f"{ctx} | {message}" if ctx else message
    logging.getLogger(LOGGER_NAME).log(level, line)


def log_http_exchange(
    *,
    kind: str,
    method: str,
    url: str,
    job_url: str | None = None,
    job_title: str | None = None,
    request_body: Any = None,
    response_status: int | None = None,
    response_body: Any = None,
    response_bytes: int | None = None,
    error: str | None = None,
    level: int = logging.INFO,
    **context,
) -> None:
    label = {
        "board": "job board list",
        "job": "job posting",
        "http": "http",
    }.get(kind, kind)
    pieces = [f"HTTP {method.upper()} {label}"]
    if job_title:
        title = str(job_title)
        pieces.append(f'position="{title}"' if " " in title else f"position={title}")
    if job_url:
        pieces.append(f"position_url={job_url}")
    pieces.append(f"request_url={url}")
    if request_body is not None and str(request_body).strip():
        pieces.append(f"request_body={_preview_body(request_body)}")
    if error:
        pieces.append(f"error={error}")
    elif response_status is not None:
        pieces.append(f"status={response_status}")
        if response_bytes is not None:
            pieces.append(f"response_bytes={response_bytes}")
        if response_body is not None and str(response_body).strip():
            pieces.append(f"response_body={_preview_body(response_body)}")
    merged = {**get_fetch_log_context(), **context}
    log_event(" — ".join(pieces), level=level, **merged)
