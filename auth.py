"""
Spotify OAuth: Authorization Code + PKCE.
"""

import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Body, HTTPException

router = APIRouter()

SPOTIFY_CLIENT_ID = os.environ["SPOTIFY_CLIENT_ID"]
SPOTIFY_CLIENT_SECRET = os.environ["SPOTIFY_CLIENT_SECRET"]  # unused by PKCE exchange; kept per CLAUDE.md env spec
SPOTIFY_REDIRECT_URI = os.environ["SPOTIFY_REDIRECT_URI"]

SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SCOPES = "user-top-read"


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for a new login attempt."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


# state -> code_verifier, for the duration of a single login attempt.
# In-memory only: lost on restart, won't work across multiple processes.
# Fine for a prototype; note if this needs to move somewhere shared later.
_pending_verifiers: dict[str, str] = {}


@router.get("/auth/spotify/login")
def spotify_login():
    """Build the Spotify authorize URL (with PKCE code_challenge)."""
    state = secrets.token_urlsafe(16)
    verifier, challenge = generate_pkce_pair()
    _pending_verifiers[state] = verifier

    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "state": state,
        "scope": SPOTIFY_SCOPES,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    return {"authorize_url": f"{SPOTIFY_AUTHORIZE_URL}?{urlencode(params)}"}


@router.get("/auth/spotify/callback")
async def spotify_callback(code: str, state: str):
    """Exchange the auth code (+ stashed verifier) for a Spotify token."""
    verifier = _pending_verifiers.pop(state, None)
    if verifier is None:
        raise HTTPException(status_code=400, detail="Unknown or expired state")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": SPOTIFY_REDIRECT_URI,
                "client_id": SPOTIFY_CLIENT_ID,
                "code_verifier": verifier,
            },
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Spotify token exchange failed")

    return response.json()


@router.post("/auth/spotify/refresh")
async def spotify_refresh(refresh_token: str = Body(..., embed=True)):
    """Exchange a refresh token for a new access token (PKCE public-client refresh — no client_secret)."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": SPOTIFY_CLIENT_ID,
            },
        )

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Spotify token refresh failed")

    data = response.json()
    # Spotify doesn't always rotate the refresh token; keep the old one if it's absent.
    data.setdefault("refresh_token", refresh_token)
    return data
