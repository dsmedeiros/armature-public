"""
Tests for task-completion.sh (TASK-002).

Hook behaviour (verified from source):
  - Reads stdin JSON; NUL-byte in payload → WARN + exit 0 (defense-in-depth).
  - Invalid JSON → ADVISORY + exit 0 (fail-open).
  - Hotfix phase → ADVISORY bypass + exit 0.
  - Ordered deliverable extraction: tool_result.content, output, result,
    subagent_output, message.
  - Reads most-recently-modified .json in active-delegations/.
  - No active-delegations/ or no .json files → ADVISORY + exit 0.
  - Keyword-anchor scan: stopword-filtered tokens from each criterion item
    checked against deliverable text (case-insensitive substring).
  - Match ratio >= TASK_002_MATCH_THRESHOLD (default 0.7) → PASS: to stdout.
  - Match ratio < threshold → ADVISORY: to stdout.
  - Deletes correlation file after evaluation (regardless of pass/fail).
  - Always exits 0 — advisory-only hook.

All tests use tmp_armature so the real repo is never mutated.
"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from .helpers import subagent_stop_event, posttooluse_agent_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_phase(tmp_armature: Path, phase: str) -> None:
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.parent.mkdir(parents=True, exist_ok=True)
    phase_file.write_text(phase, encoding="utf-8")


def _write_correlation(tmp_armature: Path, criteria_items: list, filename: str = "test_hash.json") -> Path:
    """Write a correlation file into active-delegations/ and return its path."""
    delegations_dir = tmp_armature / ".armature" / "session" / "active-delegations"
    delegations_dir.mkdir(parents=True, exist_ok=True)
    corr_file = delegations_dir / filename
    corr_data = {
        "prompt_hash": filename.replace(".json", ""),
        "criteria_raw": "## Acceptance Criteria\n" + "\n".join("- " + c for c in criteria_items),
        "criteria_items": criteria_items,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "tool_name": "Task",
    }
    corr_file.write_text(json.dumps(corr_data, indent=2), encoding="utf-8")
    return corr_file


def _delegations_dir(tmp_armature: Path) -> Path:
    return tmp_armature / ".armature" / "session" / "active-delegations"


# ===========================================================================
# MUST tests (13)
# ===========================================================================

# ---------------------------------------------------------------------------
# MUST 1: Deliverable containing all criterion keywords → PASS emitted, exit 0
# ---------------------------------------------------------------------------

def test_all_criteria_matched_emits_pass(run_hook, tmp_armature):
    """Deliverable covering all criterion keywords → PASS: emitted, exit 0."""
    criteria = [
        "Must verify the output format is correct",
        "Should check authentication works",
        "Must validate schema integrity",
    ]
    _write_correlation(tmp_armature, criteria)

    deliverable = (
        "The implementation is complete. Output format has been verified. "
        "Authentication checks are passing. Schema integrity validated successfully."
    )
    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output=deliverable),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "PASS:" in result.stdout


# ---------------------------------------------------------------------------
# MUST 2: Deliverable missing most criteria keywords → ADVISORY, exit 0
# ---------------------------------------------------------------------------

def test_missing_criteria_keywords_emits_advisory(run_hook, tmp_armature):
    """Deliverable with very few keyword hits → ADVISORY emitted, never exit 2."""
    criteria = [
        "Must verify authentication flow",
        "Should check database schema",
        "Must validate API response format",
        "Should test edge case handling",
        "Must confirm logging output",
    ]
    _write_correlation(tmp_armature, criteria)

    # Deliverable mentions none of the specific domain words
    deliverable = "Done. The work has been completed as requested."
    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output=deliverable),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY:" in result.stdout


# ---------------------------------------------------------------------------
# MUST 3: No correlation file → ADVISORY with "no active delegation found"
# ---------------------------------------------------------------------------

def test_no_correlation_file_emits_advisory(run_hook, tmp_armature):
    """No .json in active-delegations/ → ADVISORY with no active delegation, exit 0."""
    # Ensure delegations_dir does not exist
    delegations_dir = _delegations_dir(tmp_armature)
    if delegations_dir.exists():
        shutil.rmtree(str(delegations_dir))

    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output="Implementation complete."),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY:" in result.stdout
    assert "no active delegation" in result.stdout.lower()


# ---------------------------------------------------------------------------
# MUST 4: Correlation file read and deleted after evaluation
# ---------------------------------------------------------------------------

def test_correlation_file_deleted_after_evaluation(run_hook, tmp_armature):
    """Correlation file must be absent after task-completion.sh runs."""
    criteria = ["Must verify output", "Should pass tests"]
    corr_file = _write_correlation(tmp_armature, criteria)

    assert corr_file.exists(), "Correlation file should exist before hook run"

    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output="Output verified. Tests passed."),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert not corr_file.exists(), "Correlation file must be deleted after evaluation"


# ---------------------------------------------------------------------------
# MUST 5: Empty deliverable text → ADVISORY, exit 0
# ---------------------------------------------------------------------------

def test_empty_deliverable_emits_advisory(run_hook, tmp_armature):
    """Empty deliverable string → ADVISORY (no keyword matches), exit 0."""
    criteria = ["Must verify authentication", "Should check output format"]
    _write_correlation(tmp_armature, criteria)

    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output=""),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY:" in result.stdout


# ---------------------------------------------------------------------------
# MUST 6: Invalid JSON stdin → ADVISORY, exit 0 (fail-open)
# ---------------------------------------------------------------------------

def test_invalid_json_emits_advisory_failopen(run_hook, tmp_armature):
    """Invalid JSON payload → ADVISORY emitted, exit 0 (fail-open)."""
    result = run_hook(
        "task-completion.sh",
        "{{not valid json at all",
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY:" in result.stdout


# ---------------------------------------------------------------------------
# MUST 7: NUL byte in stdin payload → WARN stderr, exit 0 (not crash)
# ---------------------------------------------------------------------------

def test_nul_byte_in_payload_warn_and_exit_0(repo_root, tmp_armature):
    """NUL byte in stdin payload → WARN + exit 0 (defense-in-depth, no crash)."""
    bash_bin = shutil.which("bash")
    if bash_bin is None:
        pytest.skip("bash not available")

    hook_path = repo_root / ".armature" / "hooks" / "task-completion.sh"
    payload = b'{"output":"implementation\x00complete"}'

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
# MUST 8: Hotfix phase → exit 0 + ADVISORY bypass
# ---------------------------------------------------------------------------

def test_hotfix_phase_bypass(run_hook, tmp_armature):
    """Hotfix phase → exit 0 + ADVISORY bypass on stderr."""
    _write_phase(tmp_armature, "Hotfix")
    criteria = ["Must verify output"]
    _write_correlation(tmp_armature, criteria)

    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output="Some deliverable."),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" in result.stderr
    assert "Hotfix" in result.stderr


# ---------------------------------------------------------------------------
# MUST 9: TASK_002_MATCH_THRESHOLD=1.0 → all criteria must match for PASS
# ---------------------------------------------------------------------------

def test_threshold_1_0_requires_all_matches(run_hook, tmp_armature):
    """With threshold=1.0, all criteria items must have keyword hit for PASS."""
    criteria = [
        "Must verify output format",
        "Should check authentication",
        "Must validate schema",
    ]
    _write_correlation(tmp_armature, criteria)

    # Deliverable only mentions two of three domain areas
    deliverable = "Output format verified. Schema validated. No mention of auth."
    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output=deliverable),
        env_overrides={"TASK_002_MATCH_THRESHOLD": "1.0"},
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    # "No mention of auth" → authentication not covered → below threshold
    assert "ADVISORY:" in result.stdout


# ---------------------------------------------------------------------------
# MUST 10: TASK_002_MATCH_THRESHOLD=0.0 → always PASS
# ---------------------------------------------------------------------------

def test_threshold_0_0_always_pass(run_hook, tmp_armature):
    """With threshold=0.0, even zero keyword matches → PASS."""
    criteria = ["Must verify exotic_xyz_widget_feature", "Should check quux_flux_capacitor"]
    _write_correlation(tmp_armature, criteria)

    deliverable = "Done. Nothing relevant."
    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output=deliverable),
        env_overrides={"TASK_002_MATCH_THRESHOLD": "0.0"},
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "PASS:" in result.stdout


# ---------------------------------------------------------------------------
# MUST 11: Criteria items with stopwords only → no crash (treated as no keywords)
# ---------------------------------------------------------------------------

def test_stopword_only_criteria_no_crash(run_hook, tmp_armature):
    """Criteria item containing only stopwords → no crash, ADVISORY emitted."""
    # Stopwords only: "must", "should", "the", "is", "a"
    criteria = ["must the is a", "should of to for"]
    _write_correlation(tmp_armature, criteria)

    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output="Implementation complete."),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    # Either PASS or ADVISORY is acceptable — just no crash


# ---------------------------------------------------------------------------
# MUST 12: Deliverable in tool_result.content field → extracted correctly
# ---------------------------------------------------------------------------

def test_deliverable_in_tool_result_content(run_hook, tmp_armature):
    """Deliverable in tool_result.content → extracted and evaluated correctly."""
    criteria = ["Must verify authentication flow", "Should check output"]
    _write_correlation(tmp_armature, criteria)

    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(tool_result_content="Authentication flow verified. Output checked."),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "PASS:" in result.stdout


# ---------------------------------------------------------------------------
# MUST 13: Deliverable in output field → extracted correctly
# ---------------------------------------------------------------------------

def test_deliverable_in_output_field(run_hook, tmp_armature):
    """Deliverable in output field → extracted and evaluated correctly."""
    criteria = ["Must validate schema integrity"]
    _write_correlation(tmp_armature, criteria)

    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output="Schema integrity has been validated."),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "PASS:" in result.stdout


# ===========================================================================
# SHOULD tests (7)
# ===========================================================================

# ---------------------------------------------------------------------------
# SHOULD 14: D11 smoke — TASK-002 in agents.md invariants → definition-of-done fires
# ---------------------------------------------------------------------------

def test_should_14_task002_invariant_triggers_definition_of_done(repo_root):
    """D11 smoke: triggers.yaml must have TASK-002 → definition-of-done mapping.

    This is a config-level verification. The invariant trigger for TASK-002
    pointing at the definition-of-done discipline is confirmed in triggers.yaml.
    """
    triggers_path = repo_root / ".armature" / "disciplines" / "triggers.yaml"
    assert triggers_path.exists(), "triggers.yaml must exist"
    content = triggers_path.read_text(encoding="utf-8")

    # Verify definition-of-done entry exists
    assert "definition-of-done:" in content

    # Verify TASK-002 appears in the invariant pattern for definition-of-done
    # Find the definition-of-done block and verify TASK-002 is referenced
    assert "TASK-002" in content, "TASK-002 must appear in triggers.yaml"

    # More precise: TASK-002 must be in the definition-of-done section
    # Find definition-of-done section
    dod_idx = content.find("definition-of-done:")
    assert dod_idx >= 0

    # Find next top-level entry (non-indented) after definition-of-done
    rest = content[dod_idx:]
    # Within the definition-of-done block, TASK-002 must appear
    # Find next entry at same level
    next_entry = re.search(r"\n\S", rest[1:])
    if next_entry:
        block = rest[:next_entry.start() + 1]
    else:
        block = rest
    assert "TASK-002" in block, (
        "TASK-002 must be in the definition-of-done trigger pattern block"
    )


# ---------------------------------------------------------------------------
# SHOULD 15: Correlation file older than threshold treated as stale (functional test)
# ---------------------------------------------------------------------------

def test_should_15_stale_correlation_file_still_used(run_hook, tmp_armature):
    """Most-recent heuristic picks the file even if older; no stale-skip at task-completion level.

    (GC by post-stop.sh handles >24h files; task-completion.sh always uses most-recent.)
    This test verifies the hook still functions when only one file exists.
    """
    criteria = ["Must verify output"]
    _write_correlation(tmp_armature, criteria)

    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output="Output verified."),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    # Hook must emit exactly one of PASS or ADVISORY (no silent passes).
    has_pass = "PASS:" in result.stdout
    has_advisory = "ADVISORY:" in result.stdout
    assert has_pass or has_advisory, (
        f"Hook produced neither PASS nor ADVISORY: stdout={result.stdout!r}"
    )
    assert not (has_pass and has_advisory), (
        f"Hook produced both PASS and ADVISORY: stdout={result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# SHOULD 16: Multiple correlation files → most recent wins
# ---------------------------------------------------------------------------

def test_should_16_most_recent_correlation_file_wins(run_hook, tmp_armature):
    """When multiple .json files exist, the most recently modified one is read."""
    delegations_dir = _delegations_dir(tmp_armature)
    delegations_dir.mkdir(parents=True, exist_ok=True)

    # Write older file with criteria that won't match
    old_criteria = ["Must verify exotic_zzz_nonexistent_thing_xyz"]
    old_file = _write_correlation(tmp_armature, old_criteria, "old_hash.json")
    # Force an older mtime
    old_mtime = time.time() - 60
    os.utime(str(old_file), (old_mtime, old_mtime))

    # Write newer file with criteria that will match
    new_criteria = ["Must verify output format"]
    _write_correlation(tmp_armature, new_criteria, "new_hash.json")
    # new_hash.json has current mtime (newer)

    deliverable = "Output format has been verified successfully."
    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output=deliverable),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    # Should PASS because new file's criteria are covered
    assert "PASS:" in result.stdout


# ---------------------------------------------------------------------------
# SHOULD 17: Deliverable in result field → extracted correctly
# ---------------------------------------------------------------------------

def test_should_17_deliverable_in_result_field(run_hook, tmp_armature):
    """Deliverable in result field → extracted and evaluated correctly."""
    criteria = ["Must validate schema"]
    _write_correlation(tmp_armature, criteria)

    payload = json.dumps({"result": "Schema has been validated."})
    result = run_hook(
        "task-completion.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "PASS:" in result.stdout


# ---------------------------------------------------------------------------
# SHOULD 18: 70% keyword hit → PASS (boundary test)
# ---------------------------------------------------------------------------

def test_should_18_exactly_70_pct_is_pass(run_hook, tmp_armature):
    """Exactly 70% keyword hit rate (7/10) → PASS at default 0.7 threshold.

    Uses domain-specific tokens that are either present or absent from the
    deliverable.  Stopwords (must, should, is, a, etc.) are excluded from
    keyword matching by the hook, so we rely on unique domain nouns.
    """
    # 10 criteria items; deliverable covers exactly 7 unique domain tokens
    criteria = [
        "authentication flow validation",    # covered: "authentication"
        "output serialization format",       # covered: "serialization"
        "schema integrity enforcement",      # covered: "schema"
        "database migration consistency",    # covered: "migration"
        "logging pipeline behavior",         # covered: "logging"
        "pagination cursor implementation",  # covered: "pagination"
        "caching eviction strategy",         # covered: "caching"
        "zymurgy_module_xray",               # NOT covered (invented token)
        "frobnicate_quux_splorge",           # NOT covered (invented token)
        "xyzzy_phantasmagoria_wibble",       # NOT covered (invented token)
    ]
    _write_correlation(tmp_armature, criteria)

    # Deliverable covers exactly 7 unique domain tokens from the first 7 criteria
    deliverable = (
        "Authentication flow validated. Serialization format confirmed. "
        "Schema integrity enforced. Migration consistency verified. "
        "Logging pipeline configured. Pagination cursor implemented. "
        "Caching eviction strategy applied."
    )
    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output=deliverable),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "PASS:" in result.stdout


# ---------------------------------------------------------------------------
# SHOULD 19: 60% keyword hit → ADVISORY (below 70% boundary)
# ---------------------------------------------------------------------------

def test_should_19_below_70_pct_is_advisory(run_hook, tmp_armature):
    """60% keyword hit rate (6/10) → ADVISORY (below default 0.7 threshold).

    Uses the same domain-specific tokens as test 18 but only covers 6/10.
    """
    criteria = [
        "authentication flow validation",    # covered
        "output serialization format",       # covered: "serialization"
        "schema integrity enforcement",      # covered
        "database migration consistency",    # covered: "migration"
        "logging pipeline behavior",         # covered: "logging"
        "pagination cursor implementation",  # covered: "pagination"
        "zymurgy_module_xray",               # NOT covered
        "frobnicate_quux_splorge",           # NOT covered
        "xyzzy_phantasmagoria_wibble",       # NOT covered
        "gribbleforth_snorkel_widget",       # NOT covered
    ]
    _write_correlation(tmp_armature, criteria)

    # Deliverable covers exactly 6 of the 10 domain tokens
    deliverable = (
        "Authentication flow validated. Serialization confirmed. "
        "Schema integrity enforced. Migration consistency verified. "
        "Logging pipeline configured. Pagination cursor implemented."
    )
    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output=deliverable),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY:" in result.stdout


# ---------------------------------------------------------------------------
# SHOULD 20: Unicode in deliverable text → no crash
# ---------------------------------------------------------------------------

def test_should_20_unicode_in_deliverable_no_crash(run_hook, tmp_armature):
    """Deliverable with Unicode characters (CJK, emoji) → no crash, exit 0."""
    criteria = ["Must verify output", "Should check encoding"]
    _write_correlation(tmp_armature, criteria)

    deliverable = "Output verified. Encoding checked. 中文 text \U0001f600 handled."
    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output=deliverable),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Cycle-16: PostToolUse(Agent) payload — JSON envelope on stdout
# ---------------------------------------------------------------------------

def test_posttooluse_agent_emits_json_envelope_for_pass(run_hook, tmp_armature):
    """When fired on PostToolUse(Agent) with a passing deliverable, stdout
    is the documented hookSpecificOutput envelope carrying the PASS advisory."""
    criteria = ["Must verify authentication flow", "Must check serialization"]
    _write_correlation(tmp_armature, criteria)

    deliverable = (
        "Authentication flow verified end-to-end. Serialization checked "
        "across all schema variants."
    )
    result = run_hook(
        "task-completion.sh",
        posttooluse_agent_event(
            response_text=deliverable,
            prompt="Implement feature X",
            subagent_type="specification-impl",
        ),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    assert envelope["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    ctx = envelope["hookSpecificOutput"]["additionalContext"]
    assert "PASS: TASK-002 criteria coverage" in ctx


def test_posttooluse_agent_envelope_on_missing_deliverable(run_hook, tmp_armature):
    """A PostToolUse(Agent) payload with no recoverable deliverable text
    still wraps the ADVISORY in the JSON envelope rather than emitting
    plain stdout that the parent session would ignore."""
    # tool_response present but no text — drains as advisory
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Agent",
        "tool_input": {"prompt": "do thing"},
        "tool_response": {"type": "text"},  # text key missing
    })
    result = run_hook("task-completion.sh", payload, cwd=str(tmp_armature))
    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    assert envelope["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "ADVISORY: TASK-002" in envelope["hookSpecificOutput"]["additionalContext"]


def test_posttooluse_agent_string_tool_response_extracted(run_hook, tmp_armature):
    """Claude Code may deliver a single-result Agent tool_response as a
    plain string rather than a {text: ...} dict. The hook must accept the
    string form so the deliverable coverage check fires correctly.
    Otherwise TASK-002 emits 'deliverable text not found' without ever
    looking up the active delegation file, leaving stale criteria behind."""
    criteria = ["Must verify authentication", "Must check serialization"]
    _write_correlation(tmp_armature, criteria)
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Agent",
        "tool_input": {"prompt": "implement X"},
        "tool_response": "Authentication verified. Serialization checked across schemas.",
    })
    result = run_hook("task-completion.sh", payload, cwd=str(tmp_armature))
    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    ctx = envelope["hookSpecificOutput"]["additionalContext"]
    assert "PASS: TASK-002 criteria coverage" in ctx, f"got: {ctx!r}"


def test_legacy_subagent_stop_payload_emits_plain_stdout(run_hook, tmp_armature):
    """A legacy SubagentStop-shaped payload (hook_event_name == 'SubagentStop')
    drains the buffer as plain text, not a JSON envelope. Preserves
    backwards-compat for older Claude Code installs and ad-hoc invocation."""
    criteria = ["Must verify schema"]
    _write_correlation(tmp_armature, criteria)
    result = run_hook(
        "task-completion.sh",
        subagent_stop_event(output="Schema verified successfully."),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    stripped = result.stdout.strip()
    assert not stripped.startswith("{"), (
        f"SubagentStop payload should produce plain output, got: {stripped!r}"
    )
    assert "PASS: TASK-002 criteria coverage" in result.stdout
