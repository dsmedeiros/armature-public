"""
Tests for cascade-ci.sh (DRIFT-002 authoritative CI backstop).

cascade-ci.sh runs check-cascade.sh per-commit over a commit range against the
ACTUAL committed changeset — the layer that catches a cascade-violating commit
regardless of how it was produced (the PreToolUse gate cannot, e.g.
edit-before-stage). Exit 0 = PASS/SKIP, exit 2 = a commit violates a blocking
cascade rule.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

BASH_BIN = shutil.which("bash")
if BASH_BIN is None:
    pytest.skip("bash not available on PATH", allow_module_level=True)


_RULES = """\
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


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)


@pytest.fixture()
def ci_repo(tmp_path, repo_root):
    repo = tmp_path / "ci_repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    armature_dir = repo / ".armature"
    hooks_dir = armature_dir / "hooks"
    hooks_dir.mkdir(parents=True)
    for hook in ("check-cascade.sh", "cascade-ci.sh"):
        shutil.copy(str(repo_root / ".armature" / "hooks" / hook),
                    str(hooks_dir / hook))
    (armature_dir / "cascade-rules.yaml").write_text(_RULES, encoding="utf-8")
    (repo / "schemas").mkdir()
    (repo / "docs").mkdir()
    (repo / "schemas" / "thing.schema.json").write_text("{}\n")
    (repo / "docs" / "thing.md").write_text("# thing\n")
    (repo / "README.md").write_text("# repo\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")

    def run_ci(rng=None):
        args = [BASH_BIN, str(hooks_dir / "cascade-ci.sh")]
        if rng is not None:
            args.append(rng)
        env = os.environ.copy()
        env["ARMATURE_DIR"] = str(armature_dir)
        return subprocess.run(args, capture_output=True, text=True, timeout=30,
                              cwd=str(repo), env=env)

    return repo, run_ci


def test_clean_range_passes(ci_repo):
    repo, run_ci = ci_repo
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    # One commit touching trigger + companion together → passes.
    (repo / "schemas" / "thing.schema.json").write_text('{"v":1}\n')
    (repo / "docs" / "thing.md").write_text("# v1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "trigger + companion")
    result = run_ci(f"{base}..HEAD")
    assert result.returncode == 0, result.stderr


def test_split_across_commits_is_caught(ci_repo):
    repo, run_ci = ci_repo
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    # The bypass the PreToolUse gate cannot catch: trigger in commit A,
    # companion in a LATER commit B. The union would pass, but per-commit
    # backstop must FAIL on commit A.
    (repo / "schemas" / "thing.schema.json").write_text('{"v":2}\n')
    _git(repo, "add", "schemas/thing.schema.json")
    _git(repo, "commit", "-m", "A: trigger only")
    (repo / "docs" / "thing.md").write_text("# v2\n")
    _git(repo, "add", "docs/thing.md")
    _git(repo, "commit", "-m", "B: companion only")
    result = run_ci(f"{base}..HEAD")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr or "violation" in result.stderr


def test_edit_before_stage_commit_is_caught(ci_repo):
    repo, run_ci = ci_repo
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    # Simulate the committed result of `printf > trigger && git add trigger &&
    # git commit` (no companion) — the exact form the PreToolUse gate misses.
    (repo / "schemas" / "thing.schema.json").write_text('{"v":3}\n')
    _git(repo, "add", "schemas/thing.schema.json")
    _git(repo, "commit", "-m", "trigger only, companion missing")
    result = run_ci(f"{base}..HEAD")
    assert result.returncode == 2


def test_unrelated_commits_pass(ci_repo):
    repo, run_ci = ci_repo
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "README.md").write_text("# edited\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "docs")
    result = run_ci(f"{base}..HEAD")
    assert result.returncode == 0


def test_missing_rules_file_skips(tmp_path, repo_root):
    repo = tmp_path / "norules"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    hooks_dir = repo / ".armature" / "hooks"
    hooks_dir.mkdir(parents=True)
    for hook in ("check-cascade.sh", "cascade-ci.sh"):
        shutil.copy(str(repo_root / ".armature" / "hooks" / hook),
                    str(hooks_dir / hook))
    (repo / "f.txt").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    env = os.environ.copy()
    env["ARMATURE_DIR"] = str(repo / ".armature")
    result = subprocess.run(
        [BASH_BIN, str(hooks_dir / "cascade-ci.sh"), "HEAD"],
        capture_output=True, text=True, timeout=30, cwd=str(repo), env=env,
    )
    assert result.returncode == 0
    assert "SKIP" in result.stdout
