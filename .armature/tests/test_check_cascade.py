"""
Tests for check-cascade.sh (DRIFT-002, Tier 2 cascade-rule enforcement).

Hook behaviour (verified from source):
  - Reads cascade-rules.yaml from $ARMATURE_DIR/cascade-rules.yaml
    ($ARMATURE_DIR defaults to the hook's ../ directory).
  - Three input modes: --staged-only (git index), --files PATH..., --from-stdin.
  - Exit 0 = PASS/SKIP, exit 2 = FAIL (blocking cascade violation or bad schema).
  - Only severity=blocking rules cause a FAIL.

Each test builds an isolated .armature dir with a custom cascade-rules.yaml,
copies the real hook in, and invokes it with an explicit --files changeset so
no git state is required (the --files path is git-independent).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

BASH_BIN = shutil.which("bash")
if BASH_BIN is None:
    pytest.skip("bash not available on PATH", allow_module_level=True)


# ---------------------------------------------------------------------------
# Fixture: isolated cascade environment
# ---------------------------------------------------------------------------
@pytest.fixture()
def cascade_env(tmp_path, repo_root):
    """
    Return a factory: write_rules(yaml_text) -> (armature_dir, run_files, run_stdin).

    write_rules creates .armature/cascade-rules.yaml with the given text, copies
    the real check-cascade.sh in, and returns helpers that invoke it.
    """
    armature_dir = tmp_path / ".armature"
    hooks_dir = armature_dir / "hooks"
    hooks_dir.mkdir(parents=True)
    real_hook = repo_root / ".armature" / "hooks" / "check-cascade.sh"
    shutil.copy(str(real_hook), str(hooks_dir / "check-cascade.sh"))
    hook_path = hooks_dir / "check-cascade.sh"

    def write_rules(yaml_text: str):
        (armature_dir / "cascade-rules.yaml").write_text(yaml_text, encoding="utf-8")

        def run_files(*paths) -> subprocess.CompletedProcess:
            return subprocess.run(
                [BASH_BIN, str(hook_path), "--files", *paths],
                capture_output=True, text=True, timeout=10,
                env={**_base_env(), "ARMATURE_DIR": str(armature_dir)},
            )

        def run_stdin(stdin_text: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [BASH_BIN, str(hook_path), "--from-stdin"],
                input=stdin_text,
                capture_output=True, text=True, timeout=10,
                env={**_base_env(), "ARMATURE_DIR": str(armature_dir)},
            )

        return run_files, run_stdin

    return write_rules


def _base_env():
    import os
    return os.environ.copy()


# A minimal one-rule ruleset used by most tests.
_BASIC_RULES = """\
version: 1
same_dir_roots: []
rules:
  - name: schema-pair-cascade
    when_touched:
      - "schemas/thing.schema.json"
    must_also_touch:
      - "docs/thing.md"
    reason: "Schema changes require docs update."
    severity: blocking
"""


# ---------------------------------------------------------------------------
# Core: trigger without companion FAILs; with companion PASSes
# ---------------------------------------------------------------------------
def test_trigger_without_companion_fails(cascade_env):
    run_files, _ = cascade_env(_BASIC_RULES)
    result = run_files("schemas/thing.schema.json")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr
    assert "docs/thing.md" in result.stderr


def test_trigger_with_companion_passes(cascade_env):
    run_files, _ = cascade_env(_BASIC_RULES)
    result = run_files("schemas/thing.schema.json", "docs/thing.md")
    assert result.returncode == 0
    assert "PASS" in result.stdout


def test_unrelated_file_passes(cascade_env):
    run_files, _ = cascade_env(_BASIC_RULES)
    result = run_files("README.md")
    assert result.returncode == 0
    assert "PASS" in result.stdout


def test_empty_changeset_passes(cascade_env):
    run_files, _ = cascade_env(_BASIC_RULES)
    result = run_files()  # --files with no paths
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# advisory severity never FAILs
# ---------------------------------------------------------------------------
def test_advisory_rule_does_not_fail(cascade_env):
    rules = _BASIC_RULES.replace("severity: blocking", "severity: advisory")
    run_files, _ = cascade_env(rules)
    result = run_files("schemas/thing.schema.json")  # companion missing
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# glob patterns (** across directories)
# ---------------------------------------------------------------------------
def test_glob_recursive_trigger_fails_without_companion(cascade_env):
    rules = """\
version: 1
rules:
  - name: gold-cascade
    when_touched:
      - "corpora/**/gold.yaml"
    must_also_touch:
      - "MANIFEST.md"
    reason: "Gold changes need manifest."
    severity: blocking
"""
    run_files, _ = cascade_env(rules)
    deep = run_files("corpora/a/b/c/gold.yaml")
    assert deep.returncode == 2
    assert "gold-cascade" in deep.stderr
    ok = run_files("corpora/a/b/c/gold.yaml", "MANIFEST.md")
    assert ok.returncode == 0


# ---------------------------------------------------------------------------
# must_also_touch_same_dir with configured same_dir_roots
# ---------------------------------------------------------------------------
_SAME_DIR_RULES = """\
version: 1
same_dir_roots:
  - packages
rules:
  - name: pkg-changelog-cascade
    when_touched:
      - "packages/**/src/*.py"
    must_also_touch_same_dir:
      - "CHANGELOG.md"
    reason: "Package source changes require a CHANGELOG entry."
    severity: blocking
"""


def test_same_dir_companion_resolves_scope_root_fails(cascade_env):
    run_files, _ = cascade_env(_SAME_DIR_RULES)
    # scope root = packages/foo; companion packages/foo/CHANGELOG.md missing
    result = run_files("packages/foo/src/mod.py")
    assert result.returncode == 2
    assert "packages/foo/CHANGELOG.md" in result.stderr


def test_same_dir_companion_present_passes(cascade_env):
    run_files, _ = cascade_env(_SAME_DIR_RULES)
    result = run_files("packages/foo/src/mod.py", "packages/foo/CHANGELOG.md")
    assert result.returncode == 0


def test_same_dir_inert_without_roots_warns_and_skips(cascade_env):
    # Same rule but same_dir_roots empty → inert, must not FAIL.
    rules = _SAME_DIR_RULES.replace("same_dir_roots:\n  - packages", "same_dir_roots: []")
    run_files, _ = cascade_env(rules)
    result = run_files("packages/foo/src/mod.py")
    assert result.returncode == 0
    assert "WARN" in result.stderr  # warns the same-dir companion is unresolved


# ---------------------------------------------------------------------------
# stdin mode parity with --files
# ---------------------------------------------------------------------------
def test_stdin_mode_matches_files_mode(cascade_env):
    _, run_stdin = cascade_env(_BASIC_RULES)
    result = run_stdin("schemas/thing.schema.json\n")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


# ---------------------------------------------------------------------------
# Schema validation: malformed rules FAIL with exit 2
# ---------------------------------------------------------------------------
def test_rule_missing_when_touched_fails_schema(cascade_env):
    rules = """\
version: 1
rules:
  - name: broken
    must_also_touch:
      - "x.md"
    reason: "no trigger"
    severity: blocking
"""
    run_files, _ = cascade_env(rules)
    result = run_files("anything.txt")
    assert result.returncode == 2
    assert "when_touched" in result.stderr


def test_rule_no_companions_fails_schema(cascade_env):
    rules = """\
version: 1
rules:
  - name: nocomp
    when_touched:
      - "a.txt"
    reason: "no companions"
    severity: blocking
"""
    run_files, _ = cascade_env(rules)
    result = run_files("a.txt")
    assert result.returncode == 2
    assert "no companions" in result.stderr or "companions" in result.stderr


def test_invalid_severity_fails_schema(cascade_env):
    rules = _BASIC_RULES.replace("severity: blocking", "severity: bogus")
    run_files, _ = cascade_env(rules)
    result = run_files("schemas/thing.schema.json")
    assert result.returncode == 2
    assert "severity" in result.stderr


def test_bad_yaml_fails(cascade_env):
    run_files, _ = cascade_env("version: 1\nrules: [unterminated\n")
    result = run_files("x.txt")
    assert result.returncode == 2


def test_empty_rules_file_passes(cascade_env):
    run_files, _ = cascade_env("version: 1\nrules: []\n")
    result = run_files("schemas/thing.schema.json")
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Missing rules file → SKIP (exit 0)
# ---------------------------------------------------------------------------
def test_missing_rules_file_skips(tmp_path, repo_root):
    armature_dir = tmp_path / ".armature"
    hooks_dir = armature_dir / "hooks"
    hooks_dir.mkdir(parents=True)
    shutil.copy(
        str(repo_root / ".armature" / "hooks" / "check-cascade.sh"),
        str(hooks_dir / "check-cascade.sh"),
    )
    result = subprocess.run(
        [BASH_BIN, str(hooks_dir / "check-cascade.sh"), "--files", "schemas/thing.schema.json"],
        capture_output=True, text=True, timeout=10,
        env={**_base_env(), "ARMATURE_DIR": str(armature_dir)},
    )
    assert result.returncode == 0
    assert "SKIP" in result.stdout


# ---------------------------------------------------------------------------
# Windows-style backslash paths normalize
# ---------------------------------------------------------------------------
def test_backslash_paths_normalize(cascade_env):
    run_files, _ = cascade_env(_BASIC_RULES)
    # Trigger via backslash form; companion via forward slash — should PASS
    result = run_files("schemas\\thing.schema.json", "docs/thing.md")
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Regression: --files consumes --prefixed filenames as paths, not options
# (greptile PR #34: a tracked file literally named "--staged-only" must not
# flip the check mode).
# ---------------------------------------------------------------------------
def test_files_mode_consumes_dashdash_prefixed_filename(cascade_env):
    rules = """\
version: 1
rules:
  - name: weird-name-cascade
    when_touched:
      - "--staged-only"
    must_also_touch:
      - "docs/weird.md"
    reason: "Trigger file is literally named --staged-only."
    severity: blocking
"""
    run_files, _ = cascade_env(rules)
    # If --staged-only were treated as an option, MODE would flip and the
    # explicit path set would be lost (→ false PASS). It must be treated as a
    # path, match the trigger, and FAIL because docs/weird.md is absent.
    result = run_files("--staged-only")
    assert result.returncode == 2
    assert "weird-name-cascade" in result.stderr


def test_files_mode_double_dash_terminator_skipped(cascade_env):
    run_files, _ = cascade_env(_BASIC_RULES)
    # run_files prepends --files, so this invokes:
    #   check-cascade.sh --files -- schemas/thing.schema.json
    # The "--" terminator is accepted and skipped; the path is still collected
    # and matches the trigger (companion docs/thing.md absent → FAIL).
    result = run_files("--", "schemas/thing.schema.json")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


# ---------------------------------------------------------------------------
# Regression: PyYAML missing → fail CLOSED (exit 2), not SKIP
# (codex PR #34 P1: a blocking commit gate must not silently allow when it
# cannot parse its own rules). Simulated by running the hook with a Python
# whose import of yaml is forced to fail via a sitecustomize shim.
# ---------------------------------------------------------------------------
def test_pyyaml_missing_fails_closed(cascade_env, tmp_path):
    import os
    run_files, _ = cascade_env(_BASIC_RULES)
    # Build a directory containing a `yaml` package that raises on import,
    # and put it FIRST on PYTHONPATH so `import yaml` fails inside the hook.
    shim_dir = tmp_path / "yamlshim"
    (shim_dir / "yaml").mkdir(parents=True)
    (shim_dir / "yaml" / "__init__.py").write_text("raise ImportError('simulated missing PyYAML')\n")
    env = os.environ.copy()
    env["ARMATURE_DIR"] = str((tmp_path / ".armature"))
    env["PYTHONPATH"] = str(shim_dir) + os.pathsep + env.get("PYTHONPATH", "")
    # Re-resolve the armature dir used by cascade_env's write_rules (it lives
    # under the fixture's tmp_path/.armature). Invoke the hook directly.
    hook = (tmp_path / ".armature" / "hooks" / "check-cascade.sh")
    result = subprocess.run(
        [BASH_BIN, str(hook), "--files", "schemas/thing.schema.json"],
        capture_output=True, text=True, timeout=10, env=env,
    )
    assert result.returncode == 2
    assert "PyYAML" in result.stderr


# ---------------------------------------------------------------------------
# Regression: globstar `**` must match ZERO intervening directories too
# (codex PR #34): `dir/**/file` should trigger on `dir/file` directly under dir,
# not only on nested `dir/x/file`.
# ---------------------------------------------------------------------------
_GLOBSTAR_RULES = """\
version: 1
rules:
  - name: glob-cascade
    when_touched:
      - "corpora/**/gold.yaml"
    must_also_touch:
      - "MANIFEST.md"
    reason: "Gold changes need manifest."
    severity: blocking
"""


def test_globstar_zero_directory_match(cascade_env):
    run_files, _ = cascade_env(_GLOBSTAR_RULES)
    # File directly under corpora/ (zero intervening dirs) MUST trigger.
    r0 = run_files("corpora/gold.yaml")
    assert r0.returncode == 2, "dir/**/file must match dir/file (zero dirs)"
    assert "glob-cascade" in r0.stderr


def test_globstar_one_and_multi_directory_match(cascade_env):
    run_files, _ = cascade_env(_GLOBSTAR_RULES)
    assert run_files("corpora/a/gold.yaml").returncode == 2
    assert run_files("corpora/a/b/c/gold.yaml").returncode == 2


def test_globstar_with_companion_passes(cascade_env):
    run_files, _ = cascade_env(_GLOBSTAR_RULES)
    assert run_files("corpora/gold.yaml", "MANIFEST.md").returncode == 0
    assert run_files("corpora/a/b/gold.yaml", "MANIFEST.md").returncode == 0


def test_globstar_non_match_outside_prefix(cascade_env):
    run_files, _ = cascade_env(_GLOBSTAR_RULES)
    # Different top-level prefix must NOT trigger.
    assert run_files("other/gold.yaml").returncode == 0


def test_leading_globstar_zero_and_nested(cascade_env):
    rules = """\
version: 1
rules:
  - name: lead-glob
    when_touched:
      - "**/CHANGELOG.md"
    must_also_touch:
      - "VERSION"
    reason: "changelog needs version bump."
    severity: blocking
"""
    run_files, _ = cascade_env(rules)
    # Top-level (zero leading dirs) and nested both trigger.
    assert run_files("CHANGELOG.md").returncode == 2
    assert run_files("pkg/CHANGELOG.md").returncode == 2
    assert run_files("CHANGELOG.md", "VERSION").returncode == 0
