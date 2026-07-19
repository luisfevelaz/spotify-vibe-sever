"""
Prompt building + Groq call + structured output + validation for the vibe.

Provider-agnostic by design (CLAUDE.md): groq.Groq() here is the
OpenAI-compatible client, so swapping providers later is a base_url/model
swap, not a rewrite.

The prompt itself is fixed (same wording every call) and asks for a
creative/dramatic/artistic/funny result; the actual variation across
calls comes from `temperature`, tuned via scripts/iterate_prompt.py.
"""

import json
import os

from groq import Groq

GROQ_MODEL = "llama-3.3-70b-versatile"

FALLBACK_RESULT = {
    "vibe": "Eclectic Mix",
    "description": "A blend of sounds that doesn't settle into just one lane.",
    "tags": ["Eclectic", "Mixed"],
}

# On Groq's 0-2 scale: high enough to push past generic/flat phrasing
# toward genuinely creative-dramatic-funny output, not so high that
# outputs risk breaking the 1-10 word / no-trailing-punctuation contract.
DEFAULT_TEMPERATURE = 1.1

_client = Groq(api_key=os.environ["GROQ_API_KEY"])


def build_prompt(tracks: list[dict]) -> str:
    """The fixed vibe prompt — same wording every call, on purpose."""
    track_lines = "\n".join(
        f"- {t['name']} by {', '.join(t['artists'])}" for t in tracks
    )
    return (
        "Here are someone's most-listened-to tracks:\n"
        f"{track_lines}\n\n"
        "Describe their music vibe as JSON with three fields:\n"
        '- "vibe": 1-10 words, creative, dramatic, artistic, and/or funny — '
        "avoid generic, flat descriptions.\n"
        '- "description": one supporting sentence (under 25 words) that '
        "expands on the vibe with evocative, sensory detail.\n"
        '- "tags": 2-4 short genre or mood descriptor words (1-2 words each, '
        "Title Case, no punctuation)."
    )


# Llama 3.3 70B/8B don't support Groq's strict json_schema mode (only
# GPT-OSS models and Llama 4 Scout do, as of writing) — so this uses basic
# json_object mode plus an explicit instruction, and leans on validate()
# below (not schema enforcement) to catch anything malformed.
JSON_OBJECT_MODE = {"type": "json_object"}


def call_groq(
    prompt: str, temperature: float = DEFAULT_TEMPERATURE, timeout: float = 10.0
) -> dict:
    """Call Groq, expecting a {"vibe", "description", "tags"} JSON object."""
    response = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    'Respond with a single JSON object of the exact form '
                    '{"vibe": "...", "description": "...", "tags": ["...", "..."]} '
                    "and nothing else."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        response_format=JSON_OBJECT_MODE,
        temperature=temperature,
        timeout=timeout,
    )
    return json.loads(response.choices[0].message.content)


def _validate_vibe(vibe: object) -> bool:
    """1-10 words, no trailing punctuation, non-empty."""
    if not isinstance(vibe, str):
        return False
    vibe = vibe.strip()
    if not vibe:
        return False
    if vibe[-1] in ".,!?;:":
        return False
    word_count = len(vibe.split())
    return 1 <= word_count <= 10


def validate(result: dict) -> bool:
    """vibe passes _validate_vibe; description is a non-empty sentence; 2-4 short tags."""
    if not _validate_vibe(result.get("vibe")):
        return False

    description = result.get("description")
    if not isinstance(description, str) or not description.strip():
        return False

    tags = result.get("tags")
    if not isinstance(tags, list) or not (2 <= len(tags) <= 4):
        return False
    if not all(isinstance(t, str) and t.strip() and len(t.split()) <= 2 for t in tags):
        return False

    return True


def get_vibe(tracks: list[dict]) -> dict:
    """
    Build the prompt, call Groq, validate the result. Retry once on
    invalid output; fall back to FALLBACK_RESULT if it fails twice or the
    call errors/times out.
    """
    prompt = build_prompt(tracks)

    for _ in range(2):
        try:
            result = call_groq(prompt)
        except Exception:
            continue
        if validate(result):
            return {
                "vibe": result["vibe"].strip(),
                "description": result["description"].strip(),
                "tags": [t.strip() for t in result["tags"]],
            }

    return FALLBACK_RESULT
