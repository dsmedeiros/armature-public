"""
Tests for .armature/disciplines/triggers.yaml (Step 6, M4 CP2).

Validates:
  1. Valid YAML parse
  2. All 19 expected discipline IDs present
  3. Each entry has required fields (severity, composition-mode, triggers)
  4. All severity values from allowed set
  5. All composition-mode values from allowed set
  6. All trigger type values from allowed set
  7. Referential integrity: every discipline-id key has a matching .md file
  8. Severity drift detection: triggers.yaml severity matches .md frontmatter
  9. Composition-mode drift detection: triggers.yaml comp-mode matches .md frontmatter
 10. post-stop.sh exits 2 on bogus severity in triggers.yaml
 11. post-stop.sh exits 2 when triggers.yaml references a missing discipline file
 12. post-stop.sh exits 2 on severity drift between triggers.yaml and discipline .md
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml not installed")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_DISCIPLINE_IDS = [
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

VALID_SEVERITIES = {"critical", "high", "standard"}
VALID_COMP_MODES = {"strict", "advisory"}
VALID_TRIGGER_TYPES = {"path", "invariant", "content", "explicit"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _triggers_path(repo_root: Path) -> Path:
    return repo_root / ".armature" / "disciplines" / "triggers.yaml"


def _disciplines_dir(repo_root: Path) -> Path:
    return repo_root / ".armature" / "disciplines"


def _load_triggers(repo_root: Path) -> dict:
    data = yaml.safe_load(_triggers_path(repo_root).read_text(encoding="utf-8"))
    return data.get("triggers", {})


def _parse_frontmatter(text: str) -> dict | None:
    """Return parsed frontmatter dict or None if absent/unparseable."""
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end <= 0:
        return None
    fm_text = text[3:end]
    try:
        result = yaml.safe_load(fm_text)
        return result if isinstance(result, dict) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Test 1: Valid YAML
# ---------------------------------------------------------------------------

def test_triggers_yaml_parses(repo_root: Path) -> None:
    """triggers.yaml must parse as valid YAML."""
    path = _triggers_path(repo_root)
    assert path.exists(), f"triggers.yaml not found at {path}"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "triggers.yaml must parse to a dict"
    assert "triggers" in data, "triggers.yaml must have a top-level 'triggers' key"
    assert isinstance(data["triggers"], dict), "'triggers' must be a mapping"


# ---------------------------------------------------------------------------
# Test 2: All 19 disciplines present
# ---------------------------------------------------------------------------

def test_all_19_disciplines_present(repo_root: Path) -> None:
    """Every expected discipline ID must be a key in triggers.yaml."""
    triggers = _load_triggers(repo_root)
    for disc_id in EXPECTED_DISCIPLINE_IDS:
        assert disc_id in triggers, (
            f"Discipline '{disc_id}' is missing from triggers.yaml. "
            f"Expected all 19 disciplines to be registered."
        )
    assert len(triggers) == 19, (
        f"Expected exactly 19 discipline entries, got {len(triggers)}: {sorted(triggers.keys())}"
    )


# ---------------------------------------------------------------------------
# Test 3: Each entry has required fields
# ---------------------------------------------------------------------------

def test_each_entry_has_required_fields(repo_root: Path) -> None:
    """Each trigger entry must have severity, composition-mode, and triggers."""
    triggers = _load_triggers(repo_root)
    for disc_id, entry in triggers.items():
        assert isinstance(entry, dict), f"'{disc_id}': entry must be a mapping"
        assert "severity" in entry, f"'{disc_id}': missing 'severity' field"
        assert "composition-mode" in entry, f"'{disc_id}': missing 'composition-mode' field"
        assert "triggers" in entry, f"'{disc_id}': missing 'triggers' field"
        assert isinstance(entry["triggers"], list), f"'{disc_id}': 'triggers' must be a list"
        assert len(entry["triggers"]) >= 1, f"'{disc_id}': 'triggers' list must be non-empty"


# ---------------------------------------------------------------------------
# Test 4: severity values valid
# ---------------------------------------------------------------------------

def test_severity_values_valid(repo_root: Path) -> None:
    """All severity values in triggers.yaml must be from the allowed set."""
    triggers = _load_triggers(repo_root)
    for disc_id, entry in triggers.items():
        severity = entry.get("severity", "")
        assert severity in VALID_SEVERITIES, (
            f"'{disc_id}': invalid severity '{severity}'. "
            f"Must be one of {sorted(VALID_SEVERITIES)}."
        )


# ---------------------------------------------------------------------------
# Test 5: composition-mode values valid
# ---------------------------------------------------------------------------

def test_composition_mode_values_valid(repo_root: Path) -> None:
    """All composition-mode values in triggers.yaml must be from the allowed set."""
    triggers = _load_triggers(repo_root)
    for disc_id, entry in triggers.items():
        comp_mode = entry.get("composition-mode", "")
        assert comp_mode in VALID_COMP_MODES, (
            f"'{disc_id}': invalid composition-mode '{comp_mode}'. "
            f"Must be one of {sorted(VALID_COMP_MODES)}."
        )


# ---------------------------------------------------------------------------
# Test 6: trigger type values valid
# ---------------------------------------------------------------------------

def test_trigger_type_values_valid(repo_root: Path) -> None:
    """All trigger type values must be from the allowed set."""
    triggers = _load_triggers(repo_root)
    for disc_id, entry in triggers.items():
        for trig in entry.get("triggers", []):
            trig_type = trig.get("type", "")
            assert trig_type in VALID_TRIGGER_TYPES, (
                f"'{disc_id}': invalid trigger type '{trig_type}'. "
                f"Must be one of {sorted(VALID_TRIGGER_TYPES)}."
            )


# ---------------------------------------------------------------------------
# Test 7: referential integrity
# ---------------------------------------------------------------------------

def test_referential_integrity(repo_root: Path) -> None:
    """Every discipline-id key in triggers.yaml must have a matching .md file."""
    triggers = _load_triggers(repo_root)
    disciplines_dir = _disciplines_dir(repo_root)
    for disc_id in triggers:
        disc_file = disciplines_dir / f"{disc_id}.md"
        assert disc_file.exists(), (
            f"triggers.yaml references '{disc_id}' but "
            f".armature/disciplines/{disc_id}.md does not exist"
        )


# ---------------------------------------------------------------------------
# Test 8: severity drift detection
# ---------------------------------------------------------------------------

def test_severity_drift_detection(repo_root: Path) -> None:
    """Severity in triggers.yaml must match discipline frontmatter severity."""
    triggers = _load_triggers(repo_root)
    disciplines_dir = _disciplines_dir(repo_root)
    for disc_id, entry in triggers.items():
        disc_file = disciplines_dir / f"{disc_id}.md"
        if not disc_file.exists():
            continue
        text = disc_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        if fm is None or "severity" not in fm:
            continue
        yaml_severity = entry.get("severity", "")
        fm_severity = fm["severity"]
        assert yaml_severity == fm_severity, (
            f"'{disc_id}': severity drift detected. "
            f"triggers.yaml has '{yaml_severity}', "
            f"discipline frontmatter has '{fm_severity}'."
        )


# ---------------------------------------------------------------------------
# Test 9: composition-mode drift detection
# ---------------------------------------------------------------------------

def test_composition_mode_drift_detection(repo_root: Path) -> None:
    """Composition-mode in triggers.yaml must match discipline frontmatter."""
    triggers = _load_triggers(repo_root)
    disciplines_dir = _disciplines_dir(repo_root)
    for disc_id, entry in triggers.items():
        disc_file = disciplines_dir / f"{disc_id}.md"
        if not disc_file.exists():
            continue
        text = disc_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        if fm is None or "composition-mode" not in fm:
            continue
        yaml_comp = entry.get("composition-mode", "")
        fm_comp = fm["composition-mode"]
        assert yaml_comp == fm_comp, (
            f"'{disc_id}': composition-mode drift detected. "
            f"triggers.yaml has '{yaml_comp}', "
            f"discipline frontmatter has '{fm_comp}'."
        )


# ---------------------------------------------------------------------------
# Fixtures for post-stop.sh probe tests (10, 11, 12)
# ---------------------------------------------------------------------------

BASH_BIN = shutil.which("bash")


def _build_probe_repo(tmp_path: Path, repo_root: Path) -> Path:
    """
    Build a minimal valid git repo for post-stop.sh probe tests.
    Includes a valid triggers.yaml and one discipline file.
    """
    repo = tmp_path / "probe_repo"
    repo.mkdir()

    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        check=True, capture_output=True, cwd=str(repo),
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        check=True, capture_output=True, cwd=str(repo),
    )

    # Directory structure
    armature_dir = repo / ".armature"
    disciplines_dir = armature_dir / "disciplines"
    disciplines_dir.mkdir(parents=True)
    (armature_dir / "session").mkdir(parents=True)
    (armature_dir / "invariants").mkdir(parents=True)
    hooks_dir = armature_dir / "hooks"
    hooks_dir.mkdir(parents=True)

    adr_dir = repo / "docs" / "adr"
    adr_dir.mkdir(parents=True)

    # Copy real hook scripts
    real_hooks_dir = repo_root / ".armature" / "hooks"
    for hook_file in real_hooks_dir.glob("*.sh"):
        shutil.copy(str(hook_file), str(hooks_dir / hook_file.name))

    # Baseline governance files
    (repo / "CLAUDE.md").write_text(
        "# Test CLAUDE.md\n| Spec | `.armature/agents.md` | ADR-0001 |\n"
    )
    (repo / "CODEX.md").write_text(
        "# Test CODEX.md\n| Spec | `.armature/agents.md` | ADR-0001 |\n"
    )
    (armature_dir / "invariants" / "registry.yaml").write_text(
        "invariants:\n  TEST-001:\n    name: Test\n    severity: standard\n"
        "    rule: Test rule.\n    status: active\n"
    )
    (armature_dir / "agents.md").write_text(
        "---\nscope: .armature\nadrs: [ADR-0001, ADR-0002]\n---\n# Test\n"
    )
    (adr_dir / "0001-baseline.md").write_text("# ADR-0001\n")
    (adr_dir / "0002-baseline.md").write_text("# ADR-0002\n")

    # A valid discipline file
    (disciplines_dir / "clean-code.md").write_text(
        "---\nseverity: standard\ncomposition-mode: advisory\n---\n"
        "# Clean Code\n\n## Standards\n\n- Write clean code.\n"
    )

    # A valid triggers.yaml with one discipline
    (armature_dir / "disciplines" / "triggers.yaml").write_text(
        "triggers:\n"
        "  clean-code:\n"
        "    severity: standard\n"
        "    composition-mode: advisory\n"
        "    triggers:\n"
        "      - type: path\n"
        "        pattern: '**/*'\n"
    )

    subprocess.run(
        ["git", "add", "."], check=True, capture_output=True, cwd=str(repo),
    )
    subprocess.run(
        ["git", "commit", "-m", "init probe baseline"],
        check=True, capture_output=True, cwd=str(repo),
    )

    return repo


def _run_post_stop(repo: Path, repo_root: Path) -> subprocess.CompletedProcess:
    hook_path = repo / ".armature" / "hooks" / "post-stop.sh"
    return subprocess.run(
        [BASH_BIN, str(hook_path)],
        capture_output=True,
        text=True,
        cwd=str(repo),
        timeout=15,
    )


# ---------------------------------------------------------------------------
# Test 10: post-stop exits 2 on bogus severity
# ---------------------------------------------------------------------------

@pytest.mark.skipif(BASH_BIN is None, reason="bash not available")
def test_post_stop_exits_2_on_bogus_severity(tmp_path: Path, repo_root: Path) -> None:
    """post-stop.sh must exit 2 when triggers.yaml has an invalid severity value."""
    repo = _build_probe_repo(tmp_path, repo_root)
    triggers_file = repo / ".armature" / "disciplines" / "triggers.yaml"
    triggers_file.write_text(
        "triggers:\n"
        "  clean-code:\n"
        "    severity: BOGUS_SEVERITY\n"
        "    composition-mode: advisory\n"
        "    triggers:\n"
        "      - type: path\n"
        "        pattern: '**/*'\n"
    )
    result = _run_post_stop(repo, repo_root)
    assert result.returncode == 2, (
        f"Expected exit 2 on bogus severity, got {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "FAIL" in result.stdout
    assert "BOGUS_SEVERITY" in result.stdout


# ---------------------------------------------------------------------------
# Test 11: post-stop exits 2 on missing discipline file
# ---------------------------------------------------------------------------

@pytest.mark.skipif(BASH_BIN is None, reason="bash not available")
def test_post_stop_exits_2_on_missing_discipline_file(tmp_path: Path, repo_root: Path) -> None:
    """post-stop.sh must exit 2 when triggers.yaml references a non-existent discipline file."""
    repo = _build_probe_repo(tmp_path, repo_root)
    triggers_file = repo / ".armature" / "disciplines" / "triggers.yaml"
    triggers_file.write_text(
        "triggers:\n"
        "  clean-code:\n"
        "    severity: standard\n"
        "    composition-mode: advisory\n"
        "    triggers:\n"
        "      - type: path\n"
        "        pattern: '**/*'\n"
        "  nonexistent-discipline:\n"
        "    severity: high\n"
        "    composition-mode: strict\n"
        "    triggers:\n"
        "      - type: explicit\n"
        "        pattern: nonexistent-discipline\n"
    )
    result = _run_post_stop(repo, repo_root)
    assert result.returncode == 2, (
        f"Expected exit 2 on missing discipline file, got {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "FAIL" in result.stdout
    assert "nonexistent-discipline" in result.stdout


# ---------------------------------------------------------------------------
# Test 12: post-stop exits 2 on severity drift
# ---------------------------------------------------------------------------

@pytest.mark.skipif(BASH_BIN is None, reason="bash not available")
def test_post_stop_exits_2_on_severity_drift(tmp_path: Path, repo_root: Path) -> None:
    """post-stop.sh must exit 2 when triggers.yaml severity differs from discipline frontmatter."""
    repo = _build_probe_repo(tmp_path, repo_root)
    # triggers.yaml says 'high' but discipline frontmatter says 'standard'
    triggers_file = repo / ".armature" / "disciplines" / "triggers.yaml"
    triggers_file.write_text(
        "triggers:\n"
        "  clean-code:\n"
        "    severity: high\n"
        "    composition-mode: advisory\n"
        "    triggers:\n"
        "      - type: path\n"
        "        pattern: '**/*'\n"
    )
    result = _run_post_stop(repo, repo_root)
    assert result.returncode == 2, (
        f"Expected exit 2 on severity drift, got {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "FAIL" in result.stdout
    assert "severity" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Test 13 (LOW-3 cycle-2): post-stop rejects traversal discipline ID
# ---------------------------------------------------------------------------

@pytest.mark.skipif(BASH_BIN is None, reason="bash not available")
def test_post_stop_rejects_traversal_id(tmp_path: Path, repo_root: Path) -> None:
    """post-stop.sh must exit 2 when a discipline ID contains path traversal characters.

    A key like '../../foo' must be rejected before any os.path.join operation.
    Per LOW-3 fix in cycle-2.
    """
    repo = _build_probe_repo(tmp_path, repo_root)
    triggers_file = repo / ".armature" / "disciplines" / "triggers.yaml"
    # YAML requires quoting for keys containing special characters
    triggers_file.write_text(
        "triggers:\n"
        "  '../../foo':\n"
        "    severity: standard\n"
        "    composition-mode: advisory\n"
        "    triggers:\n"
        "      - type: path\n"
        "        pattern: '**/*'\n"
    )
    result = _run_post_stop(repo, repo_root)
    assert result.returncode == 2, (
        f"Expected exit 2 for traversal discipline ID, got {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "FAIL" in result.stdout, (
        f"Expected FAIL message for traversal ID.\nstdout: {result.stdout}"
    )
