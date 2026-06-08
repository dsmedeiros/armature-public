"""
Tests for .claude/commands/spec.md and .claude/commands/postmortem.md (M6).

Coverage:
  - spec.md: file existence, frontmatter validity, template content, and mechanical
    proof that the rendered template passes task-readiness.sh in strict mode (TASK-001).
  - postmortem.md: file existence, frontmatter validity, D7 slot keyword presence,
    and cross-references to governance files.

MUST tests (14): structural and contract requirements.
SHOULD tests (6): advisory quality checks (discipline-tags, REDACT marker, etc.).

Test naming mirrors test_task_readiness.py:
  test_must_NN_<descriptor>   for MUST tests 1-14
  test_should_NN_<descriptor> for SHOULD tests 15-20
"""

import re
from pathlib import Path

import pytest
import yaml

from .helpers import task_event


# ---------------------------------------------------------------------------
# Module-level path resolution
# ---------------------------------------------------------------------------

# conftest.py uses `git rev-parse --show-toplevel` for repo_root; mirror
# the same derivation for module-level constants without a fixture.
_TESTS_DIR = Path(__file__).resolve().parent          # .armature/tests/
_ARMATURE_DIR = _TESTS_DIR.parent                     # .armature/
_REPO_ROOT = _ARMATURE_DIR.parent                     # repo root

_SPEC_FILE = _REPO_ROOT / ".claude" / "commands" / "spec.md"
_POSTMORTEM_FILE = _REPO_ROOT / ".claude" / "commands" / "postmortem.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> dict:
    """Extract and parse YAML frontmatter delimited by '---' lines.

    Returns the parsed dict, or raises AssertionError if frontmatter is
    absent or unparseable.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise AssertionError("File does not start with YAML frontmatter delimiter '---'")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise AssertionError("Closing '---' delimiter not found in frontmatter")
    fm_text = "\n".join(lines[1:end])
    return yaml.safe_load(fm_text) or {}


def _extract_spec_template(spec_file_text: str) -> str:
    """Extract the rendered task-spec template from spec.md.

    The template lives inside a fenced code block whose content starts
    with `# Task Specification:`. Returns the fence body (without
    the fence delimiters).
    """
    # Find code fences (```...``` blocks); the spec template is the
    # one whose body begins with `# Task Specification:`
    fence_pattern = re.compile(
        r'^```(?:\w+)?\n(.*?)\n```$',
        re.DOTALL | re.MULTILINE,
    )
    for m in fence_pattern.finditer(spec_file_text):
        body = m.group(1)
        if body.lstrip().startswith("# Task Specification:"):
            return body
    raise AssertionError(
        "No fenced code block starting with '# Task Specification:' found in spec.md"
    )


def _criteria_items_under_heading(template_text: str) -> list[str]:
    """Return list-item lines (starting with '- ') under '## Acceptance Criteria'
    before the next '##' heading in the template text.
    """
    in_criteria = False
    items: list[str] = []
    for line in template_text.splitlines():
        if re.match(r'^#{1,6}\s+Acceptance\s+Criteria\s*$', line, re.IGNORECASE):
            in_criteria = True
            continue
        if in_criteria:
            if re.match(r'^##', line):
                break
            if line.startswith("- "):
                items.append(line)
    return items


# ---------------------------------------------------------------------------
# D7 slot keywords for postmortem.md (test 11)
# ---------------------------------------------------------------------------

_D7_REQUIRED_KEYWORDS = [
    "Incident Date",
    "Incident Summary",
    "Phase at incident",
    "Gates bypassed",
    "Hotfix actions",
    "Root cause",
    "Counter-pattern",
    "Follow-up",
    "Governance gaps",
    "Phase transition",
    "Author",
]


# ===========================================================================
# MUST tests (14) — spec.md (1-7) and postmortem.md (8-14)
# ===========================================================================

# ---------------------------------------------------------------------------
# MUST 1: spec.md exists
# ---------------------------------------------------------------------------

def test_must_01_spec_file_exists():
    """spec.md must exist at .claude/commands/spec.md."""
    assert _SPEC_FILE.exists(), f"spec.md not found at {_SPEC_FILE}"


# ---------------------------------------------------------------------------
# MUST 2: spec.md frontmatter parses as valid YAML
# ---------------------------------------------------------------------------

def test_must_02_spec_frontmatter_valid_yaml():
    """spec.md frontmatter must parse as valid YAML without error."""
    text = _SPEC_FILE.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    assert isinstance(fm, dict), "Frontmatter must be a YAML mapping"


# ---------------------------------------------------------------------------
# MUST 3: spec.md frontmatter contains description field, non-empty, <= 80 chars
# ---------------------------------------------------------------------------

def test_must_03_spec_description_field():
    """spec.md frontmatter must contain a non-empty description field, <= 80 chars."""
    text = _SPEC_FILE.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    assert "description" in fm, "frontmatter missing 'description' field"
    desc = str(fm["description"]).strip()
    assert desc, "frontmatter 'description' must not be empty"
    assert len(desc) <= 80, (
        f"'description' is {len(desc)} chars; must be <= 80. Value: {desc!r}"
    )


# ---------------------------------------------------------------------------
# MUST 4: spec.md frontmatter contains argument-hint field
# ---------------------------------------------------------------------------

def test_must_04_spec_argument_hint_field():
    """spec.md frontmatter must contain an 'argument-hint' field."""
    text = _SPEC_FILE.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    assert "argument-hint" in fm, "frontmatter missing 'argument-hint' field"


# ---------------------------------------------------------------------------
# MUST 5: spec.md rendered template piped through task-readiness.sh → exit 0
#         Mechanical proof of D3 / TASK-001 strict-mode compliance.
# ---------------------------------------------------------------------------

def test_must_05_spec_template_passes_task_readiness(run_hook, tmp_armature):
    """Rendered /spec template piped through task-readiness.sh must exit 0.

    This is the mechanical proof that the static template satisfies TASK-001
    strict-mode ('^#{1,6}\\s+Acceptance\\s+Criteria\\s*$' + >=1 list item).
    A defensive check also confirms exit 0 did not come from a fail-open path.
    """
    text = _SPEC_FILE.read_text(encoding="utf-8")
    template_body = _extract_spec_template(text)

    payload = task_event(prompt=template_body)
    result = run_hook("task-readiness.sh", payload, cwd=str(tmp_armature))

    assert result.returncode == 0, (
        f"task-readiness.sh must exit 0 for the /spec template.\n"
        f"stderr: {result.stderr}"
    )
    # Defensive check: exit 0 must not be from the fail-block path.
    assert "Task requires acceptance criteria before delegation per TASK-001" not in result.stderr, (
        "Strict-mode failure reason phrase present in stderr even though exit code is 0; "
        "fail-open path may have masked a real TASK-001 violation."
    )


# ---------------------------------------------------------------------------
# MUST 6: spec.md body contains '## Acceptance Criteria' as level-2 heading
# ---------------------------------------------------------------------------

def test_must_06_spec_acceptance_criteria_heading():
    """spec.md body (or its fenced template) must contain '## Acceptance Criteria'."""
    text = _SPEC_FILE.read_text(encoding="utf-8")
    template_body = _extract_spec_template(text)
    assert "## Acceptance Criteria" in template_body, (
        "'## Acceptance Criteria' not found in the spec.md rendered template"
    )


# ---------------------------------------------------------------------------
# MUST 7: spec.md template has >= 3 list items under ## Acceptance Criteria
# ---------------------------------------------------------------------------

def test_must_07_spec_three_criteria_bullets():
    """spec.md rendered template must have >= 3 '- ' list items under ## Acceptance Criteria."""
    text = _SPEC_FILE.read_text(encoding="utf-8")
    template_body = _extract_spec_template(text)
    items = _criteria_items_under_heading(template_body)
    assert len(items) >= 3, (
        f"Expected >= 3 list items under '## Acceptance Criteria' in spec.md template; "
        f"found {len(items)}: {items}"
    )


# ---------------------------------------------------------------------------
# MUST 8: postmortem.md exists
# ---------------------------------------------------------------------------

def test_must_08_postmortem_file_exists():
    """postmortem.md must exist at .claude/commands/postmortem.md."""
    assert _POSTMORTEM_FILE.exists(), f"postmortem.md not found at {_POSTMORTEM_FILE}"


# ---------------------------------------------------------------------------
# MUST 9: postmortem.md frontmatter parses as valid YAML
# ---------------------------------------------------------------------------

def test_must_09_postmortem_frontmatter_valid_yaml():
    """postmortem.md frontmatter must parse as valid YAML without error."""
    text = _POSTMORTEM_FILE.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    assert isinstance(fm, dict), "Frontmatter must be a YAML mapping"


# ---------------------------------------------------------------------------
# MUST 10: postmortem.md frontmatter contains description field, non-empty, <= 80 chars
# ---------------------------------------------------------------------------

def test_must_10_postmortem_description_field():
    """postmortem.md frontmatter must contain a non-empty description field, <= 80 chars."""
    text = _POSTMORTEM_FILE.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    assert "description" in fm, "frontmatter missing 'description' field"
    desc = str(fm["description"]).strip()
    assert desc, "frontmatter 'description' must not be empty"
    assert len(desc) <= 80, (
        f"'description' is {len(desc)} chars; must be <= 80. Value: {desc!r}"
    )


# ---------------------------------------------------------------------------
# MUST 11: postmortem.md body contains all D7 slot keywords
# ---------------------------------------------------------------------------

def test_must_11_postmortem_d7_slot_keywords():
    """postmortem.md body must contain all 11 D7 slot keywords (case-insensitive).

    Iterates each keyword individually to produce a precise failure message
    when any keyword is missing (no compound assert X or Y).
    """
    body = _POSTMORTEM_FILE.read_text(encoding="utf-8")
    body_lower = body.lower()
    for kw in _D7_REQUIRED_KEYWORDS:
        assert kw.lower() in body_lower, (
            f"{kw!r} slot keyword missing from postmortem.md"
        )


# ---------------------------------------------------------------------------
# MUST 12: postmortem.md body references .armature/antipatterns.md
# ---------------------------------------------------------------------------

def test_must_12_postmortem_references_antipatterns():
    """postmortem.md must reference '.armature/antipatterns.md'."""
    body = _POSTMORTEM_FILE.read_text(encoding="utf-8")
    assert ".armature/antipatterns.md" in body, (
        "postmortem.md must reference '.armature/antipatterns.md'"
    )


# ---------------------------------------------------------------------------
# MUST 13: postmortem.md body references .armature/session/phase
# ---------------------------------------------------------------------------

def test_must_13_postmortem_references_phase_file():
    """postmortem.md must reference '.armature/session/phase'."""
    body = _POSTMORTEM_FILE.read_text(encoding="utf-8")
    assert ".armature/session/phase" in body, (
        "postmortem.md must reference '.armature/session/phase'"
    )


# ---------------------------------------------------------------------------
# MUST 14: postmortem.md body references .armature/journal.md
# ---------------------------------------------------------------------------

def test_must_14_postmortem_references_journal():
    """postmortem.md must reference '.armature/journal.md'."""
    body = _POSTMORTEM_FILE.read_text(encoding="utf-8")
    assert ".armature/journal.md" in body, (
        "postmortem.md must reference '.armature/journal.md'"
    )


# ===========================================================================
# SHOULD tests (6) — advisory quality checks
# ===========================================================================

# ---------------------------------------------------------------------------
# SHOULD 15: spec.md frontmatter contains discipline-tags with definition-of-done
# ---------------------------------------------------------------------------

def test_should_15_spec_discipline_tags():
    """spec.md frontmatter should contain discipline-tags including 'definition-of-done'."""
    text = _SPEC_FILE.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    tags = fm.get("discipline-tags", [])
    assert "definition-of-done" in tags, (
        f"'definition-of-done' not found in spec.md discipline-tags: {tags!r}"
    )


# ---------------------------------------------------------------------------
# SHOULD 16: spec.md body contains $ARGUMENTS reference
# ---------------------------------------------------------------------------

def test_should_16_spec_arguments_reference():
    """spec.md body should reference '$ARGUMENTS' for argument injection."""
    body = _SPEC_FILE.read_text(encoding="utf-8")
    assert "$ARGUMENTS" in body, (
        "'$ARGUMENTS' not found in spec.md body — argument injection reference missing"
    )


# ---------------------------------------------------------------------------
# SHOULD 17: spec.md body contains <title> fallback placeholder
# ---------------------------------------------------------------------------

def test_should_17_spec_title_placeholder():
    """spec.md rendered template should contain '<title>' fallback placeholder."""
    text = _SPEC_FILE.read_text(encoding="utf-8")
    template_body = _extract_spec_template(text)
    assert "<title>" in template_body, (
        "'<title>' placeholder not found in spec.md rendered template"
    )


# ---------------------------------------------------------------------------
# SHOULD 18: postmortem.md frontmatter contains discipline-tags with definition-of-done
# ---------------------------------------------------------------------------

def test_should_18_postmortem_discipline_tags():
    """postmortem.md frontmatter should contain discipline-tags including 'definition-of-done'."""
    text = _POSTMORTEM_FILE.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    tags = fm.get("discipline-tags", [])
    assert "definition-of-done" in tags, (
        f"'definition-of-done' not found in postmortem.md discipline-tags: {tags!r}"
    )


# ---------------------------------------------------------------------------
# SHOULD 19: postmortem.md body contains <!-- REDACT marker
# ---------------------------------------------------------------------------

def test_should_19_postmortem_redact_marker():
    """postmortem.md body should contain '<!-- REDACT' marker for sensitive slot guidance."""
    body = _POSTMORTEM_FILE.read_text(encoding="utf-8")
    assert "<!-- REDACT" in body, (
        "'<!-- REDACT' marker not found in postmortem.md body"
    )


# ---------------------------------------------------------------------------
# SHOULD 20: postmortem.md body references .armature/session/hotfix-audit
# ---------------------------------------------------------------------------

def test_should_20_postmortem_references_hotfix_audit():
    """postmortem.md body should reference '.armature/session/hotfix-audit'."""
    body = _POSTMORTEM_FILE.read_text(encoding="utf-8")
    assert ".armature/session/hotfix-audit" in body, (
        "postmortem.md must reference '.armature/session/hotfix-audit' for D5 detection ladder"
    )
