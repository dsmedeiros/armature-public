"""
Shared fixtures and infrastructure for Armature hook tests.

JSON payload shapes verified against each hook's stdin parsing:
  block-dangerous-commands.sh : data.get('tool_input', {}).get('command', '')
  mark-dirty.sh               : data.get('tool_input', {}).get('file_path', '')
  block-config-changes.sh     : data.get('source', '')
  inject-context.sh           : data.get('file'|'path'|'scope'|'cwd'|'workingDirectory')
  check-required-reading.sh   : payload.get('tool_input', {}).get('file_path')
                                  or payload.get('file_path')
  reinject-context.sh         : does not read stdin (informational only)
  post-stop.sh                : does not read stdin
"""

import os
import shutil
import subprocess
from pathlib import Path
import pytest

# ---------------------------------------------------------------------------
# Windows / bash availability guard
# Resolve bash binary at import time; skip the whole module if absent.
# ---------------------------------------------------------------------------
BASH_BIN = shutil.which("bash")
if BASH_BIN is None:
    pytest.skip("bash not available on PATH", allow_module_level=True)


# ---------------------------------------------------------------------------
# REPO_ROOT — session-scoped fixture
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the absolute path to the repository root."""
    raw = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
    ).strip()
    return Path(raw)


# ---------------------------------------------------------------------------
# run_hook helper — available as a fixture so tests can call it concisely
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def run_hook(repo_root):
    """
    Return a callable that runs a hook script with JSON on stdin.

    Usage:
        result = run_hook("block-dangerous-commands.sh", bash_event("echo hi"))
        assert result.returncode == 0
    """

    def _run(
        hook_name: str,
        stdin_json: str,
        env_overrides: dict | None = None,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess:
        hook_path = repo_root / ".armature" / "hooks" / hook_name
        assert hook_path.exists(), (
            f"Hook script not found: {hook_path}\n"
            f"Available hooks: {list((repo_root / '.armature' / 'hooks').glob('*.sh'))}"
        )

        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)

        return subprocess.run(
            [BASH_BIN, str(hook_path)],
            input=stdin_json,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd or str(repo_root),
            timeout=10,
        )

    return _run


# ---------------------------------------------------------------------------
# tmp_armature fixture — isolated temp git repo with hooks copied in
# ---------------------------------------------------------------------------
@pytest.fixture()
def tmp_armature(tmp_path, repo_root):
    """
    Create a minimal temporary git repository that mirrors the .armature/
    directory structure, with real hook scripts copied in.

    Returns tmp_path (a Path). Cleaned up automatically by pytest.
    """
    # Initialise git repo
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
        cwd=str(tmp_path),
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        check=True,
        capture_output=True,
        cwd=str(tmp_path),
    )
    # Need at least one commit so `git diff --name-only HEAD` doesn't error
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
        cwd=str(tmp_path),
    )

    # Create expected directory structure
    armature_dir = tmp_path / ".armature"
    (armature_dir / "session").mkdir(parents=True)
    (armature_dir / "invariants").mkdir(parents=True)
    hooks_dir = armature_dir / "hooks"
    hooks_dir.mkdir(parents=True)

    # Copy hook scripts from real repo into temp repo
    real_hooks_dir = repo_root / ".armature" / "hooks"
    for hook_file in real_hooks_dir.glob("*.sh"):
        shutil.copy(str(hook_file), str(hooks_dir / hook_file.name))

    # Copy the shared hooks lib so refactored hooks (e.g. auto-reviewer.sh)
    # can import red_team_check.py in isolated test repos.  The lib is also
    # committed below so its files are tracked rather than untracked — this
    # prevents the LOC trigger in evaluate_red_team from counting lib bytes
    # as "untracked changes" and falsely firing red-team=true in tests.
    real_lib_dir = real_hooks_dir / "lib"
    if real_lib_dir.is_dir():
        shutil.copytree(str(real_lib_dir), str(hooks_dir / "lib"))

    # Commit all copied files so they are tracked.  Without this, hook scripts
    # and lib files are untracked in the temp repo; red_team_check.evaluate_red_team
    # counts untracked file lines toward the LOC threshold and would falsely trigger
    # red-team=true for any test that uses tmp_armature.
    subprocess.run(
        ["git", "add", "."],
        check=True,
        capture_output=True,
        cwd=str(tmp_path),
    )
    subprocess.run(
        ["git", "commit", "-m", "add hooks"],
        check=True,
        capture_output=True,
        cwd=str(tmp_path),
    )

    return tmp_path


# ---------------------------------------------------------------------------
# setup_post_stop_repo fixture — produces a minimal valid baseline git repo
# for post-stop.sh test isolation.
#
# Design:
#   The baseline satisfies every post-stop.sh check so that individual tests
#   can make a single targeted mutation to trigger the failure they are testing,
#   without worrying about other checks interfering.
#
#   Baseline contents:
#     CLAUDE.md         — references `.armature/agents.md` (valid path)
#     CODEX.md          — references `.armature/agents.md` (valid path)
#     .armature/
#       invariants/
#         registry.yaml — minimal valid YAML (one active invariant)
#       hooks/          — all hook scripts copied from real repo
#       session/        — directory only (no state.md)
#     docs/adr/
#       0001-baseline.md  — resolves ADR-0001 references
#       0002-baseline.md  — resolves ADR-0002 references
#     .armature/agents.md — frontmatter with adrs: [ADR-0001, ADR-0002]
#
#   Note: no tests/ directory at root → no test runner detected (SKIP path).
# ---------------------------------------------------------------------------

_BASELINE_REGISTRY = """\
invariants:
  TEST-001:
    name: "Baseline test invariant"
    severity: standard
    rule: "Baseline rule for testing."
    status: active
"""

_BASELINE_CLAUDE_MD = """\
# Test CLAUDE.md

## Routing Table

| Scope | agents.md | ADRs | Implementer |
|-------|-----------|------|-------------|
| Specification | `.armature/agents.md` | ADR-0001 | spec-impl |
"""

_BASELINE_CODEX_MD = """\
# Test CODEX.md

## Routing Table

| Scope | agents.md | ADRs |
|-------|-----------|------|
| Specification | `.armature/agents.md` | ADR-0001 |
"""

_BASELINE_AGENTS_MD = """\
---
scope: .armature
governs: Test scope
adrs: [ADR-0001, ADR-0002]
---

# Test Scope
"""


@pytest.fixture()
def setup_post_stop_repo(tmp_path, repo_root):
    """
    Return a factory that creates a minimal valid baseline git repo for post-stop.sh tests.

    Usage:
        def test_something(run_hook, setup_post_stop_repo):
            repo = setup_post_stop_repo()
            # mutate repo files as needed
            result = run_hook("post-stop.sh", "", cwd=str(repo))
            assert result.returncode == ...

    Each call to the factory returns a fresh clone of the baseline so individual
    tests are isolated from one another.
    """

    def _factory() -> Path:
        repo = tmp_path / "post_stop_test_repo"
        repo.mkdir(exist_ok=True)

        # Initialise git repo
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

        # Baseline files
        (repo / "CLAUDE.md").write_text(_BASELINE_CLAUDE_MD)
        (repo / "CODEX.md").write_text(_BASELINE_CODEX_MD)
        (armature_dir / "invariants" / "registry.yaml").write_text(_BASELINE_REGISTRY)
        (armature_dir / "agents.md").write_text(_BASELINE_AGENTS_MD)
        (adr_dir / "0001-baseline.md").write_text("# ADR-0001 Baseline\n")
        (adr_dir / "0002-baseline.md").write_text("# ADR-0002 Baseline\n")

        # Initial commit so `git diff --name-only HEAD` works
        subprocess.run(
            ["git", "add", "."],
            check=True, capture_output=True, cwd=str(repo),
        )
        subprocess.run(
            ["git", "commit", "-m", "init baseline"],
            check=True, capture_output=True, cwd=str(repo),
        )

        return repo

    return _factory
