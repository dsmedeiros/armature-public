"""
Tests for post-stop.sh (HOOK-003, SCHEMA-001, SCHEMA-002, REF-001, REF-002, REF-003, TASK-002 GC).

Hook behaviour (verified from source):
  - Runs multiple sequential checks; exits 1 on first FAIL.
  - Exits 0 if all checks pass.
  - Does NOT read stdin.

Check summary:
  1. check_adapter_routes(CLAUDE.md) — backtick-agents.md references must exist
  2. check_adapter_routes(CODEX.md) — same for CODEX.md; silently skipped if absent
  3. registry.yaml valid YAML → PASS; invalid → FAIL (exit 1)
  4. Uncommitted governance file changes → WARN (not FAIL), exit 0
  5. agents.md frontmatter ADR refs must resolve → FAIL (exit 1) if any missing
  6. .code-dirty present:
       - test runner found → run tests (smoke); pass → PASS message; fail → exit 1
         NOTE: marker is NOT cleared by post-stop (run-ci.sh owns marker lifecycle)
       - test runner absent → "SKIP: No test runner detected; deferring...", exit 0
         NOTE: marker is PRESERVED (not removed)
     .code-dirty absent → "SKIP: No application code changes detected"

Test isolation: each test uses setup_post_stop_repo() from conftest to build a
minimal valid baseline git repo in tmp_path, then mutates it for the specific case.
"""

import os
import subprocess
import time

import pytest


# ---------------------------------------------------------------------------
# MUST: exit 0 on clean repo (all checks PASS)
# ---------------------------------------------------------------------------

def test_clean_repo_exits_zero(run_hook, setup_post_stop_repo):
    """A fully valid baseline repo must produce exit 0."""
    repo = setup_post_stop_repo()
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0


def test_clean_repo_has_pass_messages(run_hook, setup_post_stop_repo):
    """A clean repo should emit at least one PASS line."""
    repo = setup_post_stop_repo()
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0
    assert "PASS" in result.stdout


# ---------------------------------------------------------------------------
# MUST: exit 1 on bad CLAUDE.md route (agents.md path that doesn't exist)
# ---------------------------------------------------------------------------

def test_bad_claude_md_route_exits_one(run_hook, setup_post_stop_repo):
    """A CLAUDE.md referencing a non-existent agents.md must exit 1."""
    repo = setup_post_stop_repo()
    # Append a backtick-referenced agents.md path that doesn't exist
    claude_md = repo / "CLAUDE.md"
    existing = claude_md.read_text()
    claude_md.write_text(
        existing + "\n| Ghost Scope | `.ghost/does-not-exist/agents.md` | ADR-0001 |\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 1


def test_bad_claude_md_route_emits_fail_message(run_hook, setup_post_stop_repo):
    """The FAIL message must reference the missing agents.md path."""
    repo = setup_post_stop_repo()
    claude_md = repo / "CLAUDE.md"
    existing = claude_md.read_text()
    claude_md.write_text(
        existing + "\n| Ghost Scope | `.ghost/agents.md` | ADR-0001 |\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    assert ".ghost/agents.md" in result.stdout


# ---------------------------------------------------------------------------
# MUST: exit 1 on invalid registry YAML
# ---------------------------------------------------------------------------

def test_invalid_registry_yaml_exits_one(run_hook, setup_post_stop_repo):
    """Invalid YAML in registry.yaml must cause exit 1."""
    repo = setup_post_stop_repo()
    registry = repo / ".armature" / "invariants" / "registry.yaml"
    registry.write_text("invariants: [\nunterminated bracket\n")
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 1


def test_invalid_registry_yaml_emits_fail_message(run_hook, setup_post_stop_repo):
    """The FAIL message must mention 'Invariant registry has invalid YAML'."""
    repo = setup_post_stop_repo()
    registry = repo / ".armature" / "invariants" / "registry.yaml"
    registry.write_text(": bad: yaml: {{{")
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    assert "invalid YAML" in result.stdout


# ---------------------------------------------------------------------------
# MUST: exit 0 + "PASS: Invariant registry is valid YAML" on valid registry
# ---------------------------------------------------------------------------

def test_valid_registry_emits_pass_message(run_hook, setup_post_stop_repo):
    """A valid registry.yaml must produce a PASS message for registry YAML."""
    repo = setup_post_stop_repo()
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0
    assert "PASS: Invariant registry is valid YAML" in result.stdout


# ---------------------------------------------------------------------------
# MUST: exit 1 on bad ADR ref in agents.md
# ---------------------------------------------------------------------------

def test_bad_adr_ref_in_agents_md_exits_one(run_hook, setup_post_stop_repo):
    """An agents.md frontmatter referencing a non-existent ADR must exit 1."""
    repo = setup_post_stop_repo()
    # Add an agents.md that references a non-existent ADR
    scope_dir = repo / "bad_scope"
    scope_dir.mkdir()
    (scope_dir / "agents.md").write_text(
        "---\nscope: bad_scope\nadrs: [ADR-9999]\n---\n\n# Bad Scope\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 1


def test_bad_adr_ref_emits_fail_message(run_hook, setup_post_stop_repo):
    """The FAIL message must mention the ADR number and the agents.md file."""
    repo = setup_post_stop_repo()
    scope_dir = repo / "bad_adr_scope"
    scope_dir.mkdir()
    (scope_dir / "agents.md").write_text(
        "---\nscope: bad_adr_scope\nadrs: [ADR-8888]\n---\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    assert "8888" in result.stdout


# ---------------------------------------------------------------------------
# MUST: .code-dirty present + no test runner → "SKIP: No test runner detected"
#       exit 0, marker REMOVED
# ---------------------------------------------------------------------------

def test_code_dirty_no_test_runner_exits_zero(run_hook, setup_post_stop_repo):
    """.code-dirty with no tests/ dir and no Makefile/package.json → exit 0."""
    repo = setup_post_stop_repo()
    marker = repo / ".armature" / ".code-dirty"
    marker.touch()
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0


def test_code_dirty_no_test_runner_emits_skip(run_hook, setup_post_stop_repo):
    """.code-dirty with no test runner must emit SKIP message with 'deferring'."""
    repo = setup_post_stop_repo()
    marker = repo / ".armature" / ".code-dirty"
    marker.touch()
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0
    assert "SKIP" in result.stdout
    assert "No test runner detected" in result.stdout
    assert "deferring" in result.stdout


def test_code_dirty_no_test_runner_preserves_marker(run_hook, setup_post_stop_repo):
    """.code-dirty marker must be preserved by post-stop when no test runner is found.

    Contract: marker clearance is the responsibility of run-ci.sh (CI-001),
    which runs the configured full pipeline. post-stop.sh is a fast-feedback
    smoke pass and must not pre-empt run-ci.sh's marker lifecycle.
    """
    repo = setup_post_stop_repo()
    marker = repo / ".armature" / ".code-dirty"
    marker.touch()
    assert marker.exists()
    run_hook("post-stop.sh", "", cwd=str(repo))
    assert marker.exists(), (
        ".code-dirty must be preserved by post-stop.sh so run-ci.sh "
        "can execute the configured full pipeline before clearing it"
    )


def test_code_dirty_no_test_runner_marker_absent_before_run_stays_absent(
    run_hook, setup_post_stop_repo
):
    """When .code-dirty is absent, no marker should be created by post-stop."""
    repo = setup_post_stop_repo()
    marker = repo / ".armature" / ".code-dirty"
    assert not marker.exists()
    run_hook("post-stop.sh", "", cwd=str(repo))
    assert not marker.exists()


# ---------------------------------------------------------------------------
# MUST: package-local tests/ detection (cycle-5 + cycle-15)
# ---------------------------------------------------------------------------

def test_code_dirty_package_local_tests_dir_detected(run_hook, setup_post_stop_repo):
    """A package-local <pkg>/tests/ with a passing test is detected and run.

    post-stop.sh should find mypkg/tests/, scope pytest to it, and produce
    PASS output. The dirty marker must still exist afterward (marker lifecycle
    belongs to run-ci.sh, not post-stop.sh).
    """
    repo = setup_post_stop_repo()
    marker = repo / ".armature" / ".code-dirty"
    marker.touch()

    # Create a package-local test dir with a passing test
    pkg_tests = repo / "mypkg" / "tests"
    pkg_tests.mkdir(parents=True)
    (pkg_tests / "__init__.py").write_text("")
    (pkg_tests / "test_simple.py").write_text("def test_pass(): assert True\n")

    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0, (
        f"Expected exit 0 when package-local pytest passes; got {result.returncode}. "
        f"stdout={result.stdout[-400:]!r} stderr={result.stderr[-400:]!r}"
    )
    combined = result.stdout + result.stderr
    assert "PASS" in combined, (
        "Expected PASS output when package-local test passes"
    )


def test_code_dirty_package_local_skips_armature_dir(run_hook, setup_post_stop_repo):
    """.armature/tests/ must NOT be detected as a package-local test dir.

    The detection loop excludes .armature/ (governance dir). If only
    .armature/tests/ exists and no other <pkg>/tests/, post-stop must emit SKIP.
    """
    repo = setup_post_stop_repo()
    marker = repo / ".armature" / ".code-dirty"
    marker.touch()

    # The baseline already has .armature/ — ensure no other pkg/tests/ exists.
    # (setup_post_stop_repo does not create a tests/ dir at root or in a package.)
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0
    assert "SKIP" in result.stdout
    assert "No test runner detected" in result.stdout


def test_code_dirty_package_local_pytest_scoped_to_pkg(run_hook, setup_post_stop_repo):
    """pytest must be scoped to the detected package tests/, not the whole repo.

    If pytest were run from repo root without a path argument it would collect
    otherdir/__tests__/somefile.py, which contains non-pytest code and would
    cause a collection error. Scoping to mypkg/tests avoids that.
    """
    repo = setup_post_stop_repo()
    marker = repo / ".armature" / ".code-dirty"
    marker.touch()

    # Package with a passing test
    pkg_tests = repo / "mypkg" / "tests"
    pkg_tests.mkdir(parents=True)
    (pkg_tests / "__init__.py").write_text("")
    (pkg_tests / "test_simple.py").write_text("def test_pass(): assert True\n")

    # A sibling directory with jest-shaped content that would break pytest collection
    # if accidentally collected (no def test_ functions, wrong structure)
    sibling_tests = repo / "otherdir" / "__tests__"
    sibling_tests.mkdir(parents=True)
    # Write a JS-style test file that would cause a Python SyntaxError if collected
    (sibling_tests / "somefile.py").write_text(
        "describe('suite', () => { it('works', () => {}); });\n"
    )

    result = run_hook("post-stop.sh", "", cwd=str(repo))
    # pytest scoped to mypkg/tests must pass; if it collected otherdir/ it would fail
    assert result.returncode == 0, (
        f"Expected exit 0; pytest must be scoped to mypkg/tests, not the whole repo. "
        f"stdout={result.stdout[-400:]!r} stderr={result.stderr[-400:]!r}"
    )


def test_code_dirty_monorepo_workspace_packages_detected(run_hook, setup_post_stop_repo):
    """Monorepo `packages/<pkg>/tests/` layout must be detected at two levels.

    Without this, a Python edit under `packages/foo/` would fall through to
    npm/make (or report no runner) because the one-level detector checked
    only `packages/tests/`. Same logic applies to `apps/` and `services/`
    workspace roots — see the post-stop.sh detection comment.
    """
    repo = setup_post_stop_repo()
    marker = repo / ".armature" / ".code-dirty"
    marker.touch()

    pkg_tests = repo / "packages" / "foo" / "tests"
    pkg_tests.mkdir(parents=True)
    (pkg_tests / "__init__.py").write_text("")
    (pkg_tests / "test_simple.py").write_text("def test_pass(): assert True\n")

    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0, (
        f"Monorepo packages/<pkg>/tests/ must be detected and pytest scoped to it. "
        f"stdout={result.stdout[-400:]!r} stderr={result.stderr[-400:]!r}"
    )
    # If the detector did NOT find the workspace, pytest would have either
    # run against the whole repo (collecting nothing → "no tests ran") or
    # been skipped entirely. Successful pytest pass confirms detection.
    assert "PASS: Application smoke tests passed" in result.stdout


def test_code_dirty_monorepo_workspace_apps_detected(run_hook, setup_post_stop_repo):
    """Monorepo `apps/<app>/tests/` layout must be detected at two levels."""
    repo = setup_post_stop_repo()
    marker = repo / ".armature" / ".code-dirty"
    marker.touch()

    app_tests = repo / "apps" / "web" / "tests"
    app_tests.mkdir(parents=True)
    (app_tests / "__init__.py").write_text("")
    (app_tests / "test_simple.py").write_text("def test_pass(): assert True\n")

    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0, (
        f"Monorepo apps/<app>/tests/ must be detected. "
        f"stdout={result.stdout[-400:]!r} stderr={result.stderr[-400:]!r}"
    )


def test_code_dirty_docs_tests_skipped_like_armature(run_hook, setup_post_stop_repo):
    """docs/tests/*.py is documentation test tooling (governance), not
    application code. mark-dirty.sh excludes docs/* from .code-dirty
    activation; the post-stop pytest probe must mirror that classification
    so it does not select docs/tests as the application smoke target.

    Without this, an application edit (which sets .code-dirty) plus a
    repo that has docs/tests/ but no real tests/ would route to
    docs/tests and either block Stop on doc-test failures or give a
    false PASS without exercising the actual app code path.
    """
    repo = setup_post_stop_repo()
    marker = repo / ".armature" / ".code-dirty"
    marker.touch()

    # Documentation test tooling — must NOT be treated as the app target.
    docs_tests = repo / "docs" / "tests"
    docs_tests.mkdir(parents=True)
    (docs_tests / "__init__.py").write_text("")
    (docs_tests / "test_doc.py").write_text("def test_pass(): assert True\n")

    result = run_hook("post-stop.sh", "", cwd=str(repo))
    # No other test runner available; hook should report SKIP rather
    # than running docs/tests.
    assert result.returncode == 0, (
        f"docs/tests/ must be skipped like .armature/tests/; got exit "
        f"{result.returncode}; stdout={result.stdout[-400:]!r}"
    )
    assert "SKIP: No test runner detected" in result.stdout, (
        f"Expected SKIP from no-runner branch (docs/tests excluded); "
        f"got stdout={result.stdout!r}"
    )


def test_code_dirty_jest_only_tests_dir_falls_through_to_npm(run_hook, setup_post_stop_repo):
    """A package-local `tests/` containing only Jest/TS files (no .py)
    must NOT trigger the pytest branch — pytest would exit 5 (no tests
    collected) and fail the smoke check, blocking the Stop hook on a
    JS-only repo that has a working npm runner.

    The Python-files gate (added in cycle 3 of PR #25 review) lets the
    detector fall through to npm.test when no .py files are present
    under tests/."""
    repo = setup_post_stop_repo()
    marker = repo / ".armature" / ".code-dirty"
    marker.touch()

    # JS-only test dir under a top-level package
    js_pkg = repo / "frontend"
    js_pkg.mkdir(parents=True)
    js_tests = js_pkg / "tests"
    js_tests.mkdir()
    (js_tests / "thing.test.ts").write_text(
        "describe('suite', () => { it('works', () => {}); });\n"
    )
    # Provide a package.json with a 'test' script so the npm branch
    # succeeds. The script does nothing (echo) so the smoke check passes.
    (repo / "package.json").write_text(
        '{"name":"r","version":"0.0.0","scripts":{"test":"echo no-op"}}\n'
    )

    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0, (
        f"JS-only tests/ must fall through to npm runner; got exit "
        f"{result.returncode}; stdout={result.stdout[-400:]!r}"
    )
    # Confirm the npm branch ran, not the pytest branch
    assert "via npm" in result.stdout, (
        f"Expected npm runner; got stdout={result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# MUST: .code-dirty absent → "SKIP: No application code changes detected"
# ---------------------------------------------------------------------------

def test_no_code_dirty_emits_no_app_changes_skip(run_hook, setup_post_stop_repo):
    """When .code-dirty is absent, hook must emit the 'no changes' SKIP message."""
    repo = setup_post_stop_repo()
    marker = repo / ".armature" / ".code-dirty"
    if marker.exists():
        marker.unlink()
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0
    assert "SKIP" in result.stdout
    assert "No application code changes detected" in result.stdout


# ---------------------------------------------------------------------------
# SHOULD: bad CODEX.md route → exit 1
# ---------------------------------------------------------------------------

def test_bad_codex_md_route_exits_one(run_hook, setup_post_stop_repo):
    """A CODEX.md referencing a non-existent agents.md must exit 1."""
    repo = setup_post_stop_repo()
    codex_md = repo / "CODEX.md"
    existing = codex_md.read_text()
    codex_md.write_text(
        existing + "\n| Ghost Scope | `.ghost/agents.md` | ADR-0001 |\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 1
    assert "FAIL" in result.stdout


# ---------------------------------------------------------------------------
# SHOULD: CODEX.md absent → CODEX check silently skipped (exit 0 unaffected)
# ---------------------------------------------------------------------------

def test_codex_md_absent_does_not_cause_failure(run_hook, setup_post_stop_repo):
    """When CODEX.md doesn't exist, the CODEX route check must be silently skipped."""
    repo = setup_post_stop_repo()
    codex_md = repo / "CODEX.md"
    if codex_md.exists():
        codex_md.unlink()
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# SHOULD: uncommitted governance file changes → WARN in output, exit 0 (not FAIL)
# ---------------------------------------------------------------------------

def test_uncommitted_governance_changes_warns_not_fails(run_hook, setup_post_stop_repo):
    """Uncommitted governance file changes must produce WARN, not FAIL (exit 0)."""
    repo = setup_post_stop_repo()
    # Modify agents.md without committing — this triggers the governance diff check
    agents_file = repo / ".armature" / "agents.md"
    agents_file.write_text(
        "---\nscope: .armature\nadrs: [ADR-0001, ADR-0002]\n---\n\n# Modified\n"
    )
    # Modify the docs/adr files to match the references (so check 5 still passes)
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    # Must exit 0 (WARN is not FAIL)
    assert result.returncode == 0
    # Must emit WARN
    assert "WARN" in result.stdout


# ---------------------------------------------------------------------------
# MUST: GC removes stale correlation file (>24h) and emits WARN
# ---------------------------------------------------------------------------

def test_gc_removes_stale_correlation_file(run_hook, setup_post_stop_repo):
    """A .json file in active-delegations/ older than 24h must be removed with a WARN log."""
    repo = setup_post_stop_repo()
    deleg_dir = repo / ".armature" / "session" / "active-delegations"
    deleg_dir.mkdir(parents=True, exist_ok=True)
    stale_file = deleg_dir / "stale_abc123.json"
    stale_file.write_text('{"prompt_hash": "abc123", "criteria_items": []}')
    # Set mtime to 25 hours ago
    stale_mtime = time.time() - 25 * 3600
    os.utime(str(stale_file), (stale_mtime, stale_mtime))

    result = run_hook("post-stop.sh", "", cwd=str(repo))

    assert result.returncode == 0
    assert not stale_file.exists(), "Stale correlation file must be removed by GC"
    assert "WARN" in result.stdout
    assert "stale_abc123.json" in result.stdout


# ---------------------------------------------------------------------------
# MUST: GC preserves recent correlation file (<1h) with no WARN about it
# ---------------------------------------------------------------------------

def test_gc_preserves_recent_correlation_file(run_hook, setup_post_stop_repo):
    """A .json file in active-delegations/ younger than 24h must not be removed."""
    repo = setup_post_stop_repo()
    deleg_dir = repo / ".armature" / "session" / "active-delegations"
    deleg_dir.mkdir(parents=True, exist_ok=True)
    recent_file = deleg_dir / "recent_def456.json"
    recent_file.write_text('{"prompt_hash": "def456", "criteria_items": []}')
    # Set mtime to 1 hour ago (well within the 24h threshold)
    recent_mtime = time.time() - 1 * 3600
    os.utime(str(recent_file), (recent_mtime, recent_mtime))

    result = run_hook("post-stop.sh", "", cwd=str(repo))

    assert result.returncode == 0
    assert recent_file.exists(), "Recent correlation file must be preserved by GC"
    assert "recent_def456.json" not in result.stdout


# ---------------------------------------------------------------------------
# MUST: GC handles empty active-delegations directory without error
# ---------------------------------------------------------------------------

def test_gc_handles_empty_active_delegations(run_hook, setup_post_stop_repo):
    """An empty active-delegations/ directory must cause no error or crash."""
    repo = setup_post_stop_repo()
    deleg_dir = repo / ".armature" / "session" / "active-delegations"
    deleg_dir.mkdir(parents=True, exist_ok=True)

    result = run_hook("post-stop.sh", "", cwd=str(repo))

    assert result.returncode == 0


# ---------------------------------------------------------------------------
# SHOULD: GC handles missing active-delegations directory without error
# ---------------------------------------------------------------------------

def test_gc_handles_missing_active_delegations(run_hook, setup_post_stop_repo):
    """When active-delegations/ does not exist at all, post-stop must exit 0."""
    repo = setup_post_stop_repo()
    deleg_dir = repo / ".armature" / "session" / "active-delegations"
    # Ensure the directory does not exist
    if deleg_dir.exists():
        import shutil
        shutil.rmtree(str(deleg_dir))

    result = run_hook("post-stop.sh", "", cwd=str(repo))

    assert result.returncode == 0


# ---------------------------------------------------------------------------
# ci.yaml schema validation tests (Step 14, CP3)
# ---------------------------------------------------------------------------

def test_post_stop_ci_yaml_valid_passes(run_hook, setup_post_stop_repo):
    """A valid ci.yaml must produce a PASS line and exit 0."""
    repo = setup_post_stop_repo()
    ci_yaml = repo / ".armature" / "ci.yaml"
    ci_yaml.write_text(
        "test:\n"
        "  command: 'python -m pytest'\n"
        "  timeout_seconds: 60\n"
        "types:\n"
        "  command: null\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0
    assert "PASS: .armature/ci.yaml schema valid" in result.stdout


def test_post_stop_ci_yaml_command_wrong_type_fails(run_hook, setup_post_stop_repo):
    """ci.yaml with command as integer must produce a FAIL line and exit non-zero."""
    repo = setup_post_stop_repo()
    ci_yaml = repo / ".armature" / "ci.yaml"
    ci_yaml.write_text(
        "test:\n"
        "  command: 42\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode != 0
    assert "FAIL" in result.stdout


def test_post_stop_ci_yaml_unknown_top_level_key_fails(run_hook, setup_post_stop_repo):
    """ci.yaml with an unknown top-level key must produce a FAIL line and exit non-zero."""
    repo = setup_post_stop_repo()
    ci_yaml = repo / ".armature" / "ci.yaml"
    ci_yaml.write_text(
        "test:\n"
        "  command: 'pytest'\n"
        "deploy:\n"
        "  command: 'make deploy'\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode != 0
    assert "FAIL" in result.stdout
    assert "unknown top-level keys" in result.stdout


def test_post_stop_ci_yaml_absent_skips(run_hook, setup_post_stop_repo):
    """When ci.yaml is absent, post-stop must emit a SKIP message and exit 0."""
    repo = setup_post_stop_repo()
    ci_yaml = repo / ".armature" / "ci.yaml"
    # Ensure ci.yaml does not exist
    if ci_yaml.exists():
        ci_yaml.unlink()
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0
    assert "SKIP: .armature/ci.yaml not present" in result.stdout


def test_post_stop_ci_yaml_negative_timeout_fails(run_hook, setup_post_stop_repo):
    """ci.yaml with timeout_seconds: -1 must produce a FAIL line and exit non-zero."""
    repo = setup_post_stop_repo()
    ci_yaml = repo / ".armature" / "ci.yaml"
    ci_yaml.write_text(
        "test:\n"
        "  command: 'pytest'\n"
        "  timeout_seconds: -1\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode != 0
    assert "FAIL" in result.stdout
    assert "must be positive integer" in result.stdout


# ---------------------------------------------------------------------------
# AGENTS.md case-insensitive adapter route check
# ---------------------------------------------------------------------------

def test_adapter_route_check_extracts_bare_root_agents_in_table(
    run_hook, setup_post_stop_repo
):
    """Route grep must extract bare `agents.md` / `AGENTS.md` when it
    appears inside a markdown table row (legitimate root-level governance
    route), but NOT when it appears in prose (documentation mention).

    The path-style pattern requires '/' before the filename, which
    excludes prose mentions like 'Codex reads `AGENTS.md` by default'.
    The complementary bare-filename pattern is gated to lines that look
    like markdown table rows (start with '|') so a routing table
    entry like `| Root | `agents.md` | ADR-0001 |` is still matched.

    Positive signal: point the bare-table reference at a missing file
    and assert the FAIL surfaces. Without the bare-table extraction
    branch, the reference is silently skipped and this test fails.
    """
    repo = setup_post_stop_repo()
    # Reference a missing root-level governance file via a table row only.
    claude_md = repo / "CLAUDE.md"
    existing = claude_md.read_text()
    claude_md.write_text(
        existing
        + "\n| Missing Root | `missing-root-agents.md` | ADR-0001 |\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 1, (
        f"Expected exit 1 (bare-table route must be extracted and validated); "
        f"got {result.returncode}. stdout={result.stdout[-400:]!r}"
    )
    assert "FAIL" in result.stdout
    assert "missing-root-agents.md" in result.stdout


def test_adapter_route_check_skips_table_header_label(
    run_hook, setup_post_stop_repo
):
    """The bare-filename pattern must NOT match column LABELS in markdown
    table headers. The documented CODEX/CLAUDE routing-table format uses
    `| Scope | \\`agents.md\\` | ADRs | ... |` as the header, with the
    bare \\`agents.md\\` token there being a column name, not a route.

    Detection rule: a header row is the line immediately preceding a
    separator row of the form `|---|---|...|` (optional ':' for
    alignment). Such header lines are dropped from extraction.
    """
    repo = setup_post_stop_repo()
    claude_md = repo / "CLAUDE.md"
    # A complete markdown table: header (with bare `agents.md` as column
    # label), separator, and one valid data row pointing to the existing
    # .armature/agents.md (which setup_post_stop_repo creates).
    table = (
        "\n## Test Routing\n\n"
        "| Scope | `agents.md` | ADRs | Implementer |\n"
        "|---|---|---|---|\n"
        "| Specification | `.armature/agents.md` | ADR-0001 | impl |\n"
    )
    claude_md.write_text(claude_md.read_text() + table)
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    # If the header label `agents.md` were mis-extracted as a route, the
    # hook would FAIL because no root-level agents.md exists. The header-
    # skip awk pass drops it; only `.armature/agents.md` (path-style) is
    # extracted and validated.
    assert result.returncode == 0, (
        f"Header-row column label must NOT be extracted as a route. "
        f"got exit {result.returncode}; stdout={result.stdout[-400:]!r}"
    )
    # Path-style entry should have validated successfully
    assert "PASS: CLAUDE.md routing references resolve" in result.stdout


def test_adapter_route_check_extracts_indented_table_route(
    run_hook, setup_post_stop_repo
):
    """The bare-table extraction must accept tables indented with leading
    whitespace (common in nested-list contexts where a routing table
    appears under a bullet point). The header-stripping awk already
    allows '^[[:space:]]*\\|...' so the grep must too, otherwise an
    indented routing table is silently skipped and a missing root
    governance file reports SKIP instead of FAIL.
    """
    repo = setup_post_stop_repo()
    claude_md = repo / "CLAUDE.md"
    # Indented routing table (2-space indent — common for nested-list
    # context). Header + separator + data row, all indented uniformly.
    # Data-row filename ends in 'agents.md' so the bare-filename pattern
    # `[^`/]*agents\.md` matches it.
    table = (
        "\n## Indented Test\n\n"
        "  | Scope | `agents.md` | ADRs |\n"
        "  |---|---|---|\n"
        "  | Missing Root | `missing-indented-agents.md` | ADR-0001 |\n"
    )
    claude_md.write_text(claude_md.read_text() + table)
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    # missing-indented-agents.md does not exist; with indented support
    # it is extracted and reported as FAIL.
    assert result.returncode == 1, (
        f"Indented routing table must be extracted; missing route should "
        f"FAIL. got exit {result.returncode}; stdout={result.stdout[-400:]!r}"
    )
    assert "FAIL" in result.stdout
    assert "missing-indented-agents.md" in result.stdout


def test_adapter_route_check_skips_bare_prose_mention(
    run_hook, setup_post_stop_repo
):
    """Route grep must NOT treat a bare-filename mention in narrative prose
    as a routing-table entry.

    CODEX.md line 12 historically said 'Codex will only read `AGENTS.md`
    and `AGENTS.override.md`' — a documentation string, not a route.
    Before the dual-pattern fix, `grep -oEi` matched it and post-stop
    reported FAIL: AGENTS.md does not exist. The bare-filename branch
    is now gated to markdown table rows, so prose mentions are skipped.
    """
    repo = setup_post_stop_repo()
    claude_md = repo / "CLAUDE.md"
    existing = claude_md.read_text()
    # Bare backtick mention in narrative paragraph (NOT in a table row).
    claude_md.write_text(
        existing
        + "\n\nNote: this hook will only read `nonexistent-prose-agents.md`"
        " when invoked with --legacy mode.\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    # If the prose mention were extracted as a route, post-stop would FAIL
    # because nonexistent-prose-agents.md does not exist.
    assert result.returncode == 0, (
        f"Prose mention of bare filename must be skipped, not validated; "
        f"got exit {result.returncode}. stdout={result.stdout[-400:]!r}"
    )
    assert "nonexistent-prose-agents.md" not in result.stdout, (
        f"Prose mention should not appear as a FAIL; got stdout={result.stdout!r}"
    )


def test_adapter_route_check_case_insensitive_extracts_route(
    run_hook, setup_post_stop_repo
):
    """check_adapter_routes must extract mixed-case AGENTS.md references.

    The grep in check_adapter_routes uses -i (case-insensitive) so that
    route entries written as AGENTS.md or Agents.md are extracted from
    the routing table. Without -i the original regex (lowercase
    `agents\\.md` only) silently skipped uppercase entries.

    Positive-signal strategy (per PR #24 cycle-3 review): point the
    mixed-case route at a file that does NOT exist on disk. With -i,
    the grep extracts the route, post-stop.sh checks the file, finds
    it missing, and emits a FAIL referencing the scope (here:
    'ci_scope_missing'). Without -i, the route is NOT extracted, no
    check runs, no FAIL is emitted — and this test fails because the
    asserted FAIL message is absent. This positive-signal pattern
    catches a silent-extraction-regression that the prior absence-of-
    FAIL assertion would have missed.

    Deterministic on case-sensitive filesystems (Linux ext4 CI) and
    case-insensitive filesystems (Windows NTFS, macOS HFS+): we do
    not write any file under ci_scope_missing/ so the FS-level case
    resolution is irrelevant.
    """
    repo = setup_post_stop_repo()
    # Deliberately do NOT create ci_scope_missing/AGENTS.md on disk.
    claude_md = repo / "CLAUDE.md"
    existing = claude_md.read_text()
    claude_md.write_text(
        existing
        + "\n| CI Scope Missing | `ci_scope_missing/AGENTS.md` | ADR-0001 |\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    # check_adapter_routes emits EXIT_CODE=1 when a referenced path is
    # missing. Hook exit reflects EXIT_CODE; we expect 1.
    assert result.returncode == 1, (
        f"Expected exit 1 (missing route target); got {result.returncode}. "
        f"With -i on the grep, the uppercase AGENTS.md route IS extracted "
        f"and the missing file IS detected and reported as FAIL. Without -i, "
        f"the route is silently skipped and this assertion would catch the "
        f"regression. stdout={result.stdout[-400:]!r}"
    )
    # Positive signal: the FAIL message names the mixed-case scope, proving
    # the -i grep matched and the file existence check ran.
    assert "FAIL" in result.stdout
    assert "ci_scope_missing" in result.stdout


# ---------------------------------------------------------------------------
# DRIFT-001: Invariant-ID resolution check (post-stop.sh section 9)
# ---------------------------------------------------------------------------

def test_drift001_clean_baseline_emits_pass(run_hook, setup_post_stop_repo):
    """Baseline repo (TEST-001 registered, ADR-0001/0002 allowlisted) must
    PASS section 9 and emit the invariant-ID resolution PASS message."""
    repo = setup_post_stop_repo()
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0
    assert "PASS: invariant-ID resolution" in result.stdout


def test_drift001_unknown_invariant_id_in_armature_md_fails(
    run_hook, setup_post_stop_repo
):
    """An invariant-shaped token cited in a governed .armature/*.md doc that
    is neither registered nor allowlisted must FAIL with exit 1 and emit a
    targeted message naming the file, line, and unknown token."""
    repo = setup_post_stop_repo()
    # FOO-999 is not in registry (only TEST-001 is) and matches no allowlist
    # pattern. Write into a fresh governed markdown so the scan finds it.
    (repo / ".armature" / "drift_test.md").write_text(
        "# Drift Test\n\nThis cites FOO-999 which does not exist.\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    assert "FOO-999" in result.stdout
    assert "drift_test.md" in result.stdout


def test_drift001_allowlisted_token_passes(run_hook, setup_post_stop_repo):
    """Tokens matching universal allowlist patterns (ADR refs, PR refs,
    severity codes, technical standards, illustrative SEQ/DIGEST IDs) must
    NOT trigger a violation even when absent from the registry."""
    repo = setup_post_stop_repo()
    (repo / ".armature" / "allowlist_test.md").write_text(
        "# Allowlist Test\n\n"
        "- ADR ref: ADR-0042\n"
        "- PR ref: PR-12345\n"
        "- Checkpoint: CP-3 and CP12\n"
        "- Cycle: CYCLE-2\n"
        "- Severity: CRITICAL-1 HIGH-2 MEDIUM-3 LOW-4\n"
        "- Standards: AES-256 SHA-256 IEEE-754 UTF-8 PEP-440\n"
        "- Illustrative: SEQ-001 DIGEST-002\n"
    )
    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0
    assert "PASS: invariant-ID resolution" in result.stdout


def test_drift001_ephemeral_dirs_excluded_from_scan(
    run_hook, setup_post_stop_repo
):
    """Tokens inside ephemeral .armature/ subtrees (session/, escalations/,
    reviews/, postmortems/) must NOT trigger a violation — those areas hold
    per-task or transient content with finding codes scoped to one PR."""
    repo = setup_post_stop_repo()
    # Each excluded dir gets an unknown invariant ID that would FAIL if scanned.
    reviews_dir = repo / ".armature" / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    (reviews_dir / "verdict.md").write_text("# Verdict\n\nFinding XYZQ-001.\n")

    postmortems_dir = repo / ".armature" / "postmortems"
    postmortems_dir.mkdir(parents=True, exist_ok=True)
    (postmortems_dir / "incident.md").write_text("# Incident\n\nROOT-555 caused outage.\n")

    escalations_dir = repo / ".armature" / "escalations"
    escalations_dir.mkdir(parents=True, exist_ok=True)
    (escalations_dir / "package.md").write_text("# Escalation\n\nSee BLOCKER-7.\n")

    session_dir = repo / ".armature" / "session"
    (session_dir / "state.md").write_text("# State\n\nActive: WIPID-123.\n")

    result = run_hook("post-stop.sh", "", cwd=str(repo))
    assert result.returncode == 0
    assert "PASS: invariant-ID resolution" in result.stdout
    # And no FAIL pointing at any of the excluded subtree files
    assert "XYZQ-001" not in result.stdout
    assert "ROOT-555" not in result.stdout
    assert "BLOCKER-7" not in result.stdout
    assert "WIPID-123" not in result.stdout
