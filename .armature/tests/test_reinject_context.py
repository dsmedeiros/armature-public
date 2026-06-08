"""
Tests for reinject-context.sh (HOOK-005).

Hook behaviour (verified from source):
  - Does NOT read stdin.
  - Always exits 0 (informational hook, never a gate).
  - Stdout always contains four section headers:
      ## Session State
      ## Recent Journal Entries
      ## Recent Commits
      ## Warnings
  - Session State: emits state.md contents or HTML comment "not found, skipping".
  - Recent Journal Entries: emits last 10 ### sections, or comment if missing,
    or "_No journal entries found._" if file exists but has no ### headers.
  - Recent Commits: git log --oneline -5.
  - Warnings:
      .code-dirty present  → "WARNING: Application code has been modified..."
      .code-dirty absent   → "_No warnings._"

Behaviour mismatch vs. plan §Step 5:
  The plan says missing state.md/journal.md → 'not found, skipping' (plain text).
  The actual hook emits an HTML comment: <!-- <full_path> not found, skipping -->
  Tests check what the hook actually does.
"""

import pytest


# ---------------------------------------------------------------------------
# MUST: always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_zero_real_repo(run_hook):
    """Hook must always exit 0 against the real repo (which has all files)."""
    result = run_hook("reinject-context.sh", "")
    assert result.returncode == 0


def test_always_exits_zero_with_code_dirty(run_hook, tmp_armature):
    """Hook must exit 0 even when .code-dirty is present."""
    (tmp_armature / ".armature" / ".code-dirty").touch()
    result = run_hook("reinject-context.sh", "", cwd=str(tmp_armature))
    assert result.returncode == 0


def test_always_exits_zero_missing_files(run_hook, tmp_armature):
    """Hook must exit 0 even when state.md and journal.md are absent."""
    # tmp_armature has .armature/session/ but no state.md or journal.md by default
    result = run_hook("reinject-context.sh", "", cwd=str(tmp_armature))
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST: stdout always contains all four section headers
# ---------------------------------------------------------------------------

def test_stdout_contains_session_state_header(run_hook):
    result = run_hook("reinject-context.sh", "")
    assert "## Session State" in result.stdout


def test_stdout_contains_recent_journal_entries_header(run_hook):
    result = run_hook("reinject-context.sh", "")
    assert "## Recent Journal Entries" in result.stdout


def test_stdout_contains_recent_commits_header(run_hook):
    result = run_hook("reinject-context.sh", "")
    assert "## Recent Commits" in result.stdout


def test_stdout_contains_warnings_header(run_hook):
    result = run_hook("reinject-context.sh", "")
    assert "## Warnings" in result.stdout


# ---------------------------------------------------------------------------
# MUST: .code-dirty present → "Application code has been modified" warning
# ---------------------------------------------------------------------------

def test_code_dirty_present_emits_warning(run_hook, tmp_armature):
    """When .code-dirty exists, the Warnings section must mention it."""
    (tmp_armature / ".armature" / ".code-dirty").touch()
    result = run_hook("reinject-context.sh", "", cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "Application code has been modified" in result.stdout


def test_code_dirty_present_does_not_emit_no_warnings(run_hook, tmp_armature):
    """When .code-dirty exists, '_No warnings._' must NOT appear."""
    (tmp_armature / ".armature" / ".code-dirty").touch()
    result = run_hook("reinject-context.sh", "", cwd=str(tmp_armature))
    assert "_No warnings._" not in result.stdout


# ---------------------------------------------------------------------------
# MUST: .code-dirty absent → _No warnings._
# ---------------------------------------------------------------------------

def test_no_code_dirty_emits_no_warnings_placeholder(run_hook, tmp_armature):
    """When .code-dirty is absent, Warnings section must contain '_No warnings._'."""
    # Ensure marker does NOT exist
    marker = tmp_armature / ".armature" / ".code-dirty"
    if marker.exists():
        marker.unlink()
    result = run_hook("reinject-context.sh", "", cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "_No warnings._" in result.stdout


# ---------------------------------------------------------------------------
# SHOULD: missing state.md → HTML comment containing "not found, skipping"
# ---------------------------------------------------------------------------

def test_missing_state_md_emits_comment(run_hook, tmp_armature):
    """When state.md is absent, output should include 'not found, skipping' comment."""
    state_path = tmp_armature / ".armature" / "session" / "state.md"
    assert not state_path.exists(), "state.md should not exist in tmp_armature"
    result = run_hook("reinject-context.sh", "", cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "not found, skipping" in result.stdout


# ---------------------------------------------------------------------------
# SHOULD: missing journal.md → HTML comment containing "not found, skipping"
# ---------------------------------------------------------------------------

def test_missing_journal_md_emits_comment(run_hook, tmp_armature):
    """When journal.md is absent, output should include 'not found, skipping' comment."""
    journal_path = tmp_armature / ".armature" / "journal.md"
    assert not journal_path.exists(), "journal.md should not exist in tmp_armature"
    result = run_hook("reinject-context.sh", "", cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "not found, skipping" in result.stdout


# ---------------------------------------------------------------------------
# SHOULD: state.md present → its contents appear in Session State section
# ---------------------------------------------------------------------------

def test_state_md_contents_appear_in_output(run_hook, tmp_armature):
    """When state.md exists, its contents should be emitted under ## Session State."""
    state_path = tmp_armature / ".armature" / "session" / "state.md"
    state_path.write_text("## Current Objective\nTest the reinject hook.\n")
    result = run_hook("reinject-context.sh", "", cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "Test the reinject hook." in result.stdout


# ---------------------------------------------------------------------------
# SHOULD: journal with ### entries → recent entries appear in output
# ---------------------------------------------------------------------------

def test_journal_entries_appear_in_output(run_hook, tmp_armature):
    """Journal ### sections should be extracted and emitted."""
    journal_path = tmp_armature / ".armature" / "journal.md"
    journal_path.write_text(
        "# Journal\n\n"
        "### 2026-05-01 — Entry one\n"
        "Some older work.\n\n"
        "### 2026-05-10 — Entry two\n"
        "Some recent work.\n"
    )
    result = run_hook("reinject-context.sh", "", cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "Entry two" in result.stdout


def test_journal_only_last_10_entries_included(run_hook, tmp_armature):
    """When there are more than 10 ### entries, only the last 10 appear."""
    journal_path = tmp_armature / ".armature" / "journal.md"
    entries = []
    for i in range(1, 13):  # 12 entries
        entries.append(f"### 2026-05-{i:02d} — Entry {i}\nContent {i}.\n")
    journal_path.write_text("# Journal\n\n" + "\n".join(entries))
    result = run_hook("reinject-context.sh", "", cwd=str(tmp_armature))
    assert result.returncode == 0
    # Entry 12 (last) must appear
    assert "Entry 12" in result.stdout
    # Entry 1 and 2 should NOT appear (outside last 10)
    assert "Entry 1\n" not in result.stdout
    # Entry 3 should appear (entries 3..12 are the last 10)
    assert "Entry 3" in result.stdout


def test_journal_with_no_hash_entries_emits_no_entries_found(run_hook, tmp_armature):
    """Journal file with no ### headers should emit '_No journal entries found._'."""
    journal_path = tmp_armature / ".armature" / "journal.md"
    journal_path.write_text("# Journal\n\nSome content but no ### entries.\n")
    result = run_hook("reinject-context.sh", "", cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "_No journal entries found._" in result.stdout
