"""
Wraps Spotify's GET /me/top/tracks.

Deliberately does NOT touch "On Repeat"/algorithmic playlist endpoints or
audio-features/audio-analysis endpoints — both are gated behind extended
quota approval Spotify isn't granting to new apps. Top tracks (real
listening history) is what we build the vibe from.
"""

from typing import Optional

import httpx
from fastapi import HTTPException

SPOTIFY_TOP_TRACKS_URL = "https://api.spotify.com/v1/me/top/tracks"

VALID_TIME_RANGES = {"short_term", "medium_term", "long_term"}
DEFAULT_TIME_RANGE = "short_term"  # ~4 weeks, per CLAUDE.md


async def get_top_tracks(
    access_token: str, time_range: str = DEFAULT_TIME_RANGE, limit: int = 20
) -> list[dict]:
    """Return the user's top tracks as a list of {name, artists, albumArt} dicts."""
    if time_range not in VALID_TIME_RANGES:
        raise ValueError(f"Invalid time_range: {time_range}")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            SPOTIFY_TOP_TRACKS_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"time_range": time_range, "limit": limit},
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502, detail="Failed to fetch top tracks from Spotify"
        )

    items = response.json()["items"]
    return [
        {
            "name": track["name"],
            "artists": [artist["name"] for artist in track["artists"]],
            "albumArt": _smallest_image(track["album"]["images"]),
        }
        for track in items
    ]


def _smallest_image(images: list[dict]) -> Optional[str]:
    """Spotify returns album images largest-first; the smallest is enough for a list thumbnail."""
    return images[-1]["url"] if images else None
