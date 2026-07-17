# spotify-vibe-server

FastAPI backend for **spotify-vibe**: pulls a user's Spotify top tracks and
uses an LLM (Groq / Llama 3.3) to generate a short, evocative description of
their music "vibe" (e.g. "Rainy Day Indie", "Chaotic Gym Energy").

Companion frontend: [`spotify-vibe-app`](../spotify-vibe-app) (Expo / React Native).

## Stack

- Python, FastAPI, uvicorn
- `httpx` for outbound HTTP (Spotify API)
- Groq (OpenAI-compatible SDK) for the LLM call, not OpenAI — keeps a
  shared API key on a free tier with bounded per-user cost
- In-memory cache + rate limiter (prototype-stage; see [Notes](#notes))

## Setup

```bash
source ~/ai-eng-env/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in the values below
```

### Environment variables (`.env`)

| Variable | Description |
| --- | --- |
| `SPOTIFY_CLIENT_ID` | From the Spotify Developer dashboard |
| `SPOTIFY_CLIENT_SECRET` | Loaded but unused by the PKCE exchange itself; kept per the app's env spec |
| `SPOTIFY_REDIRECT_URI` | Must match the redirect URI registered with Spotify (e.g. `spotify-vibe://callback`) |
| `GROQ_API_KEY` | Groq API key for the vibe-generation call |

`.env` is gitignored; `.env.example` is the checked-in template. Secrets
live per-project in `.env` — never as shell-level exports.

## Running

```bash
uvicorn main:app --reload --port 8000
```

## Endpoints

- `GET /auth/spotify/login` — returns the Spotify authorize URL, with a PKCE
  code challenge embedded
- `GET /auth/spotify/callback?code=...&state=...` — exchanges the auth code
  for a Spotify access token
- `GET /vibe?time_range=short_term` — resolves the caller's Spotify user via
  the `Authorization: Bearer <token>` header, then returns
  `{ "vibe": "...", "tracks": [...] }` (served from cache when available)

## How a `/vibe` request flows

```
App: GET /vibe?time_range=short_term
     Authorization: Bearer <spotify_access_token>
        |
        v
main.py: get_current_user_id()
   -> calls Spotify GET /me to resolve (user_id, access_token)
        |
        v
main.py: GET /vibe handler
        |
        +--> cache.get(user_id, time_range)
        |       hit?  -> return cached result (done)
        |       miss
        |       v
        +--> rate_limit.is_allowed(user_id)
        |       not allowed? -> 429 error (done)
        |       allowed
        |       v
        +--> spotify_client.get_top_tracks(access_token, time_range)
        |       (hits Spotify's GET /me/top/tracks)
        |       v
        +--> rate_limit.record_request(user_id)
        |       v
        +--> vibe.get_vibe(tracks)
        |       (build_prompt -> call_groq -> validate,
        |        retry once, fallback to "Eclectic Mix")
        |       v
        +--> cache.set(user_id, time_range, result)
        |       v
        +--> return { vibe, tracks } to the app
```

Cache is checked *before* rate limiting, so a cache hit never counts against
the hourly rate limit — the limit exists to protect Groq quota, not to gate
reads of already-computed results.

## Project layout

```
spotify-vibe-server/
├── main.py            # app entrypoint, route registration, GET /vibe
├── auth.py             # PKCE helpers, /auth/spotify/login, /auth/spotify/callback
├── spotify_client.py    # wraps GET /me/top/tracks
├── vibe.py               # prompt building, Groq call, structured output + validation
├── cache.py                # per-(user_id, time_range) result cache
├── rate_limit.py             # per-user rate limiting for /vibe
├── requirements.txt
├── .env.example
└── .env                        # gitignored
```

## Deliberate constraints

- **No "On Repeat" / algorithmic playlist endpoints** — locked behind
  extended-quota approval Spotify isn't granting new apps. Uses
  `GET /me/top/tracks` (real listening history) instead.
- **No audio-features/audio-analysis endpoints** (danceability, energy,
  valence, etc.) — same quota restriction. The vibe is built purely from
  track and artist names.
- **OAuth is Authorization Code + PKCE**, not implicit grant, and no client
  secret is embedded in the mobile app.

## Notes

- Cache and rate limiter are both in-memory: state is lost on restart and
  isn't shared across multiple server processes. Fine for a prototype; flag
  if this needs to move to something like Redis for anything closer to
  production.
- `vibe.py`'s prompt wording is a placeholder pending a standalone
  prompt-iteration pass against real top-tracks data (word count
  compliance, tone quality, behavior on sparse listening history).
