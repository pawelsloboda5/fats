"""Unit tests for assets/settings_defaults.json.

Added in v1.1.0 to cover the new `models` and `concurrency` keys that drive
the three-tier subagent architecture (orchestrator / search / resume).
Tests assert directly on the literal JSON — we deliberately do not build a
settings-validator class just to have something to test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


SETTINGS_PATH = Path(__file__).parent.parent / "assets" / "settings_defaults.json"


@pytest.fixture(scope="module")
def settings():
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def test_settings_defaults_parses_as_json():
    """The asset file must exist and parse as valid JSON."""
    assert SETTINGS_PATH.exists(), f"missing: {SETTINGS_PATH}"
    data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_models_key_has_expected_defaults(settings):
    """v1.1.0 introduced a three-tier model assignment."""
    assert settings["models"] == {
        "orchestrator": "opus",
        "search_agent": "haiku",
        "resume_agent": "sonnet",
    }


def test_concurrency_key_has_expected_defaults(settings):
    """v1.1.0 introduced parallel-dispatch knobs for subagents."""
    assert settings["concurrency"] == {
        "search_agents": 5,
        "resume_agents": 5,
    }


def test_model_values_are_valid_tier(settings):
    """Every model value must be one of the known Claude tiers."""
    valid_tiers = {"haiku", "sonnet", "opus"}
    for role, tier in settings["models"].items():
        assert tier in valid_tiers, (
            f"models.{role} = {tier!r} not in {valid_tiers}"
        )


def test_concurrency_values_in_valid_range(settings):
    """Concurrency values must be ints in 1..8 (sane parallelism cap)."""
    for role, n in settings["concurrency"].items():
        assert isinstance(n, int), f"concurrency.{role} is not int: {n!r}"
        assert 1 <= n <= 8, f"concurrency.{role} = {n} not in 1..8"
