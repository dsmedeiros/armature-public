"""
Tests for task-readiness.sh (TASK-001).

Hook behaviour (verified from source):
  - Reads stdin JSON; NUL-byte in payload → WARN + exit 0 (defense-in-depth).
  - Invalid JSON → exit 0 (fail-open).
  - tool_name == "Task" → PreToolUse(Task) mode; extract prompt from
    tool_input.prompt (fallback: description, task, bare prompt).
  - tool_name absent + scope present → SubagentStart mode; extract prompt.
  - tool_name == "Bash" (or any non-Task non-SubagentStart) → exit 0
    (pass-through).
  - Strict mode: ^#{1,6}\\s+Acceptance\\s+Criteria heading followed by ≥1
    non-blank list item → exit 0.
  - Empty criteria block (heading but no items) → exit 2.
  - Lenient mode: ≥2 keyword-bearing bullets → exit 0 + WARN advisory.
  - Lenient with only 1 keyword bullet → exit 2.
  - Hotfix phase → exit 0 + ADVISORY (bypass).
  - PASS → correlation file written to active-delegations/<hash>.json.
  - Correlation file contains criteria_items list.
  - active-delegations/ directory created if absent.
  - Exit 2 → stderr contains exact phrase "TASK-001".

All tests use tmp_armature so the real repo is never mutated.
"""

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from .helpers import task_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_phase(tmp_armature: Path, phase: str) -> None:
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.parent.mkdir(parents=True, exist_ok=True)
    phase_file.write_text(phase, encoding="utf-8")


def _block(result: subprocess.CompletedProcess, expected_reason: str = "TASK-001") -> None:
    """Assert the hook exited 2 and stderr contains expected_reason."""
    assert result.returncode == 2
    assert expected_reason in result.stderr


def _pass(result: subprocess.CompletedProcess) -> None:
    """Assert the hook exited 0 (pass / fail-open)."""
    assert result.returncode == 0


def _find_correlation_file(tmp_armature: Path) -> Path | None:
    """Return the first .json in active-delegations/, or None."""
    delegations_dir = tmp_armature / ".armature" / "session" / "active-delegations"
    if not delegations_dir.exists():
        return None
    files = list(delegations_dir.glob("*.json"))
    return files[0] if files else None


# ===========================================================================
# MUST tests (16)
# ===========================================================================

# ---------------------------------------------------------------------------
# MUST 1: Strict heading ## Acceptance Criteria → exit 0 + correlation file
# ---------------------------------------------------------------------------

def test_strict_hash_heading_acceptance_criteria(run_hook, tmp_armature):
    """## Acceptance Criteria heading with list item → exit 0, correlation file written."""
    prompt = "## Acceptance Criteria\n- Must pass all checks\n- Must verify output\n"
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _pass(result)
    corr = _find_correlation_file(tmp_armature)
    assert corr is not None, "Correlation file should be written on PASS"


# ---------------------------------------------------------------------------
# MUST 2: Strict heading **Acceptance Criteria:** → exit 0
# ---------------------------------------------------------------------------

def test_strict_bold_acceptance_criteria(run_hook, tmp_armature):
    """**Acceptance Criteria:** heading → exit 0."""
    prompt = "**Acceptance Criteria:**\n- Must verify output\n- Should pass tests\n"
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _pass(result)


# ---------------------------------------------------------------------------
# MUST 3: Strict heading Acceptance criteria: (lowercase) → exit 0
# ---------------------------------------------------------------------------

def test_strict_lowercase_acceptance_criteria(run_hook, tmp_armature):
    """Acceptance criteria: (lowercase) → exit 0."""
    prompt = "Acceptance criteria:\n- Must pass\n- Should verify\n"
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _pass(result)


# ---------------------------------------------------------------------------
# MUST 4: No criteria, no bullet list → exit 2 with TASK-001 in stderr
# ---------------------------------------------------------------------------

def test_no_criteria_blocks(run_hook, tmp_armature):
    """Prompt with no criteria heading and no bullet list → exit 2."""
    prompt = "Implement the feature as described in the design doc."
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _block(result, "TASK-001")


# ---------------------------------------------------------------------------
# MUST 5: Lenient match (≥2 criterion-like bullets, no heading) → exit 0 + WARN
# ---------------------------------------------------------------------------

def test_lenient_match_passes_with_warn(run_hook, tmp_armature):
    """Two criterion-keyword bullets, no heading → exit 0 + WARN advisory."""
    prompt = (
        "Implement the thing.\n"
        "- Must handle edge cases\n"
        "- Should verify the output\n"
    )
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _pass(result)
    assert "WARN" in result.stderr


# ---------------------------------------------------------------------------
# MUST 6: Lenient match below threshold (1 matching bullet) → exit 2
# ---------------------------------------------------------------------------

def test_lenient_match_single_keyword_bullet_blocks(run_hook, tmp_armature):
    """Only 1 criterion-keyword bullet → fails lenient threshold → exit 2."""
    prompt = (
        "Do this task.\n"
        "- Must handle the case\n"
        "- Some other step with no keyword\n"
        "- Another non-keyword bullet\n"
    )
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _block(result, "TASK-001")


# ---------------------------------------------------------------------------
# MUST 7: tool_name = "Bash" → exit 0 (pass-through, not sub-agent spawn)
# ---------------------------------------------------------------------------

def test_tool_name_bash_passthrough(run_hook, tmp_armature):
    """tool_name=Bash → not a sub-agent spawn → exit 0 (pass-through)."""
    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
    })
    result = run_hook(
        "task-readiness.sh",
        payload,
        cwd=str(tmp_armature),
    )
    _pass(result)


# ---------------------------------------------------------------------------
# MUST 8: tool_name absent (not SubagentStart shape either) → exit 0 (fail-open)
# ---------------------------------------------------------------------------

def test_tool_name_absent_no_scope_failopen(run_hook, tmp_armature):
    """tool_name absent + no scope field → not a recognized event → exit 0."""
    payload = json.dumps({"tool_input": {"command": "echo hi"}})
    result = run_hook(
        "task-readiness.sh",
        payload,
        cwd=str(tmp_armature),
    )
    _pass(result)


# ---------------------------------------------------------------------------
# MUST 9: Invalid JSON stdin → exit 0 (fail-open)
# ---------------------------------------------------------------------------

def test_invalid_json_failopen(run_hook, tmp_armature):
    """Invalid JSON → exit 0 (fail-open)."""
    result = run_hook(
        "task-readiness.sh",
        "{{not json at all",
        cwd=str(tmp_armature),
    )
    _pass(result)


# ---------------------------------------------------------------------------
# MUST 10: NUL byte in payload → exit 0 with WARN (not exit 2)
# ---------------------------------------------------------------------------

def test_nul_byte_in_payload_failopen_with_warn(repo_root, tmp_armature):
    """NUL byte in stdin payload → WARN + exit 0 (defense-in-depth, not blocking)."""
    bash_bin = shutil.which("bash")
    if bash_bin is None:
        pytest.skip("bash not available")

    hook_path = repo_root / ".armature" / "hooks" / "task-readiness.sh"
    # Embed NUL inside the JSON payload
    payload = b'{"tool_name":"Task","tool_input":{"prompt":"## Acceptance\x00 Criteria\n- ok\n"}}'

    result = subprocess.run(
        [bash_bin, str(hook_path)],
        input=payload,
        capture_output=True,
        cwd=str(tmp_armature),
        timeout=10,
    )
    assert result.returncode == 0
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "WARN" in stderr


# ---------------------------------------------------------------------------
# MUST 11: Hotfix phase + no criteria → exit 0 + ADVISORY (not exit 2)
# ---------------------------------------------------------------------------

def test_hotfix_phase_no_criteria_bypass(run_hook, tmp_armature):
    """Hotfix phase + prompt with no criteria → exit 0 + ADVISORY (not blocked)."""
    _write_phase(tmp_armature, "Hotfix")
    prompt = "Do the thing without any criteria."
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _pass(result)
    assert "ADVISORY" in result.stderr


# ---------------------------------------------------------------------------
# MUST 12: Hotfix phase + criteria present → exit 0
# ---------------------------------------------------------------------------

def test_hotfix_phase_with_criteria_passes(run_hook, tmp_armature):
    """Hotfix phase + valid criteria → exit 0 (bypass fires before detection)."""
    _write_phase(tmp_armature, "Hotfix")
    prompt = "## Acceptance Criteria\n- Must pass\n"
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _pass(result)


# ---------------------------------------------------------------------------
# MUST 13: Correlation file created in active-delegations/ on PASS
# ---------------------------------------------------------------------------

def test_correlation_file_created_on_pass(run_hook, tmp_armature):
    """PASS → .armature/session/active-delegations/<hash>.json created."""
    prompt = "## Acceptance Criteria\n- Must verify\n- Should pass\n"
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _pass(result)
    corr = _find_correlation_file(tmp_armature)
    assert corr is not None
    assert corr.suffix == ".json"
    # Filename is 16-char hex
    assert re.fullmatch(r"[0-9a-f]{16}", corr.stem)


# ---------------------------------------------------------------------------
# MUST 14: Correlation file contains criteria_items list
# ---------------------------------------------------------------------------

def test_correlation_file_contains_criteria_items(run_hook, tmp_armature):
    """Correlation file contains a non-empty criteria_items list and all 5 required fields."""
    prompt = "## Acceptance Criteria\n- Must verify output\n- Should pass tests\n"
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _pass(result)
    corr = _find_correlation_file(tmp_armature)
    assert corr is not None
    data = json.loads(corr.read_text(encoding="utf-8"))
    # Assert all 5 required fields present
    required_fields = {"prompt_hash", "criteria_raw", "criteria_items",
                       "timestamp", "tool_name"}
    assert set(data.keys()) >= required_fields, (
        f"Missing fields: {required_fields - set(data.keys())}"
    )
    # Type checks
    assert isinstance(data["prompt_hash"], str)
    assert isinstance(data["criteria_raw"], str)
    assert isinstance(data["criteria_items"], list)
    assert isinstance(data["timestamp"], str)
    assert isinstance(data["tool_name"], str)
    # Content checks
    assert len(data["prompt_hash"]) == 16  # SHA-256 first 16 hex
    assert data["tool_name"] == "Task"
    assert len(data["criteria_items"]) >= 1


# ---------------------------------------------------------------------------
# MUST 15: active-delegations/ directory created if absent
# ---------------------------------------------------------------------------

def test_active_delegations_dir_created(run_hook, tmp_armature):
    """Hook creates active-delegations/ directory if it does not exist."""
    delegations_dir = tmp_armature / ".armature" / "session" / "active-delegations"
    assert not delegations_dir.exists(), "Should not exist before the test"

    prompt = "## Acceptance Criteria\n- Must pass\n"
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _pass(result)
    assert delegations_dir.exists()


# ---------------------------------------------------------------------------
# MUST 16: Exit reason text present in stderr when exit 2
# ---------------------------------------------------------------------------

def test_block_stderr_contains_reason(run_hook, tmp_armature):
    """Exit 2 → stderr contains the exact phrase about TASK-001."""
    prompt = "Just do the thing."
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "Task requires acceptance criteria before delegation per TASK-001" in result.stderr


# ===========================================================================
# SHOULD tests (8)
# ===========================================================================

# ---------------------------------------------------------------------------
# SHOULD 17: Criteria heading inside fenced code block — strict mode matches
#            (conservative: no exclusion of fenced blocks)
# ---------------------------------------------------------------------------

def test_strict_matches_heading_in_fenced_block(run_hook, tmp_armature):
    """Strict mode conservatively matches 'Acceptance Criteria' even inside fenced block.

    The implementation does not exclude fenced blocks in strict mode (simpler
    implementation; documented limitation).  A heading-only presence inside a
    fence still triggers strict match if followed by a list item.
    """
    prompt = (
        "```\n"
        "## Acceptance Criteria\n"
        "- Must pass\n"
        "```\n"
    )
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _pass(result)


# ---------------------------------------------------------------------------
# SHOULD 18: Empty criteria block after heading → exit 2
# ---------------------------------------------------------------------------

def test_empty_criteria_block_blocks(run_hook, tmp_armature):
    """Strict heading present but no list items → exit 2 (empty block)."""
    prompt = "## Acceptance Criteria\n\nDo the thing.\n"
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _block(result, "TASK-001")


# ---------------------------------------------------------------------------
# SHOULD 19: Unicode in prompt text → handled without crash
# ---------------------------------------------------------------------------

def test_unicode_in_prompt_no_crash(run_hook, tmp_armature):
    """Prompt with Unicode characters (emoji, CJK) → no crash, deterministic exit."""
    prompt = (
        "## Acceptance Criteria\n"
        "- Must handle 中文 characters \U0001f600\n"
        "- Should verify éàü encoding\n"
    )
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    # Should pass (strict match)
    _pass(result)


# ---------------------------------------------------------------------------
# SHOULD 20: Very long prompt (>10000 chars) → completes within 3 seconds
# ---------------------------------------------------------------------------

def test_long_prompt_completes_in_time(run_hook, tmp_armature):
    """Prompt >10000 chars with criteria → exit 0 within 3 seconds."""
    big_filler = "This is some filler text. " * 400  # ~10400 chars
    prompt = f"## Acceptance Criteria\n- Must pass\n- Should verify\n\n{big_filler}"
    start = time.monotonic()
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    elapsed = time.monotonic() - start
    _pass(result)
    assert elapsed < 3.0, f"Hook took {elapsed:.2f}s — expected < 3s"


# ---------------------------------------------------------------------------
# SHOULD 21: Multiple ## Acceptance Criteria headings → first one wins
# ---------------------------------------------------------------------------

def test_multiple_headings_first_wins(run_hook, tmp_armature):
    """Multiple acceptance criteria headings → first heading drives detection."""
    prompt = (
        "## Acceptance Criteria\n"
        "- Must pass first check\n"
        "\n"
        "## Acceptance Criteria\n"
        "- Must pass second check\n"
    )
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _pass(result)
    corr = _find_correlation_file(tmp_armature)
    assert corr is not None
    data = json.loads(corr.read_text(encoding="utf-8"))
    # Should have extracted at least one item from the first block
    assert len(data["criteria_items"]) >= 1


# ---------------------------------------------------------------------------
# SHOULD 22: TASK_002_MATCH_THRESHOLD env variable has no effect on readiness
# ---------------------------------------------------------------------------

def test_task_002_env_has_no_effect_on_readiness(run_hook, tmp_armature):
    """TASK_002_MATCH_THRESHOLD env override does not affect task-readiness.sh."""
    prompt = "## Acceptance Criteria\n- Must pass\n"
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        env_overrides={"TASK_002_MATCH_THRESHOLD": "0.0"},
        cwd=str(tmp_armature),
    )
    _pass(result)


# ---------------------------------------------------------------------------
# SHOULD 23: Criteria block extraction includes all bullet items
# ---------------------------------------------------------------------------

def test_criteria_items_all_extracted(run_hook, tmp_armature):
    """All bullet items under the criteria heading are captured in criteria_items."""
    prompt = (
        "## Acceptance Criteria\n"
        "- Must pass check A\n"
        "- Must pass check B\n"
        "- Should verify output C\n"
    )
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _pass(result)
    corr = _find_correlation_file(tmp_armature)
    assert corr is not None
    data = json.loads(corr.read_text(encoding="utf-8"))
    assert len(data["criteria_items"]) == 3


# ---------------------------------------------------------------------------
# SHOULD 24: Phase file with trailing newline and Windows CRLF → Hotfix parsed
# ---------------------------------------------------------------------------

def test_phase_file_crlf_hotfix_parsed(run_hook, tmp_armature):
    """Phase file with CRLF line ending 'Hotfix\\r\\n' → Hotfix parsed correctly."""
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.parent.mkdir(parents=True, exist_ok=True)
    phase_file.write_bytes(b"Hotfix\r\n")

    prompt = "No criteria here."
    result = run_hook(
        "task-readiness.sh",
        task_event(prompt),
        cwd=str(tmp_armature),
    )
    _pass(result)
    assert "ADVISORY" in result.stderr


# ---------------------------------------------------------------------------
# SHOULD 25: Embedded <digit>. in criterion text must be preserved
# ---------------------------------------------------------------------------

def test_should_25_criteria_items_preserve_embedded_digit_dot(tmp_armature, run_hook):
    """Bullet stripping must not corrupt embedded '<digit>.' substrings."""
    prompt = (
        "## Acceptance Criteria\n"
        "- Must verify v1.2 specification\n"
        "- Must check 3. step works\n"
    )
    payload = task_event(prompt)
    result = run_hook("task-readiness.sh", payload, cwd=str(tmp_armature))
    assert result.returncode == 0, f"Should pass: {result.stderr}"
    delegations_dir = tmp_armature / ".armature" / "session" / "active-delegations"
    files = list(delegations_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    items = data["criteria_items"]
    assert any("v1.2" in item for item in items), (
        f"Embedded 'v1.2' must be preserved in criteria_items: {items}"
    )
    assert any("3." in item for item in items), (
        f"Embedded '3.' must be preserved in criteria_items: {items}"
    )


# ---------------------------------------------------------------------------
# SHOULD 26: CR-only line endings normalized before regex matching
# ---------------------------------------------------------------------------

def test_should_26_cr_only_line_endings_normalized(tmp_armature, run_hook):
    """Legacy CR-only line endings must be normalized before regex matching."""
    prompt = "## Acceptance Criteria\r- Must pass\r- Should verify\r"
    payload = task_event(prompt)
    result = run_hook("task-readiness.sh", payload, cwd=str(tmp_armature))
    assert result.returncode == 0, f"CR-only prompt must pass: {result.stderr}"


# ---------------------------------------------------------------------------
# SHOULD 27: SubagentStart shape with criteria → passes (R1 dual-mode)
# ---------------------------------------------------------------------------

def test_should_27_subagent_start_shape_evaluates_criteria(tmp_armature, run_hook):
    """SubagentStart payload (scope present, tool_name absent) evaluates
    criteria the same way PreToolUse(Task) does."""
    prompt = "## Acceptance Criteria\n- Must pass\n- Must verify\n"
    payload = task_event(prompt, tool_name=None, scope=".armature")
    result = run_hook("task-readiness.sh", payload, cwd=str(tmp_armature))
    assert result.returncode == 0, f"SubagentStart shape with criteria must pass: {result.stderr}"
    delegations_dir = tmp_armature / ".armature" / "session" / "active-delegations"
    assert any(delegations_dir.glob("*.json")), "Correlation file must be written"


def test_should_28_subagent_start_shape_blocks_without_criteria(tmp_armature, run_hook):
    """SubagentStart payload without criteria must block (exit 2)."""
    payload = task_event("just do the thing", tool_name=None, scope=".armature")
    result = run_hook("task-readiness.sh", payload, cwd=str(tmp_armature))
    assert result.returncode == 2, f"SubagentStart shape without criteria must block"
    assert "TASK-001" in result.stderr


# ---------------------------------------------------------------------------
# Cycle-16: PreToolUse(Agent) — current canonical Claude Code tool name
# ---------------------------------------------------------------------------

def test_pretooluse_agent_tool_name_passes_with_criteria(tmp_armature, run_hook):
    """tool_name == 'Agent' is the documented Claude Code matcher; a payload
    with acceptance criteria must pass and write the correlation file."""
    prompt = "## Acceptance Criteria\n- Must implement X\n- Must add tests\n"
    payload = task_event(prompt, tool_name="Agent")
    result = run_hook("task-readiness.sh", payload, cwd=str(tmp_armature))
    assert result.returncode == 0, (
        f"PreToolUse(Agent) with criteria must pass: stderr={result.stderr}"
    )
    delegations_dir = tmp_armature / ".armature" / "session" / "active-delegations"
    assert any(delegations_dir.glob("*.json"))


def test_pretooluse_agent_tool_name_blocks_without_criteria(tmp_armature, run_hook):
    """tool_name == 'Agent' without acceptance criteria must block (exit 2)."""
    payload = task_event("just do the thing", tool_name="Agent")
    result = run_hook("task-readiness.sh", payload, cwd=str(tmp_armature))
    assert result.returncode == 2, "PreToolUse(Agent) without criteria must block"
    assert "TASK-001" in result.stderr
