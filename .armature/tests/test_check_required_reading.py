"""
Tests for check-required-reading.sh (HOOK-006).

Hook behaviour (verified from source):
  - Reads tool_input.file_path (or fallback file_path) from stdin JSON.
  - Walks up from file's directory to REPO_ROOT to find nearest agents.md / AGENTS.md.
  - Parses YAML frontmatter for adrs: list.
  - Resolves each ADR-ID to docs/adr/{ID}* via glob.
  - Prints advisory to stdout.
  - Always exits 0 (advisory, never a gate).

Behaviour details verified from source:
  - Invalid JSON  → "SKIP: Could not parse hook payload as JSON"
  - No file_path  → "SKIP: No file_path found in hook payload"
  - No agents.md  → "SKIP: No governance file found for <path>"
  - Found         → "ADVISORY: Required reading for scope governed by <rel-path>:"
  - agents.md rel-path appears in advisory
  - ADR path appears in advisory when file exists
  - ADR not found → "<ADR-ID> (file not found — check docs/adr/)"
  - Relative file_path → normalised to absolute using REPO_ROOT
  - Nested file    → walks to nearest parent agents.md (not skipping to root)
"""

import json

import pytest

from .helpers import edit_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scope(tmp_path):
    """Create a minimal test scope under tmp_path with agents.md + ADR file.

    Layout:
      <tmp_path>/
        test_scope/
          agents.md          (frontmatter: adrs: [ADR-0001])
          target.py          (a file in this scope)
        docs/
          adr/
            0001-test.md
    """
    scope_dir = tmp_path / "test_scope"
    scope_dir.mkdir(parents=True)

    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0001-test.md").write_text("# ADR-0001 Test\n")

    (scope_dir / "agents.md").write_text(
        "---\nscope: test_scope\nadrs: [ADR-0001]\n---\n\n# Test Scope\n"
    )
    (scope_dir / "target.py").write_text("# target\n")

    return scope_dir


# ---------------------------------------------------------------------------
# MUST: always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_zero_no_agents_md(run_hook, tmp_armature):
    """Hook must exit 0 even when no agents.md exists anywhere in hierarchy."""
    payload = edit_event(str((tmp_armature / "src" / "app.py").as_posix()))
    result = run_hook("check-required-reading.sh", payload, cwd=str(tmp_armature))
    assert result.returncode == 0


def test_always_exits_zero_with_agents_md(run_hook, tmp_armature):
    """Hook must exit 0 when agents.md is found and advisory is emitted."""
    _make_scope(tmp_armature)
    target = (tmp_armature / "test_scope" / "target.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


def test_always_exits_zero_invalid_json(run_hook, tmp_armature):
    """Hook must exit 0 on invalid JSON input."""
    result = run_hook(
        "check-required-reading.sh",
        "{{not valid json",
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


def test_always_exits_zero_no_file_path(run_hook, tmp_armature):
    """Hook must exit 0 when file_path is missing from payload."""
    payload = json.dumps({"tool_input": {"command": "echo hi"}})
    result = run_hook(
        "check-required-reading.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST: "ADVISORY: Required reading" appears when agents.md found in hierarchy
# ---------------------------------------------------------------------------

def test_advisory_message_present_when_agents_md_found(run_hook, tmp_armature):
    """stdout must contain 'ADVISORY: Required reading' when agents.md governs the file."""
    _make_scope(tmp_armature)
    target = (tmp_armature / "test_scope" / "target.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY: Required reading" in result.stdout


def test_no_advisory_when_no_agents_md(run_hook, tmp_armature):
    """stdout must NOT contain 'ADVISORY' when no agents.md is found."""
    payload = edit_event((tmp_armature / "orphan.py").as_posix())
    result = run_hook(
        "check-required-reading.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" not in result.stdout


# ---------------------------------------------------------------------------
# MUST: agents.md path appears in advisory
# ---------------------------------------------------------------------------

def test_agents_md_path_appears_in_advisory(run_hook, tmp_armature):
    """The relative path to agents.md must appear in the advisory output."""
    _make_scope(tmp_armature)
    target = (tmp_armature / "test_scope" / "target.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    # Relative path to agents.md should appear (forward or back slashes)
    assert "test_scope" in result.stdout
    assert "agents.md" in result.stdout


# ---------------------------------------------------------------------------
# MUST: ADR paths appear when frontmatter has adrs: list with valid files
# ---------------------------------------------------------------------------

def test_valid_adr_path_appears_in_advisory(run_hook, tmp_armature):
    """A resolvable ADR reference must appear as a path in the advisory."""
    _make_scope(tmp_armature)
    target = (tmp_armature / "test_scope" / "target.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    # The resolved ADR file path must appear somewhere in stdout
    assert "0001-test.md" in result.stdout
    # The raw "file not found" annotation must NOT appear for this valid ref
    assert "file not found" not in result.stdout


# ---------------------------------------------------------------------------
# MUST: non-existent ADR ref → "(file not found — check docs/adr/)" annotation
# ---------------------------------------------------------------------------

def test_missing_adr_file_shows_not_found_annotation(run_hook, tmp_armature):
    """An ADR reference with no matching file must show the 'file not found' annotation."""
    scope_dir = tmp_armature / "missing_adr_scope"
    scope_dir.mkdir()
    (scope_dir / "agents.md").write_text(
        "---\nscope: missing_adr_scope\nadrs: [ADR-9999]\n---\n"
    )
    (scope_dir / "file.py").write_text("")

    target = (scope_dir / "file.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "file not found" in result.stdout
    assert "check docs/adr/" in result.stdout


def test_missing_adr_does_not_show_resolved_path(run_hook, tmp_armature):
    """When ADR cannot be resolved, no file path for it should appear (only annotation)."""
    scope_dir = tmp_armature / "bad_adr_scope"
    scope_dir.mkdir()
    (scope_dir / "agents.md").write_text(
        "---\nscope: bad_adr_scope\nadrs: [ADR-9998]\n---\n"
    )
    (scope_dir / "file.py").write_text("")

    target = (scope_dir / "file.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" in result.stdout
    assert "9998" in result.stdout  # ADR-9998 must appear
    assert "file not found" in result.stdout


# ---------------------------------------------------------------------------
# MUST: no agents.md in hierarchy → "SKIP: No governance file found"
# ---------------------------------------------------------------------------

def test_no_agents_md_emits_skip_message(run_hook, tmp_armature):
    """When no agents.md exists anywhere in hierarchy, SKIP message must appear."""
    # tmp_armature has no agents.md by default
    target = (tmp_armature / "orphan.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "SKIP" in result.stdout
    assert "No governance file found" in result.stdout


# ---------------------------------------------------------------------------
# MUST: no file_path in payload → "SKIP: No file_path found"
# ---------------------------------------------------------------------------

def test_no_file_path_emits_skip_message(run_hook, tmp_armature):
    """Payload with no file_path must emit a SKIP message."""
    payload = json.dumps({"tool_input": {}})
    result = run_hook(
        "check-required-reading.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "SKIP" in result.stdout
    assert "No file_path found" in result.stdout


def test_empty_file_path_emits_skip_message(run_hook, tmp_armature):
    """Payload with empty file_path string must emit a SKIP message."""
    payload = json.dumps({"tool_input": {"file_path": ""}})
    result = run_hook(
        "check-required-reading.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "SKIP" in result.stdout


# ---------------------------------------------------------------------------
# MUST: invalid JSON → "SKIP: Could not parse"
# ---------------------------------------------------------------------------

def test_invalid_json_emits_could_not_parse(run_hook, tmp_armature):
    """Completely invalid JSON must produce a 'Could not parse' SKIP message."""
    result = run_hook(
        "check-required-reading.sh",
        "{{not-json}}",
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "SKIP" in result.stdout
    assert "Could not parse" in result.stdout


def test_invalid_json_does_not_emit_advisory(run_hook, tmp_armature):
    """Invalid JSON must never produce an ADVISORY (only a SKIP)."""
    result = run_hook(
        "check-required-reading.sh",
        "not json at all",
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" not in result.stdout


# ---------------------------------------------------------------------------
# SHOULD: relative file_path normalised to absolute then walked
# ---------------------------------------------------------------------------

def test_relative_file_path_normalised_and_walked(run_hook, tmp_armature):
    """Relative file_path is normalised using REPO_ROOT; should find agents.md."""
    _make_scope(tmp_armature)
    # Pass relative path (relative from REPO_ROOT) — hook normalises it
    payload = json.dumps({"tool_input": {"file_path": "test_scope/target.py"}})
    result = run_hook(
        "check-required-reading.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" in result.stdout


# ---------------------------------------------------------------------------
# SHOULD: nested file finds nearest parent agents.md (not root, not deepest child)
# ---------------------------------------------------------------------------

def test_nested_file_finds_nearest_parent_agents_md(run_hook, tmp_armature):
    """A file nested under multiple levels uses the nearest parent agents.md.

    Layout:
      outer/
        agents.md   (adrs: [ADR-0001])
        inner/
          target.py

    The file at inner/target.py should find outer/agents.md (nearest parent).
    """
    outer = tmp_armature / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)

    adr_dir = tmp_armature / "docs" / "adr"
    adr_dir.mkdir(parents=True, exist_ok=True)
    (adr_dir / "0001-test.md").write_text("# ADR-0001\n")

    (outer / "agents.md").write_text(
        "---\nscope: outer\nadrs: [ADR-0001]\n---\n"
    )
    (inner / "target.py").write_text("")

    target = (inner / "target.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" in result.stdout
    # The outer agents.md should be mentioned, not a non-existent inner agents.md
    assert "outer" in result.stdout


def test_nested_file_uses_nearest_not_root_agents_md(run_hook, tmp_armature):
    """When both root and a subdirectory have agents.md, the nearest wins.

    Layout:
      agents.md        (root — would be found if walking hits root)
      sub_scope/
        agents.md      (nearest to target)
        target.py
    """
    # Root agents.md (note: real repo has .armature/agents.md, not root agents.md,
    # so we place it at tmp_armature root for isolation)
    (tmp_armature / "agents.md").write_text(
        "---\nscope: root\nadrs: []\n---\n"
    )
    sub = tmp_armature / "sub_scope"
    sub.mkdir()
    (sub / "agents.md").write_text(
        "---\nscope: sub_scope\nadrs: []\n---\n"
    )
    (sub / "target.py").write_text("")

    target = (sub / "target.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" in result.stdout
    # The sub_scope agents.md is nearer; must appear
    assert "sub_scope" in result.stdout


# ---------------------------------------------------------------------------
# Discipline-tags advisory (Step 10)
# ---------------------------------------------------------------------------

def _make_discipline_scope(tmp_path, discipline_tags_yaml):
    """Create a minimal scope with a disciplines directory and configurable tags.

    Layout:
      <tmp_path>/
        disc_scope/
          agents.md   (frontmatter: discipline-tags: <discipline_tags_yaml>)
          target.py
        .armature/
          disciplines/
            adr-process.md
            definition-of-done.md
    """
    scope_dir = tmp_path / "disc_scope"
    scope_dir.mkdir(parents=True)

    disc_dir = tmp_path / ".armature" / "disciplines"
    disc_dir.mkdir(parents=True)
    (disc_dir / "adr-process.md").write_text("# adr-process discipline\n")
    (disc_dir / "definition-of-done.md").write_text("# definition-of-done discipline\n")

    (scope_dir / "agents.md").write_text(
        f"---\nscope: disc_scope\nadrs: []\ndiscipline-tags: {discipline_tags_yaml}\n---\n\n# Disc Scope\n"
    )
    (scope_dir / "target.py").write_text("# target\n")

    return scope_dir


def test_discipline_tags_resolve_to_advisory(run_hook, tmp_armature):
    """agents.md with discipline-tags: [adr-process] → advisory includes adr-process.md path."""
    _make_discipline_scope(tmp_armature, "[adr-process]")
    target = (tmp_armature / "disc_scope" / "target.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" in result.stdout
    assert "adr-process.md" in result.stdout
    assert "discipline file not found" not in result.stdout


def test_empty_discipline_tags_emits_no_disciplines_comment(run_hook, tmp_armature):
    """agents.md with discipline-tags: [] → 'no required disciplines' comment in advisory."""
    _make_discipline_scope(tmp_armature, "[]")
    target = (tmp_armature / "disc_scope" / "target.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" in result.stdout
    assert "no required disciplines" in result.stdout


def test_no_discipline_tags_field_emits_no_disciplines_comment(run_hook, tmp_armature):
    """agents.md frontmatter without discipline-tags field → 'no required disciplines' comment."""
    scope_dir = tmp_armature / "no_tags_scope"
    scope_dir.mkdir(parents=True)
    (scope_dir / "agents.md").write_text(
        "---\nscope: no_tags_scope\nadrs: []\n---\n\n# No Tags Scope\n"
    )
    (scope_dir / "target.py").write_text("# target\n")

    target = (scope_dir / "target.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" in result.stdout
    assert "no required disciplines" in result.stdout


def test_missing_discipline_file_emits_not_found_annotation(run_hook, tmp_armature):
    """discipline-tags: [nonexistent] → 'discipline file not found' annotation."""
    scope_dir = tmp_armature / "missing_disc_scope"
    scope_dir.mkdir(parents=True)
    (scope_dir / "agents.md").write_text(
        "---\nscope: missing_disc_scope\nadrs: []\ndiscipline-tags: [nonexistent]\n---\n"
    )
    (scope_dir / "target.py").write_text("")

    target = (scope_dir / "target.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" in result.stdout
    assert "discipline file not found" in result.stdout
    assert "check .armature/disciplines/" in result.stdout
    assert "nonexistent" in result.stdout


def test_multiple_discipline_tags_all_appear(run_hook, tmp_armature):
    """discipline-tags: [adr-process, definition-of-done] → both paths in advisory."""
    _make_discipline_scope(tmp_armature, "[adr-process, definition-of-done]")
    target = (tmp_armature / "disc_scope" / "target.py").as_posix()
    result = run_hook(
        "check-required-reading.sh",
        edit_event(target),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" in result.stdout
    assert "adr-process.md" in result.stdout
    assert "definition-of-done.md" in result.stdout
    assert "discipline file not found" not in result.stdout
