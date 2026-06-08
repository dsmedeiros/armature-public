"""
Tests for mark-dirty.sh (HOOK-003).

Hook behaviour (verified from source):
  - Reads tool_input.file_path from stdin JSON.
  - Strips REPO_ROOT prefix (+ leading slash) to produce a relative path.
  - Paths under .armature/, .claude/, or docs/ → governance; no marker; exit 0.
  - All other paths → non-governance; touches .armature/.code-dirty; exit 0.
  - No stdin / empty stdin / missing file_path field → exit 0 (fail-open).
  - Invalid JSON → sed fallback; if still no path → exit 0 (fail-open).
  - Marker path: ${ARMATURE_DIR}/.code-dirty  (inside the tmp repo .armature/).

All filesystem tests use tmp_armature so the real repo is never mutated.
"""

import json

import pytest

from .helpers import edit_event


# ---------------------------------------------------------------------------
# MUST: non-governance path creates marker
# ---------------------------------------------------------------------------

def test_non_governance_path_creates_marker(run_hook, tmp_armature):
    """A plain application file should cause .code-dirty to be created."""
    result = run_hook(
        "mark-dirty.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert (tmp_armature / ".armature" / ".code-dirty").exists()


def test_non_governance_path_at_root_creates_marker(run_hook, tmp_armature):
    """A file at the repo root (not under any governance prefix) creates marker."""
    result = run_hook(
        "mark-dirty.sh",
        edit_event("README.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert (tmp_armature / ".armature" / ".code-dirty").exists()


def test_nested_non_governance_path_creates_marker(run_hook, tmp_armature):
    """A deeply nested application file creates marker."""
    result = run_hook(
        "mark-dirty.sh",
        edit_event("app/api/v1/routes.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert (tmp_armature / ".armature" / ".code-dirty").exists()


# ---------------------------------------------------------------------------
# MUST: governance paths do NOT create marker
# ---------------------------------------------------------------------------

def test_armature_prefix_does_not_create_marker(run_hook, tmp_armature):
    """Files under .armature/ are governance — no marker created."""
    result = run_hook(
        "mark-dirty.sh",
        edit_event(".armature/hooks/post-stop.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert not (tmp_armature / ".armature" / ".code-dirty").exists()


def test_claude_prefix_does_not_create_marker(run_hook, tmp_armature):
    """Files under .claude/ are governance — no marker created."""
    result = run_hook(
        "mark-dirty.sh",
        edit_event(".claude/agents/specification-impl.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert not (tmp_armature / ".armature" / ".code-dirty").exists()


def test_docs_prefix_does_not_create_marker(run_hook, tmp_armature):
    """Files under docs/ are governance — no marker created."""
    result = run_hook(
        "mark-dirty.sh",
        edit_event("docs/adr/ADR-0001.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert not (tmp_armature / ".armature" / ".code-dirty").exists()


def test_docs_at_root_level_does_not_create_marker(run_hook, tmp_armature):
    """A file directly in docs/ (not nested) is still governance."""
    result = run_hook(
        "mark-dirty.sh",
        edit_event("docs/overview.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert not (tmp_armature / ".armature" / ".code-dirty").exists()


# ---------------------------------------------------------------------------
# MUST: root-level governance adapter files do NOT create marker (cycle-6)
# ---------------------------------------------------------------------------

def test_claude_md_root_does_not_create_marker(run_hook, tmp_armature):
    """CLAUDE.md at repo root is a governance adapter — no marker created."""
    result = run_hook(
        "mark-dirty.sh",
        edit_event("CLAUDE.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert not (tmp_armature / ".armature" / ".code-dirty").exists()


def test_codex_md_root_does_not_create_marker(run_hook, tmp_armature):
    """CODEX.md at repo root is a governance adapter — no marker created."""
    result = run_hook(
        "mark-dirty.sh",
        edit_event("CODEX.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert not (tmp_armature / ".armature" / ".code-dirty").exists()


def test_agents_md_root_does_not_create_marker(run_hook, tmp_armature):
    """AGENTS.md at repo root is a governance adapter — no marker created."""
    result = run_hook(
        "mark-dirty.sh",
        edit_event("AGENTS.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert not (tmp_armature / ".armature" / ".code-dirty").exists()


def test_armature_md_root_does_not_create_marker(run_hook, tmp_armature):
    """ARMATURE.md at repo root is a governance spec — no marker created."""
    result = run_hook(
        "mark-dirty.sh",
        edit_event("ARMATURE.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert not (tmp_armature / ".armature" / ".code-dirty").exists()


def test_normal_app_file_creates_marker(run_hook, tmp_armature):
    """A normal application source file (src/foo.py) DOES trigger the marker."""
    result = run_hook(
        "mark-dirty.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert (tmp_armature / ".armature" / ".code-dirty").exists()


# ---------------------------------------------------------------------------
# MUST: missing / empty stdin → exit 0 (fail-open, no marker)
# ---------------------------------------------------------------------------

def test_empty_stdin_exits_zero(run_hook, tmp_armature):
    """Empty stdin must not crash the hook and must exit 0."""
    result = run_hook(
        "mark-dirty.sh",
        "",
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert not (tmp_armature / ".armature" / ".code-dirty").exists()


def test_missing_file_path_field_exits_zero(run_hook, tmp_armature):
    """JSON without a file_path field must exit 0 and not create marker."""
    payload = json.dumps({"tool_input": {"command": "echo hi"}})
    result = run_hook(
        "mark-dirty.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert not (tmp_armature / ".armature" / ".code-dirty").exists()


def test_empty_file_path_exits_zero(run_hook, tmp_armature):
    """JSON with an empty file_path string must exit 0 and not create marker."""
    payload = json.dumps({"tool_input": {"file_path": ""}})
    result = run_hook(
        "mark-dirty.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert not (tmp_armature / ".armature" / ".code-dirty").exists()


# ---------------------------------------------------------------------------
# SHOULD: absolute path with REPO_ROOT prefix → stripped, classified correctly
# ---------------------------------------------------------------------------

def test_absolute_governance_path_stripped_and_classified(run_hook, tmp_armature):
    """Absolute path under REPO_ROOT/.armature/ should be stripped and treated as governance.

    Use .as_posix() so bash on Windows receives forward-slash paths that match
    the REPO_ROOT produced by git rev-parse --show-toplevel inside the hook.
    """
    abs_path = (tmp_armature / ".armature" / "ARMATURE.md").as_posix()
    result = run_hook(
        "mark-dirty.sh",
        edit_event(abs_path),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert not (tmp_armature / ".armature" / ".code-dirty").exists()


def test_absolute_non_governance_path_stripped_and_classified(run_hook, tmp_armature):
    """Absolute path under REPO_ROOT/src/ should be stripped and treated as non-governance.

    Use .as_posix() so bash on Windows receives forward-slash paths that match
    the REPO_ROOT produced by git rev-parse --show-toplevel inside the hook.
    """
    abs_path = (tmp_armature / "src" / "app.py").as_posix()
    result = run_hook(
        "mark-dirty.sh",
        edit_event(abs_path),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert (tmp_armature / ".armature" / ".code-dirty").exists()


# ---------------------------------------------------------------------------
# SHOULD: invalid JSON → fail-open exit 0, no marker
# ---------------------------------------------------------------------------

def test_invalid_json_exits_zero(run_hook, tmp_armature):
    """Completely invalid JSON must fail open (exit 0) and not create marker."""
    result = run_hook(
        "mark-dirty.sh",
        "not json at all {{{",
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    # The sed fallback may or may not extract something; with no valid "file_path"
    # key-value pair in this garbage input, no marker should appear.
    # (The sed pattern looks for "file_path": "value" — not present here.)
    assert not (tmp_armature / ".armature" / ".code-dirty").exists()
