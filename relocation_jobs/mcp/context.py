from __future__ import annotations

from contextvars import ContextVar

_current_user_id: ContextVar[int | None] = ContextVar("mcp_current_user_id", default=None)


def set_current_user_id(user_id: int | None):
    return _current_user_id.set(user_id)


def reset_current_user_id(token) -> None:
    _current_user_id.reset(token)


def get_current_user_id() -> int | None:
    return _current_user_id.get()
