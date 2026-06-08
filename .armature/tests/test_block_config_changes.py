"""
Tests for block-config-changes.sh (HOOK-002).

Hook behaviour (verified from source):
  - Reads "source" field from stdin JSON.
  - Normalises to lowercase via bash ${SOURCE,,}.
  - Blocked sources (exit 2 + "BLOCK" on stderr):
      user_settings, project_settings, local_settings, skills
  - Allowed source (exit 0, no output):
      policy_settings
  - Empty source (parse failure): exit 0 + "WARN" on stderr (fail-open).
  - Unknown source: exit 0 + "WARN" on stderr.
  - Invalid JSON: python exception caught → SOURCE stays empty → exit 0 + "WARN".

Note: uppercase normalisation (e.g., USER_SETTINGS → blocked) is a SHOULD.
"""

from .helpers import config_event


# ---------------------------------------------------------------------------
# MUST: blocked sources → exit 2 + "BLOCK" on stderr
# ---------------------------------------------------------------------------

def test_user_settings_is_blocked(run_hook):
    result = run_hook("block-config-changes.sh", config_event("user_settings"))
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


def test_project_settings_is_blocked(run_hook):
    result = run_hook("block-config-changes.sh", config_event("project_settings"))
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


def test_local_settings_is_blocked(run_hook):
    result = run_hook("block-config-changes.sh", config_event("local_settings"))
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


def test_skills_is_blocked(run_hook):
    result = run_hook("block-config-changes.sh", config_event("skills"))
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


# ---------------------------------------------------------------------------
# MUST: policy_settings → exit 0 (explicitly allowed)
# ---------------------------------------------------------------------------

def test_policy_settings_is_allowed(run_hook):
    result = run_hook("block-config-changes.sh", config_event("policy_settings"))
    assert result.returncode == 0
    # No BLOCK and no WARN expected for explicitly allowed source
    assert "BLOCK" not in result.stderr
    assert "WARN" not in result.stderr


# ---------------------------------------------------------------------------
# MUST: unknown source → exit 0 with WARN
# ---------------------------------------------------------------------------

def test_unknown_source_exits_zero_with_warn(run_hook):
    result = run_hook("block-config-changes.sh", config_event("some_future_source"))
    assert result.returncode == 0
    assert "WARN" in result.stderr


# ---------------------------------------------------------------------------
# MUST: empty / missing source field → exit 0 fail-open with WARN
# ---------------------------------------------------------------------------

def test_empty_source_field_exits_zero(run_hook):
    """Explicit empty string source should fail open."""
    result = run_hook("block-config-changes.sh", config_event(""))
    assert result.returncode == 0
    assert "WARN" in result.stderr


def test_missing_source_field_exits_zero(run_hook):
    """JSON without a source field at all should fail open."""
    import json
    payload = json.dumps({"tool_input": {"command": "something"}})
    result = run_hook("block-config-changes.sh", payload)
    assert result.returncode == 0
    assert "WARN" in result.stderr


# ---------------------------------------------------------------------------
# SHOULD: uppercase normalisation → exit 2 (bash ${SOURCE,,} lowercases)
# ---------------------------------------------------------------------------

def test_uppercase_user_settings_is_blocked(run_hook):
    """USER_SETTINGS should be normalised to user_settings and blocked."""
    result = run_hook("block-config-changes.sh", config_event("USER_SETTINGS"))
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


def test_mixed_case_skills_is_blocked(run_hook):
    """Skills in mixed case should be normalised and blocked."""
    result = run_hook("block-config-changes.sh", config_event("Skills"))
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


# ---------------------------------------------------------------------------
# SHOULD: invalid JSON → fail-open exit 0
# ---------------------------------------------------------------------------

def test_invalid_json_exits_zero(run_hook):
    """Completely malformed JSON must not crash the hook; fails open."""
    result = run_hook("block-config-changes.sh", "{{not json")
    assert result.returncode == 0
    assert "WARN" in result.stderr
