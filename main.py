"""App entrypoint and route registration."""

from dotenv import load_dotenv

load_dotenv()  # before importing anything that reads os.environ at import time

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException

import auth
import cache
import rate_limit
import spotify_client
import vibe

app = FastAPI()
app.include_router(auth.router)


async def get_current_user_id(authorization: str = Header(...)) -> tuple[str, str]:
    """Resolve the Bearer token to a Spotify user id. Returns (user_id, access_token)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    access_token = authorization.removeprefix("Bearer ")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired Spotify token")

    return response.json()["id"], access_token


@app.get("/vibe")
async def get_vibe_endpoint(
    time_range: str = "short_term",
    user=Depends(get_current_user_id),
):
    user_id, access_token = user

    cached = cache.get(user_id, time_range)
    if cached is not None:
        return cached

    if not rate_limit.is_allowed(user_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded, try again later")

    tracks = await spotify_client.get_top_tracks(access_token, time_range)
    rate_limit.record_request(user_id)

    result = {**vibe.get_vibe(tracks), "tracks": tracks}
    cache.set(user_id, time_range, result)
    return result
