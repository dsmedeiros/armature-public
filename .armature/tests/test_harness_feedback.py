"""
Tests for harness-feedback.sh (G8 advisory Stop hook).

Hook behaviour (verified from source):
  - Always exits 0 — advisory emission only, no invariant backing.
  - lessons.yaml absent → exit 0 + stderr "no lessons corpus".
  - lessons.yaml present → exit 0 + HTML comment on stdout.
  - HTML comment format: <!-- HARNESS-FEEDBACK ... --> with lesson-id, phase, title.
  - stderr prose: "HARNESS-FEEDBACK [<id>]: <title>" + indented text.
  - Phase filtering: keep lessons where phases is empty/absent OR contains current phase.
  - phases: [] = universal (surfaces regardless of phase).
  - Hotfix phase → exit 0 + ADVISORY on stderr; NO HTML comment emitted.
  - NUL byte in lessons.yaml → exit 0 + advisory on stderr.
  - Invalid YAML → exit 0 + advisory on stderr.
  - 0 matching lessons for phase → random fallback from full corpus OR advisory.
  - Selection: highest lesson id (lexicographic max) from filtered set.
  - Lexicographic comparison: L010 > L002 (string compare, not numeric).
  - Local antipatterns.md with mtime <30 days → synthetic candidate added.

All tests use tmp_armature so the real repo is never mutated.
No compound assert X or Y (L005 antipattern).
"""

import re
import subprocess
import time
from pathlib import Path

import pytest

from .helpers import stop_event


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _write_lessons(tmp_armature: Path, content: str) -> None:
    """Write content to .armature/lessons.yaml under tmp_armature."""
    lessons_file = tmp_armature / ".armature" / "lessons.yaml"
    lessons_file.write_text(content, encoding="utf-8")


def _set_phase(tmp_armature: Path, value: str) -> None:
    """Write value to .armature/session/phase under tmp_armature."""
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.parent.mkdir(parents=True, exist_ok=True)
    phase_file.write_text(value, encoding="utf-8")


MINIMAL_LESSONS_YAML = """\
lessons:
  - id: L001
    title: "NUL bytes in stdin bypass JSON parsers"
    phases: [Implementation, Review]
    tags: [hooks, security]
    text: >
      Use sys.stdin.buffer.read() to detect NUL bytes before decode.
"""

HTML_COMMENT_RE = re.compile(
    r"<!--\s*HARNESS-FEEDBACK[\s\S]*?-->",
    re.MULTILINE,
)


# ===========================================================================
# MUST tests (12)
# ===========================================================================

# ---------------------------------------------------------------------------
# MUST 1: hook file exists
# ---------------------------------------------------------------------------

def test_hook_file_exists(repo_root):
    """harness-feedback.sh must exist at .armature/hooks/harness-feedback.sh."""
    hook = repo_root / ".armature" / "hooks" / "harness-feedback.sh"
    assert hook.exists(), (
        "harness-feedback.sh not found; expected at .armature/hooks/harness-feedback.sh"
    )


# ---------------------------------------------------------------------------
# MUST 2: lessons.yaml absent → exit 0 + stderr advisory
# ---------------------------------------------------------------------------

def test_lessons_yaml_absent_exits_0(run_hook, tmp_armature):
    """lessons.yaml absent → exit 0, stderr contains 'no lessons corpus' advisory."""
    # Do NOT write lessons.yaml
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "Expected exit 0 when lessons.yaml absent, got {}".format(result.returncode)
    )
    assert "no lessons corpus" in result.stderr.lower(), (
        f"Expected advisory containing 'no lessons corpus'; got stderr: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# MUST 3: lessons.yaml present → exit 0
# ---------------------------------------------------------------------------

def test_lessons_yaml_present_exits_0(run_hook, tmp_armature):
    """lessons.yaml present → exit 0."""
    _write_lessons(tmp_armature, MINIMAL_LESSONS_YAML)
    _set_phase(tmp_armature, "Implementation")
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "Expected exit 0 with valid lessons.yaml, got {}".format(result.returncode)
    )


# ---------------------------------------------------------------------------
# MUST 4: stdout contains opening and closing HTML comment markers
# ---------------------------------------------------------------------------

def test_html_comment_markers_present(run_hook, tmp_armature):
    """stdout must contain <!-- HARNESS-FEEDBACK and -->."""
    _write_lessons(tmp_armature, MINIMAL_LESSONS_YAML)
    _set_phase(tmp_armature, "Implementation")
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert "<!-- HARNESS-FEEDBACK" in result.stdout, (
        "stdout must contain '<!-- HARNESS-FEEDBACK'; got: {}".format(result.stdout)
    )
    assert "-->" in result.stdout, (
        "stdout must contain '-->'; got: {}".format(result.stdout)
    )


# ---------------------------------------------------------------------------
# MUST 5: HTML comment contains lesson-id, phase, title fields
# ---------------------------------------------------------------------------

def test_html_comment_contains_required_fields(run_hook, tmp_armature):
    """HTML comment must contain lesson-id=, phase=, title= lines."""
    _write_lessons(tmp_armature, MINIMAL_LESSONS_YAML)
    _set_phase(tmp_armature, "Implementation")
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert "lesson-id=" in result.stdout, (
        "stdout must contain 'lesson-id='; got: {}".format(result.stdout)
    )
    assert "phase=" in result.stdout, (
        "stdout must contain 'phase='; got: {}".format(result.stdout)
    )
    assert "title=" in result.stdout, (
        "stdout must contain 'title='; got: {}".format(result.stdout)
    )


# ---------------------------------------------------------------------------
# MUST 6: stderr contains lesson title and lesson text prose
# ---------------------------------------------------------------------------

def test_stderr_contains_lesson_prose(run_hook, tmp_armature):
    """stderr must contain lesson title and indented text prose."""
    _write_lessons(tmp_armature, MINIMAL_LESSONS_YAML)
    _set_phase(tmp_armature, "Implementation")
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert "HARNESS-FEEDBACK" in result.stderr, (
        "stderr must contain 'HARNESS-FEEDBACK'; got: {}".format(result.stderr)
    )
    assert "NUL bytes" in result.stderr, (
        "stderr must contain lesson title text; got: {}".format(result.stderr)
    )


# ---------------------------------------------------------------------------
# MUST 7: phase filtering — only matching-phase lessons surfaced
# ---------------------------------------------------------------------------

def test_phase_filtering_respects_current_phase(run_hook, tmp_armature):
    """Implementation-only lesson surfaces when phase=Implementation; Review-only does not."""
    lessons_content = """\
lessons:
  - id: L001
    title: "Implementation lesson"
    phases: [Implementation]
    tags: []
    text: >
      This is an implementation-only lesson.
  - id: L002
    title: "Review lesson"
    phases: [Review]
    tags: []
    text: >
      This is a review-only lesson.
"""
    _write_lessons(tmp_armature, lessons_content)
    _set_phase(tmp_armature, "Implementation")
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "Expected exit 0, got {}".format(result.returncode)
    )
    # L002 (Review) should NOT appear when phase=Implementation
    assert "Review lesson" not in result.stdout, (
        "Review-only lesson must not surface in Implementation phase; stdout: {}".format(
            result.stdout
        )
    )
    # L001 (Implementation) should appear
    assert "lesson-id=L001" in result.stdout, (
        "Implementation lesson must surface when phase=Implementation; stdout: {}".format(
            result.stdout
        )
    )


# ---------------------------------------------------------------------------
# MUST 8: phases: [] = universal, surfaces regardless of phase
# ---------------------------------------------------------------------------

def test_empty_phases_is_universal(run_hook, tmp_armature):
    """Lesson with phases: [] must surface in any phase."""
    lessons_content = """\
lessons:
  - id: L001
    title: "Universal lesson"
    phases: []
    tags: []
    text: >
      This lesson applies to any phase.
"""
    _write_lessons(tmp_armature, lessons_content)
    _set_phase(tmp_armature, "Design")
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "Expected exit 0 with universal lesson in Design phase"
    )
    assert "lesson-id=L001" in result.stdout, (
        "Universal lesson must surface in Design phase; stdout: {}".format(result.stdout)
    )


# ---------------------------------------------------------------------------
# MUST 9: Hotfix phase → exit 0 + ADVISORY; NO HTML comment
# ---------------------------------------------------------------------------

def test_hotfix_bypass_no_html_comment(run_hook, tmp_armature):
    """Hotfix phase: exit 0, stderr contains advisory, stdout does NOT have HTML comment."""
    _write_lessons(tmp_armature, MINIMAL_LESSONS_YAML)
    _set_phase(tmp_armature, "Hotfix")
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "Expected exit 0 on Hotfix bypass, got {}".format(result.returncode)
    )
    assert "Hotfix" in result.stderr, (
        "stderr must mention Hotfix in bypass advisory; got: {}".format(result.stderr)
    )
    assert "ADVISORY" in result.stderr, (
        f"Hotfix bypass must emit ADVISORY label; got stderr: {result.stderr!r}"
    )
    assert "bypass" in result.stderr.lower(), (
        f"Hotfix bypass must mention 'bypass'; got stderr: {result.stderr!r}"
    )
    assert "<!-- HARNESS-FEEDBACK" not in result.stdout, (
        "HTML comment must NOT be emitted under Hotfix phase; stdout: {}".format(result.stdout)
    )


# ---------------------------------------------------------------------------
# MUST 10: exit 0 in ALL code paths (combine failure modes)
# ---------------------------------------------------------------------------

def test_exit_0_all_failure_modes(run_hook, tmp_armature):
    """Exit 0 even with: no lessons.yaml, no phase file, no antipatterns."""
    # Ensure no lessons.yaml, no phase file
    lessons_path = tmp_armature / ".armature" / "lessons.yaml"
    if lessons_path.exists():
        lessons_path.unlink()
    phase_path = tmp_armature / ".armature" / "session" / "phase"
    if phase_path.exists():
        phase_path.unlink()
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "Expected exit 0 with no lessons.yaml and no phase file, got {}".format(
            result.returncode
        )
    )


# ---------------------------------------------------------------------------
# MUST 11: invalid YAML in lessons.yaml → exit 0 + advisory on stderr
# ---------------------------------------------------------------------------

def test_invalid_yaml_lessons_exits_0(run_hook, tmp_armature):
    """Malformed lessons.yaml → exit 0, stderr contains parse error advisory."""
    _write_lessons(tmp_armature, "lessons: [unclosed bracket\n  bad: : yaml\n")
    _set_phase(tmp_armature, "Implementation")
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "Expected exit 0 with invalid YAML, got {}".format(result.returncode)
    )
    assert "parse error" in result.stderr.lower(), (
        f"Invalid YAML must emit 'parse error' advisory; got stderr: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# MUST 12: 0 matching lessons for phase → fallback selection, exit 0
# ---------------------------------------------------------------------------

def test_zero_matching_lessons_fallback(run_hook, tmp_armature):
    """No lessons match current phase → random fallback or advisory; always exit 0."""
    lessons_content = """\
lessons:
  - id: L001
    title: "Design-only lesson"
    phases: [Design]
    tags: []
    text: >
      This only applies in Design phase.
"""
    _write_lessons(tmp_armature, lessons_content)
    # Set phase to something that doesn't match
    _set_phase(tmp_armature, "Release")
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "Expected exit 0 when no lessons match phase, got {}".format(result.returncode)
    )
    # Either a fallback lesson is emitted or a "no applicable" advisory appears.
    # Both are valid; we just require exit 0.
    # (The implementation uses random fallback from full corpus when filtered is empty.)


# ===========================================================================
# SHOULD tests (6)
# ===========================================================================

# ---------------------------------------------------------------------------
# SHOULD 13: selection is deterministic — same phase + corpus → same lesson
# ---------------------------------------------------------------------------

def test_selection_is_deterministic(run_hook, tmp_armature):
    """Same phase + corpus → same lesson selected on repeated runs."""
    lessons_content = """\
lessons:
  - id: L001
    title: "First lesson"
    phases: []
    tags: []
    text: First lesson text.
  - id: L002
    title: "Second lesson"
    phases: []
    tags: []
    text: Second lesson text.
  - id: L003
    title: "Third lesson"
    phases: []
    tags: []
    text: Third lesson text.
"""
    _write_lessons(tmp_armature, lessons_content)
    _set_phase(tmp_armature, "Implementation")
    result1 = run_hook("harness-feedback.sh", stop_event(), cwd=str(tmp_armature))
    result2 = run_hook("harness-feedback.sh", stop_event(), cwd=str(tmp_armature))
    assert result1.returncode == 0, "First run must exit 0"
    assert result2.returncode == 0, "Second run must exit 0"
    assert result1.stdout == result2.stdout, (
        "Selection must be deterministic; run1 stdout: {!r}, run2 stdout: {!r}".format(
            result1.stdout, result2.stdout
        )
    )


# ---------------------------------------------------------------------------
# SHOULD 14: highest lesson id selected (lexicographic, not numeric)
# ---------------------------------------------------------------------------

def test_highest_id_lexicographic_selected(run_hook, tmp_armature):
    """Highest id by lexicographic comparison selected: L010 > L002 > L001."""
    lessons_content = """\
lessons:
  - id: L001
    title: "Low id lesson"
    phases: []
    tags: []
    text: Low id.
  - id: L010
    title: "High id lesson lexicographic"
    phases: []
    tags: []
    text: Lexicographic max.
  - id: L002
    title: "Middle id lesson"
    phases: []
    tags: []
    text: Middle id.
"""
    _write_lessons(tmp_armature, lessons_content)
    _set_phase(tmp_armature, "Implementation")
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "Expected exit 0, got {}".format(result.returncode)
    )
    assert "lesson-id=L010" in result.stdout, (
        "L010 must be selected as lexicographic max (NOT L002); stdout: {}".format(
            result.stdout
        )
    )


# ---------------------------------------------------------------------------
# SHOULD 15: antipatterns.md with mtime < 30 days → LOCAL-ANTIPATTERNS candidate
# ---------------------------------------------------------------------------

def test_antipatterns_scan_recent_file(run_hook, tmp_armature):
    """antipatterns.md with recent mtime → LOCAL-ANTIPATTERNS candidate added to filtered set."""
    # Write a lessons.yaml with only a Review-phase lesson — so filtered is empty
    # for "Implementation" phase, forcing only LOCAL-ANTIPATTERNS in the filtered set.
    lessons_content = """\
lessons:
  - id: L001
    title: "Review only lesson"
    phases: [Review]
    tags: []
    text: Review only.
"""
    _write_lessons(tmp_armature, lessons_content)
    _set_phase(tmp_armature, "Implementation")

    # Create antipatterns.md with current mtime
    antipatterns_path = tmp_armature / ".armature" / "antipatterns.md"
    antipatterns_path.write_text("# Antipatterns\n\nSome recent antipattern.\n")
    # mtime is already "now" from write; no need to utime

    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "Expected exit 0, got {}".format(result.returncode)
    )
    # LOCAL-ANTIPATTERNS should be selected since it's the only candidate
    # in the filtered set (L001 is Review-only, antipatterns.md is recent)
    assert "LOCAL-ANTIPATTERNS" in result.stdout, (
        "LOCAL-ANTIPATTERNS candidate must surface when antipatterns.md is recent "
        "and no phase-matched lessons exist; stdout: {}".format(result.stdout)
    )


# ---------------------------------------------------------------------------
# SHOULD 16: NUL byte in lessons.yaml → exit 0 + advisory
# ---------------------------------------------------------------------------

def test_nul_byte_in_lessons_yaml_exits_0(run_hook, tmp_armature):
    """lessons.yaml containing NUL byte → exit 0, stderr contains advisory."""
    lessons_path = tmp_armature / ".armature" / "lessons.yaml"
    lessons_path.write_bytes(b"lessons:\n  - id: L001\x00\n    title: bad\n")
    _set_phase(tmp_armature, "Implementation")
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "Expected exit 0 with NUL byte in lessons.yaml, got {}".format(result.returncode)
    )
    assert "NUL" in result.stderr, (
        f"NUL-byte detection advisory must mention 'NUL'; got stderr: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# SHOULD 17: HTML comment parseable by regex
# ---------------------------------------------------------------------------

def test_html_comment_parseable_by_regex(run_hook, tmp_armature):
    """stdout HTML comment must be parseable by the canonical regex pattern."""
    _write_lessons(tmp_armature, MINIMAL_LESSONS_YAML)
    _set_phase(tmp_armature, "Implementation")
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "Expected exit 0, got {}".format(result.returncode)
    )
    match = HTML_COMMENT_RE.search(result.stdout)
    assert match is not None, (
        "HTML comment must be parseable by regex r'<!--\\s*HARNESS-FEEDBACK[\\s\\S]*?-->'; "
        "stdout: {!r}".format(result.stdout)
    )


# ---------------------------------------------------------------------------
# SHOULD 18: corpus with 8+ lessons → lexicographic max selected
# ---------------------------------------------------------------------------

def test_8_lesson_corpus_max_selected(run_hook, tmp_armature):
    """With 8+ lessons (all universal), lexicographic max id is selected."""
    lessons_content = """\
lessons:
  - id: L001
    title: "Lesson 1"
    phases: []
    tags: []
    text: Lesson 1 text.
  - id: L002
    title: "Lesson 2"
    phases: []
    tags: []
    text: Lesson 2 text.
  - id: L003
    title: "Lesson 3"
    phases: []
    tags: []
    text: Lesson 3 text.
  - id: L004
    title: "Lesson 4"
    phases: []
    tags: []
    text: Lesson 4 text.
  - id: L005
    title: "Lesson 5"
    phases: []
    tags: []
    text: Lesson 5 text.
  - id: L006
    title: "Lesson 6"
    phases: []
    tags: []
    text: Lesson 6 text.
  - id: L007
    title: "Lesson 7"
    phases: []
    tags: []
    text: Lesson 7 text.
  - id: L008
    title: "Lesson 8"
    phases: []
    tags: []
    text: Lesson 8 text.
"""
    _write_lessons(tmp_armature, lessons_content)
    _set_phase(tmp_armature, "Implementation")
    result = run_hook(
        "harness-feedback.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "Expected exit 0 with 8-lesson corpus, got {}".format(result.returncode)
    )
    assert "lesson-id=L008" in result.stdout, (
        "L008 must be selected as lexicographic max from 8-lesson corpus; "
        "stdout: {}".format(result.stdout)
    )
