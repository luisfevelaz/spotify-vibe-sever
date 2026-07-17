"""
Vibe result cache, keyed by (user_id, time_range).

Starting in-memory per CLAUDE.md — not yet decided whether this needs to
move to Redis for anything closer to production. In-memory means cache is
lost on server restart and won't work across multiple server processes.
"""

from typing import Optional

_cache: dict[tuple[str, str], dict] = {}


def get(user_id: str, time_range: str) -> Optional[dict]:
    return _cache.get((user_id, time_range))


def set(user_id: str, time_range: str, vibe_result: dict) -> None:
    _cache[(user_id, time_range)] = vibe_result
