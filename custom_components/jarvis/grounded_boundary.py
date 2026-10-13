"""Non-promotable authority boundary for grounded conversation reasoning.

Every model turn with history, retrieval, entity metadata or external tool
descriptions is read-only. Authority lives in task-local application state,
never in a message role, summary, provider response or persisted transcript.
Fresh deterministic local commands execute outside this scope.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import Awaitable, Callable, ParamSpec

_P = ParamSpec("_P")
DENIAL = (
    "Action refused: grounded conversation reasoning is read-only. "
    "Send a fresh explicit device command supported by the local command "
    "engine; conversation history and search results cannot authorize actions."
)


@dataclass
class _Scope:
    denied: bool = False


_scope: ContextVar[_Scope | None] = ContextVar("jarvis_grounded_scope", default=None)


def is_grounded() -> bool:
    return _scope.get() is not None


def deny_action() -> str:
    scope = _scope.get()
    if scope is not None:
        scope.denied = True
    return DENIAL


def read_only_reasoning(
    fn: Callable[_P, Awaitable[str]],
) -> Callable[_P, Awaitable[str]]:
    """Scope the complete loop, including retries, nested tools and tasks."""
    @wraps(fn)
    async def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> str:
        parent = _scope.get()
        scope = parent if parent is not None else _Scope()
        token = _scope.set(scope)
        try:
            result = await fn(*args, **kwargs)
            return DENIAL if scope.denied else result
        finally:
            _scope.reset(token)

    return wrapped
