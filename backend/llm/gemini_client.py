"""
Shared Gemini JSON helper — T2.2/T2.3.

Exposes a single network-facing function ``generate_json()`` that is the ONLY
place where the google-genai SDK is called.  All other code imports this
function; tests monkeypatch only this one symbol.

Model: gemini-2.5-flash  (ADR-003 / CONF-2 — gemini-2.x family).
JSON mode: response_mime_type="application/json", temperature=0.0.
Retry: one automatic retry on JSON-parse failure, then raises GeminiError.
API key: read from backend.config.Settings.GEMINI_API_KEY — never logged.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config constant (single source of truth for callers)
# ---------------------------------------------------------------------------

GEMINI_MODEL = "models/gemini-2.5-flash"

# ---------------------------------------------------------------------------
# Typed exception
# ---------------------------------------------------------------------------


class GeminiError(RuntimeError):
    """
    Raised when the Gemini call fails after all retries.

    Covers: API errors, JSON parse errors, schema validation failures.
    """


# ---------------------------------------------------------------------------
# Lazy client — isolated so tests can monkeypatch _raw_generate()
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    """Return the lazily-created google-genai client."""
    global _client
    if _client is None:
        from google import genai  # type: ignore
        from backend.config import get_settings

        settings = get_settings()
        # API key read from config, never printed/logged
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def _raw_generate(prompt: str, system_prompt: str) -> str:
    """
    Send a single request to Gemini in JSON mode and return the raw text.

    This is the ONLY network call in this module.  Monkeypatch this function
    in tests to avoid real API calls.

    Args:
        prompt: User-turn prompt text.
        system_prompt: Optional system instruction.

    Returns:
        Raw text response from Gemini (should be valid JSON).

    Raises:
        GeminiError: on any Gemini API error.
    """
    from google.genai import types  # type: ignore

    client = _get_client()
    config = types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
        system_instruction=system_prompt if system_prompt else None,
    )
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        return response.text.strip()
    except Exception as exc:
        raise GeminiError(f"Gemini API error: {exc}") from exc


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_json(
    prompt: str,
    schema_hint: str | dict | None = None,
    system_prompt: str = "",
) -> dict[str, Any]:
    """
    Call Gemini in JSON mode and return the parsed dict.

    Retries ONCE on JSON-parse failure, then raises ``GeminiError``.

    Args:
        prompt: User-turn text sent to Gemini.
        schema_hint: Optional schema description injected into system_prompt
            (if ``system_prompt`` is empty) or appended (if provided as dict,
            pretty-printed).  Pass ``None`` to omit.
        system_prompt: Full system instruction.  If non-empty, ``schema_hint``
            is appended to it.

    Returns:
        Parsed JSON dict from Gemini's response.

    Raises:
        GeminiError: on API error or if JSON parsing fails after one retry.
    """
    # Build effective system prompt
    effective_system = system_prompt
    if schema_hint is not None:
        hint_str = (
            json.dumps(schema_hint, indent=2)
            if isinstance(schema_hint, dict)
            else str(schema_hint)
        )
        if effective_system:
            effective_system = f"{effective_system}\n\nExpected JSON schema: {hint_str}"
        else:
            effective_system = f"Return ONLY valid JSON matching this schema: {hint_str}"

    # Attempt 1
    try:
        raw = _raw_generate(prompt, effective_system)
        return _parse_json(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Gemini returned invalid JSON on attempt 1 — retrying once. Error: %s", exc
        )

    # Attempt 2 (single retry)
    try:
        raw = _raw_generate(prompt, effective_system)
        return _parse_json(raw)
    except json.JSONDecodeError as exc:
        raise GeminiError(
            f"Gemini returned invalid JSON after 1 retry: {exc}"
        ) from exc
    except GeminiError:
        raise  # API errors re-raised immediately


def _parse_json(text: str) -> dict[str, Any]:
    """Parse text as JSON; raises json.JSONDecodeError on failure."""
    # Strip markdown code fences if present
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Remove opening and closing ```
        inner = lines[1:] if lines[0].startswith("```") else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        stripped = "\n".join(inner)
    return json.loads(stripped)


# ---------------------------------------------------------------------------
# Embedding — text-embedding-004 (ADR-003/004, T3.1)
# ---------------------------------------------------------------------------

EMBED_MODEL = "models/gemini-embedding-001"


def embed_text(text: str) -> list[float]:
    """
    Embed a single text string using Gemini gemini-embedding-001 (3072-d).

    This is the ONLY embedding network call in this module.  Monkeypatch this
    function in tests to avoid real API calls.

    Args:
        text: The text to embed.

    Returns:
        List of 768 floats.

    Raises:
        GeminiError: on any Gemini API error.
    """
    client = _get_client()
    try:
        response = client.models.embed_content(
            model=EMBED_MODEL,
            contents=text,
        )
        # google-genai v2 SDK: response.embeddings[0].values
        return list(response.embeddings[0].values)
    except Exception as exc:
        raise GeminiError(f"Gemini embed_text error: {exc}") from exc


# ---------------------------------------------------------------------------
# Text generation — for RAG chat (T3.2)
# ---------------------------------------------------------------------------

def generate_text(prompt: str, system_prompt: str = "") -> str:
    """
    Call Gemini in text mode (not JSON) and return the response string.

    Used by the RAG chat module to generate grounded answers.

    This is the ONLY text-generation network call in this module.  Monkeypatch
    this function in tests to avoid real API calls.

    Args:
        prompt: User-turn prompt text.
        system_prompt: Optional system instruction.

    Returns:
        Raw text response from Gemini.

    Raises:
        GeminiError: on any Gemini API error.
    """
    from google.genai import types  # type: ignore

    client = _get_client()
    config = types.GenerateContentConfig(
        temperature=0.0,
        system_instruction=system_prompt if system_prompt else None,
    )
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        return response.text.strip()
    except Exception as exc:
        raise GeminiError(f"Gemini generate_text error: {exc}") from exc
