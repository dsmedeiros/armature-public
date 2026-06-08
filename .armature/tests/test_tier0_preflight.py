"""
Tests for tier0-preflight.sh (TIER0-001).

Hook behaviour (verified from source):
  - Reads tool_input.file_path from stdin JSON.
  - Rejects NUL bytes in raw JSON stdin → exit 2 + "BLOCK [TIER0-001]".
  - Normalizes to absolute path (prepends REPO_ROOT for relative paths).
  - Hotfix bypass: if .armature/session/phase contains "Hotfix" → advisory + exit 0.
  - Exempt paths (always exit 0, even if tier-0 files are missing):
      DOMAIN.md, PROJECT.md, .armature/*, .claude/*, docs/adr/*
  - Checks $REPO_ROOT/DOMAIN.md and $REPO_ROOT/PROJECT.md exist.
  - If either/both missing → exit 2 + "BLOCK [TIER0-001]" on stderr.
  - Fail-open conditions (exit 0): not a git repo, Python unavailable,
    invalid JSON, missing/empty file_path.
  - Control characters in file_path → exit 2 + "BLOCK [TIER0-001]" (MEDIUM-1 fix).
  - JSON null for file_path → exit 0 (treated as absent; LOW-1 fix).

All filesystem tests use tmp_armature so the real repo is never mutated.
"""

import json
import os
import shutil
import subprocess

import pytest

from .helpers import edit_event


# ---------------------------------------------------------------------------
# MUST: tier-0 files missing → exit 2
# ---------------------------------------------------------------------------

def test_block_domain_md_missing(run_hook, tmp_armature):
    """DOMAIN.md absent, source edit → exit 2 with BLOCK and TIER0-001."""
    # Only PROJECT.md present; DOMAIN.md absent
    (tmp_armature / "PROJECT.md").write_text("# Project\n")

    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TIER0-001" in result.stderr


def test_block_project_md_missing(run_hook, tmp_armature):
    """PROJECT.md absent, source edit → exit 2."""
    # Only DOMAIN.md present; PROJECT.md absent
    (tmp_armature / "DOMAIN.md").write_text("# Domain\n")

    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


def test_block_both_missing(run_hook, tmp_armature):
    """Both DOMAIN.md and PROJECT.md absent → exit 2."""
    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


def test_allow_both_present(run_hook, tmp_armature):
    """Both DOMAIN.md and PROJECT.md present, source edit → exit 0."""
    (tmp_armature / "DOMAIN.md").write_text("# Domain\n")
    (tmp_armature / "PROJECT.md").write_text("# Project\n")

    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


def test_allow_editing_domain_md_itself(run_hook, tmp_armature):
    """Even if PROJECT.md is missing, editing DOMAIN.md itself → exit 0 (exempt)."""
    # Neither tier-0 file exists; DOMAIN.md is the target — exempt from its own gate
    result = run_hook(
        "tier0-preflight.sh",
        edit_event("DOMAIN.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


def test_allow_editing_project_md_itself(run_hook, tmp_armature):
    """Even if DOMAIN.md is missing, editing PROJECT.md itself → exit 0 (exempt)."""
    result = run_hook(
        "tier0-preflight.sh",
        edit_event("PROJECT.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


def test_allow_armature_hooks_path(run_hook, tmp_armature):
    """Editing .armature/hooks/foo.sh → exit 0 (exempt governance path)."""
    result = run_hook(
        "tier0-preflight.sh",
        edit_event(".armature/hooks/foo.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


def test_allow_claude_agents_path(run_hook, tmp_armature):
    """Editing .claude/agents/foo.md → exit 0 (exempt governance path)."""
    result = run_hook(
        "tier0-preflight.sh",
        edit_event(".claude/agents/foo.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


def test_allow_docs_adr_path(run_hook, tmp_armature):
    """Editing docs/adr/0001-foo.md → exit 0 (exempt governance path)."""
    result = run_hook(
        "tier0-preflight.sh",
        edit_event("docs/adr/0001-foo.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


def test_fail_open_invalid_json(run_hook, tmp_armature):
    """Invalid JSON stdin → exit 0 (fail-open, cannot parse file_path)."""
    result = run_hook(
        "tier0-preflight.sh",
        "{{not json at all",
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


def test_fail_open_no_file_path(run_hook, tmp_armature):
    """JSON missing file_path → exit 0 (fail-open)."""
    payload = json.dumps({"tool_input": {"command": "echo hi"}})
    result = run_hook(
        "tier0-preflight.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


def test_hotfix_bypass(run_hook, tmp_armature):
    """Hotfix phase active → exit 0 + 'ADVISORY' on stderr, even with missing tier-0 files."""
    # Write "Hotfix" to phase file (no tier-0 files present)
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.write_text("Hotfix")

    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" in result.stderr


# ---------------------------------------------------------------------------
# SHOULD: additional coverage
# ---------------------------------------------------------------------------

def test_relative_path_normalized(run_hook, tmp_armature):
    """Relative path provided → resolved to absolute and blocked correctly."""
    # No tier-0 files; use a bare relative path (no leading slash/dot)
    result = run_hook(
        "tier0-preflight.sh",
        edit_event("app/utils.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


def test_nested_governance_exempt(run_hook, tmp_armature):
    """Editing .armature/personas/foo.md → exit 0 (nested .armature/ path is exempt)."""
    result = run_hook(
        "tier0-preflight.sh",
        edit_event(".armature/personas/foo.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


def test_block_message_names_missing_files(run_hook, tmp_armature):
    """BLOCK message identifies which file(s) are missing."""
    # Neither tier-0 file exists; message should name them
    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/app.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    # At least one of the missing file names appears in the error message
    assert "DOMAIN.md" in result.stderr or "PROJECT.md" in result.stderr


def test_block_message_references_tier0_001(run_hook, tmp_armature):
    """BLOCK message contains the invariant ID 'TIER0-001'."""
    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/app.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "TIER0-001" in result.stderr


def test_allow_only_domain_present(run_hook, tmp_armature):
    """DOMAIN.md present but PROJECT.md missing → exit 2 (both are required)."""
    (tmp_armature / "DOMAIN.md").write_text("# Domain\n")
    # PROJECT.md intentionally absent

    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


def test_allow_only_project_present(run_hook, tmp_armature):
    """PROJECT.md present but DOMAIN.md missing → exit 2 (both are required)."""
    (tmp_armature / "PROJECT.md").write_text("# Project\n")
    # DOMAIN.md intentionally absent

    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


# ---------------------------------------------------------------------------
# Cycle-2 fixes: MEDIUM-1 (control chars) and LOW-1 (JSON null)
# ---------------------------------------------------------------------------

def test_block_control_chars_in_file_path(run_hook, tmp_armature):
    """file_path with embedded newline (JSON \\n escape) → exit 2 with BLOCK.

    A JSON string containing a \\n escape decodes to a real newline character
    (ord < 32).  The hook must reject this before the exempt-path check fires,
    so a payload like '.armature/foo\\nsrc/main.py' cannot bypass the gate by
    prefix-matching '.armature/'.
    """
    # The JSON string ".armature/foo\nsrc/main.py" contains a real newline after decode.
    payload = '{"tool_input":{"file_path":".armature/foo\\nsrc/main.py"}}'
    result = run_hook(
        "tier0-preflight.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TIER0-001" in result.stderr
    assert "control characters" in result.stderr


def test_fail_open_null_file_path(run_hook, tmp_armature):
    """JSON null for file_path → exit 0 (treated as absent/empty; fail-open).

    When file_path is JSON null the Python extractor used to print the string
    'None', which flowed through as a fake path and produced a confusing BLOCK.
    The fix treats null identically to a missing key.
    """
    payload = '{"tool_input":{"file_path":null}}'
    result = run_hook(
        "tier0-preflight.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


def test_strict_hotfix_capitalization(run_hook, tmp_armature):
    """phase file contains 'hotfix' (lowercase) → no bypass, normal block fires.

    The bypass requires exactly the string 'Hotfix'.  Any other capitalisation
    must not short-circuit the gate.
    """
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.write_text("hotfix")
    # No tier-0 files present → should BLOCK, not bypass

    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


def test_block_when_domain_is_directory(run_hook, tmp_armature):
    """DOMAIN.md is a directory, not a file → bash -f returns false → exit 2.

    The hook uses [ -f ] for existence checks.  A directory at DOMAIN.md must
    not satisfy the check.
    """
    (tmp_armature / "DOMAIN.md").mkdir()
    (tmp_armature / "PROJECT.md").write_text("# Project\n")

    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


def test_block_when_domain_is_dangling_symlink(run_hook, tmp_armature):
    """DOMAIN.md is a symlink pointing to a non-existent target → exit 2.

    bash's [ -f ] follows symlinks: a dangling symlink is not a regular file,
    so the tier-0 check must treat it as missing.
    """
    nonexistent_target = tmp_armature / "nonexistent_domain_target.md"
    link_path = tmp_armature / "DOMAIN.md"
    os.symlink(str(nonexistent_target), str(link_path))
    (tmp_armature / "PROJECT.md").write_text("# Project\n")

    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


# ---------------------------------------------------------------------------
# Test 24 (cycle-2 / m3-cp3 HIGH fix): NUL byte in phase file must not bypass
# ---------------------------------------------------------------------------

def test_block_nul_byte_phase_file_tier0_preflight(run_hook, tmp_armature):
    """Phase file containing 'Hot\\x00fix' must NOT trigger Hotfix bypass.

    bash command-substitution strips NUL bytes, so 'Hot\\x00fix' would be
    captured as 'Hotfix' and bypass tier0-preflight.  The cycle-2 Python-based
    phase reader rejects files containing control bytes, so the phase is treated
    as unknown → no bypass → the tier-0 gate fires normally.

    With no tier-0 files present and a non-exempt source file, exit 2 (BLOCK)
    must be returned — confirming the gate was NOT bypassed.
    """
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.parent.mkdir(parents=True, exist_ok=True)
    phase_file.write_bytes(b"Hot\x00fix")

    # No DOMAIN.md / PROJECT.md, source file → tier-0 gate fires
    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TIER0-001" in result.stderr
    assert "ADVISORY" not in result.stderr


# ---------------------------------------------------------------------------
# Test 25 (cycle-3 / m3-cp3 MEDIUM-1 fix): Unicode NBSP in phase file must not bypass
# ---------------------------------------------------------------------------

def test_block_unicode_nbsp_phase_file_tier0_preflight(run_hook, tmp_armature):
    """Phase file containing NBSP+Hotfix+NBSP must NOT trigger Hotfix bypass.

    Python's str.strip() (without arguments) strips Unicode whitespace including
    U+00A0 NO-BREAK SPACE (\\xc2\\xa0 in UTF-8).  The cycle-2 reader used .strip()
    which allowed '\\xc2\\xa0Hotfix\\xc2\\xa0' to decode to 'Hotfix' and bypass.
    The cycle-3 fix uses .strip(' \\t\\n\\r') which only strips ASCII whitespace,
    so the NBSP-wrapped value is not in VALID → treated as unknown phase →
    no bypass occurs → tier-0 gate fires normally.

    With no tier-0 files present and a non-exempt source file, exit 2 (BLOCK)
    must be returned — confirming the gate was NOT bypassed.
    """
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.parent.mkdir(parents=True, exist_ok=True)
    # NBSP (U+00A0) = \\xc2\\xa0 in UTF-8; wrap Hotfix on both sides
    phase_file.write_bytes(b"\xc2\xa0Hotfix\xc2\xa0")

    # No DOMAIN.md / PROJECT.md, source file → tier-0 gate fires
    result = run_hook(
        "tier0-preflight.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TIER0-001" in result.stderr
    assert "ADVISORY" not in result.stderr


# ===========================================================================
# LOW-2 fix (m3-cp4 polish): NUL byte in raw JSON stdin payload → exit 2
# ===========================================================================

# ---------------------------------------------------------------------------
# Test 26: LOW-2 — NUL byte in raw JSON stdin → exit 2 BLOCK
# ---------------------------------------------------------------------------

def test_block_nul_byte_in_json_payload(repo_root, tmp_armature):
    """JSON stdin payload with a literal NUL byte (0x00) → exit 2 + BLOCK.

    bash command substitution ($(cat)) silently strips NUL bytes from the
    byte stream.  Under the old pattern, a payload of
      {"tool_input":{"file_path":"foo<NUL>bar"}}
    was captured by bash as
      {"tool_input":{"file_path":"foobar"}}
    — the NUL was stripped and 'foobar' passed the control-character check.

    The LOW-2 fix replaces the bash payload capture with Python
    sys.stdin.buffer.read(), which preserves NUL bytes.  The hook now exits 2
    with BLOCK [TIER0-001] when any NUL byte appears in the raw JSON stream.

    This test sends binary stdin directly (bypassing run_hook's text=True
    limitation) using subprocess.run with input=bytes.
    """
    bash_bin = shutil.which("bash")
    if bash_bin is None:
        pytest.skip("bash not available")

    hook_path = repo_root / ".armature" / "hooks" / "tier0-preflight.sh"
    # Payload: valid JSON wrapper with a literal NUL byte embedded in file_path
    payload = b'{"tool_input":{"file_path":"foo\x00bar"}}'

    result = subprocess.run(
        [bash_bin, str(hook_path)],
        input=payload,
        capture_output=True,
        cwd=str(tmp_armature),
        timeout=10,
    )
    assert result.returncode == 2
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "BLOCK" in stderr
    assert "TIER0-001" in stderr
