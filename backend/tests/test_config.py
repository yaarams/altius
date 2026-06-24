"""
Property 14: Startup Fails Fast on Missing Environment Variables.

Tests that missing_required_vars() correctly identifies absent / empty vars.
sys.exit is NOT called in these tests — only the detection function is exercised.
validate_required() is tested via monkeypatching sys.exit to prevent process termination.

Feature: investor-document-platform, Property 14: Startup fails fast on missing env vars
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from backend.config import Settings, missing_required_vars

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUIRED_VARS = ["PORTAL_USER", "PORTAL_PASSWORD", "GEMINI_API_KEY"]


def _settings_with(**overrides) -> Settings:
    """Build a Settings instance with given fields; defaults fill remaining required vars."""
    defaults = {
        "PORTAL_USER": "user@example.com",
        "PORTAL_PASSWORD": "secret",
        "GEMINI_API_KEY": "key123",
        "DATABASE_URL": "sqlite:///./data/app.db",
    }
    defaults.update(overrides)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# Example-based tests
# ---------------------------------------------------------------------------

def test_no_missing_vars_when_all_present():
    s = _settings_with()
    assert missing_required_vars(s) == []


def test_detects_single_missing_var():
    s = _settings_with(PORTAL_USER="")
    missing = missing_required_vars(s)
    assert "PORTAL_USER" in missing


def test_detects_whitespace_only_as_missing():
    s = _settings_with(GEMINI_API_KEY="   ")
    missing = missing_required_vars(s)
    assert "GEMINI_API_KEY" in missing


def test_detects_all_missing_when_all_empty():
    s = _settings_with(PORTAL_USER="", PORTAL_PASSWORD="", GEMINI_API_KEY="")
    missing = missing_required_vars(s)
    assert set(missing) == {"PORTAL_USER", "PORTAL_PASSWORD", "GEMINI_API_KEY"}


def test_missing_list_is_sorted():
    """Result must be sorted so error messages are deterministic."""
    s = _settings_with(PORTAL_USER="", PORTAL_PASSWORD="", GEMINI_API_KEY="")
    missing = missing_required_vars(s)
    assert missing == sorted(missing)


def test_validate_required_calls_exit_on_missing(monkeypatch):
    """validate_required() must call sys.exit(1) when vars are missing."""
    import sys
    exit_calls: list[int] = []
    monkeypatch.setattr(sys, "exit", lambda code: exit_calls.append(code))

    from backend.config import validate_required

    s = _settings_with(PORTAL_USER="", PORTAL_PASSWORD="")
    validate_required(s)
    assert exit_calls == [1], f"expected [1], got {exit_calls}"


def test_validate_required_does_not_exit_when_all_present(monkeypatch):
    """validate_required() must NOT call sys.exit when all vars are set."""
    import sys
    exit_calls: list[int] = []
    monkeypatch.setattr(sys, "exit", lambda code: exit_calls.append(code))

    from backend.config import validate_required

    s = _settings_with()
    validate_required(s)
    assert exit_calls == [], f"unexpected exit calls: {exit_calls}"


# ---------------------------------------------------------------------------
# Hypothesis property-based tests (≥ 100 examples)
# Feature: investor-document-platform, Property 14: Startup fails fast on missing env vars
# ---------------------------------------------------------------------------

h_settings.register_profile(
    "ci",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=5000,
)
h_settings.load_profile("ci")

# Strategy: a subset of required vars (at least 1) to leave empty
_non_empty_str = st.text(min_size=1, max_size=50).filter(
    lambda s: s.strip() != "" and "\x00" not in s
)
_missing_subset = st.sets(
    st.sampled_from(REQUIRED_VARS), min_size=1, max_size=len(REQUIRED_VARS)
)


@given(missing_subset=_missing_subset, filler=_non_empty_str)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=5000)
def test_hypothesis_missing_vars_detected(missing_subset: set[str], filler: str):
    """
    For any non-empty subset of required vars set to empty string,
    missing_required_vars() must return exactly those var names.
    """
    kwargs: dict = {}
    for var in REQUIRED_VARS:
        kwargs[var] = "" if var in missing_subset else filler
    kwargs["DATABASE_URL"] = "sqlite:///./data/app.db"

    s = Settings(**kwargs)
    detected = set(missing_required_vars(s))
    assert detected == missing_subset, (
        f"Expected missing={missing_subset}, got detected={detected}"
    )


@given(filler=_non_empty_str)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=5000)
def test_hypothesis_no_false_positives(filler: str):
    """
    When all required vars are non-empty, missing_required_vars() returns [].
    """
    s = Settings(
        PORTAL_USER=filler,
        PORTAL_PASSWORD=filler,
        GEMINI_API_KEY=filler,
        DATABASE_URL="sqlite:///./data/app.db",
    )
    assert missing_required_vars(s) == []
