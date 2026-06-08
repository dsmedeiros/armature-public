"""
Contract tests for .armature/templates/settings-hooks.json.tmpl.

Verifies that the template:
  1. Parses as valid JSON.
  2. Uses only canonical Claude Code hook event key names.
  3. Uses only documented Claude Code tool names in matcher values.
  4. Quotes all ${CLAUDE_PROJECT_DIR} occurrences for path-with-spaces safety.
  5. Specifies all timeouts as integer seconds (not milliseconds).
"""

import json
from pathlib import Path

TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / ".armature" / "templates" / "settings-hooks.json.tmpl"
)


def _load_template():
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Test 1: template parses as valid JSON
# ---------------------------------------------------------------------------

def test_template_parses_as_json():
    """The template file must be valid JSON (json.load succeeds)."""
    data = _load_template()
    assert isinstance(data, dict), "Top-level must be a JSON object"
    assert "hooks" in data, "Top-level must have a 'hooks' key"


# ---------------------------------------------------------------------------
# Test 2: hook event keys are canonical Claude Code event names
# ---------------------------------------------------------------------------

CANONICAL_HOOK_EVENTS = {
    "PreToolUse",
    "PostToolUse",
    "SubagentStart",
    "SubagentStop",
    "Stop",
    "SessionStart",
    "ConfigChange",
}


def test_hook_event_keys_are_canonical():
    """All keys under 'hooks' (excluding _comment* keys) must be canonical event names."""
    data = _load_template()
    hooks = data["hooks"]
    for key in hooks:
        if key.startswith("_comment"):
            continue
        assert key in CANONICAL_HOOK_EVENTS, (
            f"Unexpected hook event key: {key!r}. "
            f"Must be one of {sorted(CANONICAL_HOOK_EVENTS)}"
        )


# ---------------------------------------------------------------------------
# Test 3: PreToolUse and PostToolUse matchers are documented Claude Code tools
# ---------------------------------------------------------------------------

DOCUMENTED_TOOLS = {"Bash", "Edit", "Write", "MultiEdit", "Read", "WebFetch", "WebSearch", "Agent"}


def test_pretooluse_matchers_are_documented_tools():
    """Every matcher under PreToolUse and PostToolUse must name documented Claude Code tools."""
    data = _load_template()
    hooks = data["hooks"]
    for event_name in ("PreToolUse", "PostToolUse"):
        entries = hooks.get(event_name, [])
        for entry in entries:
            matcher = entry.get("matcher")
            if matcher is None:
                continue
            # Matcher may be pipe-delimited (e.g. "Edit|Write")
            parts = [p.strip() for p in matcher.split("|")]
            for part in parts:
                assert part in DOCUMENTED_TOOLS, (
                    f"{event_name} matcher {part!r} (from {matcher!r}) is not a "
                    f"documented Claude Code tool. Allowed: {sorted(DOCUMENTED_TOOLS)}"
                )


# ---------------------------------------------------------------------------
# Test 4: ${CLAUDE_PROJECT_DIR} is always quoted in command values
# ---------------------------------------------------------------------------

def _iter_commands(hooks_dict):
    """Yield all command string values from any depth of the hooks structure."""
    for event_entries in hooks_dict.values():
        if not isinstance(event_entries, list):
            continue
        for entry in event_entries:
            if not isinstance(entry, dict):
                continue
            for hook in entry.get("hooks", []):
                if isinstance(hook, dict):
                    cmd = hook.get("command")
                    if isinstance(cmd, str):
                        yield cmd


def test_claude_project_dir_is_quoted():
    """Every command containing ${CLAUDE_PROJECT_DIR} must wrap it in double quotes."""
    data = _load_template()
    hooks = data["hooks"]
    VAR = "${CLAUDE_PROJECT_DIR}"
    QUOTED = '"${CLAUDE_PROJECT_DIR}"'
    for command in _iter_commands(hooks):
        if VAR in command:
            assert QUOTED in command, (
                f"Command uses {VAR!r} but it is not double-quoted. "
                f"Expected {QUOTED!r} in: {command!r}"
            )


# ---------------------------------------------------------------------------
# Test 5: all timeout values are integer seconds (1 <= v <= 7200)
# ---------------------------------------------------------------------------

def test_all_timeouts_are_integer_seconds():
    """Every timeout value must be an integer between 1 and 7200 (seconds, not milliseconds)."""
    data = _load_template()
    hooks = data["hooks"]
    for event_entries in hooks.values():
        if not isinstance(event_entries, list):
            continue
        for entry in event_entries:
            if not isinstance(entry, dict):
                continue
            for hook in entry.get("hooks", []):
                if not isinstance(hook, dict):
                    continue
                timeout = hook.get("timeout")
                if timeout is None:
                    continue
                assert isinstance(timeout, int), (
                    f"timeout must be an integer (seconds), got {type(timeout).__name__}: {timeout!r}"
                )
                assert 1 <= timeout <= 7200, (
                    f"timeout {timeout!r} is out of range [1, 7200] seconds. "
                    f"If this was meant as milliseconds, divide by 1000."
                )
