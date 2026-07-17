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
FALLBACK_VIBE = "Eclectic Mix"

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
        "Describe their music vibe in 1-10 words. The result must be "
        "creative, dramatic, artistic, and/or funny — avoid generic, flat "
        "descriptions."
    )


# Llama 3.3 70B/8B don't support Groq's strict json_schema mode (only
# GPT-OSS models and Llama 4 Scout do, as of writing) — so this uses basic
# json_object mode plus an explicit instruction, and leans on validate()
# below (not schema enforcement) to catch anything malformed.
JSON_OBJECT_MODE = {"type": "json_object"}


def call_groq(
    prompt: str, temperature: float = DEFAULT_TEMPERATURE, timeout: float = 10.0
) -> str:
    """Call Groq, expecting a {"vibe": "..."} JSON object. Returns the raw vibe string."""
    response = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": 'Respond with a single JSON object of the exact form {"vibe": "..."} and nothing else.',
            },
            {"role": "user", "content": prompt},
        ],
        response_format=JSON_OBJECT_MODE,
        temperature=temperature,
        timeout=timeout,
    )
    content = json.loads(response.choices[0].message.content)
    return content["vibe"]


def validate(vibe: str) -> bool:
    """1-10 words, no trailing punctuation, non-empty."""
    vibe = vibe.strip()
    if not vibe:
        return False
    if vibe[-1] in ".,!?;:":
        return False
    word_count = len(vibe.split())
    return 1 <= word_count <= 10


def get_vibe(tracks: list[dict]) -> str:
    """
    Build the prompt, call Groq, validate the result. Retry once on
    invalid output; fall back to FALLBACK_VIBE if it fails twice or the
    call errors/times out.
    """
    prompt = build_prompt(tracks)

    for _ in range(2):
        try:
            vibe = call_groq(prompt)
        except Exception:
            continue
        if validate(vibe):
            return vibe.strip()

    return FALLBACK_VIBE
