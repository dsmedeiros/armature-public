"""
Format and existence validation tests for the discipline corpus.

Tests parametrized over all 19 discipline IDs. Checks:
  1. File exists at .armature/disciplines/{id}.md
  2. File starts with a top-level H1 heading (# )
  3. File contains a recognizable standards/apply section header
  4. File is ≤ 60 lines
  5. If YAML frontmatter delimiters are present, the frontmatter parses cleanly

Content substance is evaluated by the human reviewer — these tests verify structure only.
"""

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Canonical list of all expected discipline IDs
# ---------------------------------------------------------------------------
DISCIPLINE_IDS = [
    "clean-code",
    "error-handling",
    "typing",
    "python-conventions",
    "test-naming",
    "testing-standards",
    "llm-evaluation-criteria",
    "abstraction-rules",
    "adr-process",
    "layer-boundaries",
    "data-handling",
    "owasp-checklist",
    "metrics",
    "guardrail-rules",
    "sdlc-phases",
    "tdd-workflow",
    "code-review",
    "definition-of-done",
    "interactive-user-input",
]

# Section headers that satisfy the "has a recognizable structure section" check.
# Any discipline must contain at least one of these strings (case-insensitive).
_VALID_SECTION_HEADERS = [
    "## standards",
    "## when to apply",
    "## dod checklist",
    "## summary",
    "## checklist",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _discipline_path(repo_root: Path, discipline_id: str) -> Path:
    return repo_root / ".armature" / "disciplines" / f"{discipline_id}.md"


def _parse_frontmatter(text: str) -> tuple[str | None, str]:
    """
    Split YAML frontmatter from body.

    Returns (frontmatter_text_or_None, body_text).
    Frontmatter is present only when the file starts with '---' on its own line.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        return None, text

    # Find closing delimiter
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip() == "---":
            fm = "".join(lines[1:i])
            body = "".join(lines[i + 1:])
            return fm, body

    # No closing delimiter found — treat as no frontmatter
    return None, text


# ---------------------------------------------------------------------------
# Parametrized tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("discipline_id", DISCIPLINE_IDS)
def test_discipline_file_exists(repo_root: Path, discipline_id: str) -> None:
    """Discipline file must exist at .armature/disciplines/{id}.md."""
    path = _discipline_path(repo_root, discipline_id)
    assert path.exists(), (
        f"Missing discipline file: {path}\n"
        f"Expected one file per discipline ID in DISCIPLINE_IDS."
    )


@pytest.mark.parametrize("discipline_id", DISCIPLINE_IDS)
def test_discipline_has_h1_heading(repo_root: Path, discipline_id: str) -> None:
    """Discipline file must begin (after optional frontmatter) with a # H1 heading."""
    path = _discipline_path(repo_root, discipline_id)
    if not path.exists():
        pytest.skip(f"File missing: {path}")

    text = path.read_text(encoding="utf-8")
    _, body = _parse_frontmatter(text)
    body_stripped = body.lstrip()

    assert body_stripped.startswith("# "), (
        f"{discipline_id}.md: file body does not start with a H1 heading ('# ').\n"
        f"First 80 chars of body: {body_stripped[:80]!r}"
    )


@pytest.mark.parametrize("discipline_id", DISCIPLINE_IDS)
def test_discipline_has_standards_section(repo_root: Path, discipline_id: str) -> None:
    """Discipline file must contain a recognizable structure section header."""
    path = _discipline_path(repo_root, discipline_id)
    if not path.exists():
        pytest.skip(f"File missing: {path}")

    text = path.read_text(encoding="utf-8").lower()
    found = any(header in text for header in _VALID_SECTION_HEADERS)

    assert found, (
        f"{discipline_id}.md: no recognizable structure section found.\n"
        f"Expected one of: {_VALID_SECTION_HEADERS}\n"
        f"Add a '## Standards', '## When to apply', or equivalent section."
    )


@pytest.mark.parametrize("discipline_id", DISCIPLINE_IDS)
def test_discipline_under_60_lines(repo_root: Path, discipline_id: str) -> None:
    """Discipline file must be ≤ 60 lines (test enforces the LOC budget)."""
    path = _discipline_path(repo_root, discipline_id)
    if not path.exists():
        pytest.skip(f"File missing: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    line_count = len(lines)

    assert line_count <= 60, (
        f"{discipline_id}.md: {line_count} lines exceeds the 60-line budget.\n"
        f"Trim content to stay within the per-discipline LOC limit."
    )


@pytest.mark.parametrize("discipline_id", DISCIPLINE_IDS)
def test_discipline_yaml_frontmatter_parses(repo_root: Path, discipline_id: str) -> None:
    """If YAML frontmatter delimiters are present, the frontmatter must parse cleanly."""
    pytest.importorskip("yaml", reason="pyyaml not installed — skipping frontmatter parse test")
    import yaml  # noqa: PLC0415 — import after importorskip guard

    path = _discipline_path(repo_root, discipline_id)
    if not path.exists():
        pytest.skip(f"File missing: {path}")

    text = path.read_text(encoding="utf-8")
    fm_text, _ = _parse_frontmatter(text)

    if fm_text is None:
        pytest.skip(f"{discipline_id}.md: no frontmatter delimiters — skipping parse check")

    try:
        parsed = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        pytest.fail(
            f"{discipline_id}.md: YAML frontmatter parse error: {exc}\n"
            f"Frontmatter text:\n{fm_text}"
        )

    assert isinstance(parsed, dict), (
        f"{discipline_id}.md: frontmatter parsed to {type(parsed).__name__}, expected dict.\n"
        f"Ensure frontmatter is key: value pairs."
    )
