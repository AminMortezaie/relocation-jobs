from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")


def any_of(ctx: T, rules: Iterable[Callable[[T], bool]]) -> bool:
    return any(rule(ctx) for rule in rules)


def all_of(ctx: T, rules: Iterable[Callable[[T], bool]]) -> bool:
    return all(rule(ctx) for rule in rules)
