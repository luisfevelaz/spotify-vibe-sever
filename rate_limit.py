"""
Per-user rate limiting for /vibe, to protect the shared Groq quota from
abuse or retry bugs.

In-memory, same pattern/caveats as cache.py: lost on restart, won't work
across multiple server processes.
"""

import time

RATE_LIMIT_SECONDS = 60 * 60  # 1 request/hour

_last_request: dict[str, float] = {}


def is_allowed(user_id: str) -> bool:
    """Check whether user_id may make a /vibe request right now."""
    last = _last_request.get(user_id)
    if last is None:
        return True
    return (time.time() - last) >= RATE_LIMIT_SECONDS


def record_request(user_id: str) -> None:
    _last_request[user_id] = time.time()
