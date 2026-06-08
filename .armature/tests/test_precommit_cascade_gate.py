"""
Tests for precommit-cascade-gate.sh (DRIFT-002 PreToolUse(Bash) gate).

The gate receives Claude Code tool-input JSON on stdin, extracts the Bash
command, and — only for commit-producing git subcommands — delegates to
check-cascade.sh against the file set the command will actually commit. For
everything else (non-git commands, recovery flags, staging commands) it exits 0
so normal workflow is never blocked.

Exit codes:
  0  allow (not commit-producing, or commit passes cascade)
  2  block (commit fails cascade, or fail-closed: shell-wrapper / substitution)

Each test builds an isolated git repo with a cascade rule (schema → docs),
copies both hooks + cascade-rules.yaml in, optionally stages files, then pipes
a tool-input JSON envelope to the gate.
"""

import json
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
def gate_repo(tmp_path, repo_root):
    """
    Build an isolated git repo wired with the cascade gate + checker + rules.

    Returns (repo_path, run_gate) where run_gate(command_str) pipes the
    tool-input JSON for that Bash command into the gate and returns the
    CompletedProcess.
    """
    repo = tmp_path / "gate_repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")

    armature_dir = repo / ".armature"
    hooks_dir = armature_dir / "hooks"
    hooks_dir.mkdir(parents=True)
    for hook in ("check-cascade.sh", "precommit-cascade-gate.sh"):
        shutil.copy(
            str(repo_root / ".armature" / "hooks" / hook),
            str(hooks_dir / hook),
        )
    (armature_dir / "cascade-rules.yaml").write_text(_RULES, encoding="utf-8")

    # Seed tracked files so HEAD exists and the schema/docs paths are known.
    (repo / "schemas").mkdir()
    (repo / "docs").mkdir()
    (repo / "schemas" / "thing.schema.json").write_text("{}\n")
    (repo / "docs" / "thing.md").write_text("# thing\n")
    (repo / "README.md").write_text("# repo\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")

    gate_path = hooks_dir / "precommit-cascade-gate.sh"

    def run_gate(command_str: str) -> subprocess.CompletedProcess:
        payload = json.dumps({"tool_input": {"command": command_str}})
        env = os.environ.copy()
        env["ARMATURE_DIR"] = str(armature_dir)
        return subprocess.run(
            [BASH_BIN, str(gate_path)],
            input=payload,
            capture_output=True, text=True, timeout=20,
            cwd=str(repo),
            env=env,
        )

    return repo, run_gate


# ---------------------------------------------------------------------------
# Non-commit commands always pass through (exit 0)
# ---------------------------------------------------------------------------
def test_non_git_command_allowed(gate_repo):
    _, run_gate = gate_repo
    assert run_gate("echo hello").returncode == 0


def test_git_status_allowed(gate_repo):
    _, run_gate = gate_repo
    assert run_gate("git status").returncode == 0


def test_git_add_allowed(gate_repo):
    _, run_gate = gate_repo
    assert run_gate("git add schemas/thing.schema.json").returncode == 0


def test_empty_stdin_allowed(gate_repo):
    repo, _ = gate_repo
    gate = repo / ".armature" / "hooks" / "precommit-cascade-gate.sh"
    env = os.environ.copy()
    env["ARMATURE_DIR"] = str(repo / ".armature")
    result = subprocess.run([BASH_BIN, str(gate)], input="",
                            capture_output=True, text=True, timeout=20,
                            cwd=str(repo), env=env)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# git commit: blocks when cascade violated, allows when satisfied
# ---------------------------------------------------------------------------
def test_commit_with_violation_blocks(gate_repo):
    repo, run_gate = gate_repo
    # Stage ONLY the trigger; companion docs/thing.md not staged.
    (repo / "schemas" / "thing.schema.json").write_text('{"v":2}\n')
    _git(repo, "add", "schemas/thing.schema.json")
    result = run_gate("git commit -m 'change schema'")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


def test_commit_with_companion_allowed(gate_repo):
    repo, run_gate = gate_repo
    (repo / "schemas" / "thing.schema.json").write_text('{"v":2}\n')
    (repo / "docs" / "thing.md").write_text("# thing v2\n")
    _git(repo, "add", "schemas/thing.schema.json", "docs/thing.md")
    result = run_gate("git commit -m 'change schema + docs'")
    assert result.returncode == 0


def test_commit_unrelated_file_allowed(gate_repo):
    repo, run_gate = gate_repo
    (repo / "README.md").write_text("# repo edited\n")
    _git(repo, "add", "README.md")
    result = run_gate("git commit -m 'docs'")
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Compound command: `git add <trigger> && git commit` (index empty at gate time)
# ---------------------------------------------------------------------------
def test_compound_add_then_commit_blocks(gate_repo):
    repo, run_gate = gate_repo
    # Nothing staged yet; the gate must pre-flight the `git add` in the compound.
    (repo / "schemas" / "thing.schema.json").write_text('{"v":3}\n')
    result = run_gate("git add schemas/thing.schema.json && git commit -m x")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


# ---------------------------------------------------------------------------
# Recovery flags bypass the gate entirely (exit 0)
# ---------------------------------------------------------------------------
def test_rebase_abort_bypassed(gate_repo):
    _, run_gate = gate_repo
    assert run_gate("git rebase --abort").returncode == 0


def test_cherry_pick_abort_bypassed(gate_repo):
    _, run_gate = gate_repo
    assert run_gate("git cherry-pick --abort").returncode == 0


# ---------------------------------------------------------------------------
# Fail-closed: shell wrapper and substitution-as-executable with a commit verb
# ---------------------------------------------------------------------------
def test_shell_wrapper_with_commit_blocks(gate_repo):
    _, run_gate = gate_repo
    result = run_gate("bash -c 'git commit -m x'")
    assert result.returncode == 2
    assert "shell wrapper" in result.stderr.lower() or "FAIL" in result.stderr


def test_substitution_executable_with_commit_blocks(gate_repo):
    _, run_gate = gate_repo
    result = run_gate("$(which git) commit -m x")
    assert result.returncode == 2


def test_shell_wrapper_without_commit_allowed(gate_repo):
    _, run_gate = gate_repo
    # bash -c with no commit verb is clearly not commit-producing.
    assert run_gate("bash -c 'echo hello'").returncode == 0


# ---------------------------------------------------------------------------
# --no-commit opt-out: cherry-pick -n stages but does not commit → allowed
# ---------------------------------------------------------------------------
def test_cherry_pick_no_commit_optout_allowed(gate_repo):
    _, run_gate = gate_repo
    # -n means --no-commit for cherry-pick; no commit is produced, so even a
    # cascade-violating staged set must not block (the eventual commit will).
    result = run_gate("git cherry-pick -n someref")
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Regression: staged RENAME of a trigger file is caught (codex PR #34 P2).
# `git diff --cached --name-only` shows only the post-rename path; check-cascade
# uses --no-renames so the old (trigger) path is also in the changeset.
# ---------------------------------------------------------------------------
def test_commit_rename_of_trigger_blocks(gate_repo):
    repo, run_gate = gate_repo
    # Rename the trigger file; companion docs/thing.md not touched. A pure
    # rename must still trip the rule via the old (deleted) path.
    _git(repo, "mv", "schemas/thing.schema.json", "schemas/thing2.schema.json")
    result = run_gate("git commit -m 'rename schema'")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


def test_commit_dash_a_rename_of_trigger_blocks(gate_repo):
    """`git commit -a` after a staged rename of a trigger must still trip the
    rule (codex PR #34: the -a preflight now uses --no-renames so the deleted
    old path reaches check-cascade.sh)."""
    repo, run_gate = gate_repo
    _git(repo, "mv", "schemas/thing.schema.json", "schemas/thing2.schema.json")
    result = run_gate("git commit -a -m 'rename schema'")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


# ---------------------------------------------------------------------------
# Regression: --no-commit / opt-out detection must honour value-taking options.
# codex PR #34 P2: `git commit -m --no-commit` is a commit whose message is
# literally "--no-commit"; the old code wrongly treated --no-commit as an
# opt-out and skipped the cascade check.
# ---------------------------------------------------------------------------
def test_commit_dash_m_consumes_no_commit_as_value(gate_repo):
    repo, run_gate = gate_repo
    # Cascade violation: trigger staged, companion absent.
    (repo / "schemas" / "thing.schema.json").write_text('{"v":99}\n')
    _git(repo, "add", "schemas/thing.schema.json")
    # `--no-commit` is the value of the first `-m`; the second `-m msg` is the
    # real commit message. The gate must NOT treat `--no-commit` as a flag.
    result = run_gate("git commit -m --no-commit -m 'real msg'")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


# ---------------------------------------------------------------------------
# Regression: merge bypass-detection must honour value-taking options too.
# codex PR #34 P2: `git merge -m --squash topic` is a normal merge whose
# message is "--squash"; the old check wrongly treated it as a squash merge
# and skipped the cascade check.
# ---------------------------------------------------------------------------
def test_merge_dash_m_consumes_squash_as_value(gate_repo):
    repo, run_gate = gate_repo
    # Build a topic branch whose tip modifies the trigger without the companion,
    # then return to the original branch via `git checkout -` (portable across
    # default branch names like master/main).
    _git(repo, "checkout", "-b", "topic")
    (repo / "schemas" / "thing.schema.json").write_text('{"topic":1}\n')
    _git(repo, "add", "schemas/thing.schema.json")
    _git(repo, "commit", "-m", "topic edits trigger")
    _git(repo, "checkout", "-")
    result = run_gate("git merge -m --squash topic")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


# ---------------------------------------------------------------------------
# Regression: directory changes (`cd`) before a staging segment (codex PR #34).
# The gate tracks `cd`/`pushd` so a later `git add` is preflighted from the
# correct cwd; unresolvable cd (bare cd, cd -, popd, expanded target) before a
# staging command fails closed.
# ---------------------------------------------------------------------------
def test_compound_cd_subdir_then_add_blocks(gate_repo):
    repo, run_gate = gate_repo
    # `cd schemas` then `git add thing.schema.json` stages schemas/thing.schema.json
    # (the trigger); companion docs/thing.md absent → must block.
    (repo / "schemas" / "thing.schema.json").write_text('{"v":5}\n')
    result = run_gate("cd schemas && git add thing.schema.json && git commit -m x")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


def test_compound_cd_subdir_with_companion_allowed(gate_repo):
    repo, run_gate = gate_repo
    # Both trigger and companion staged from within schemas/ → must pass.
    (repo / "schemas" / "thing.schema.json").write_text('{"v":6}\n')
    (repo / "docs" / "thing.md").write_text("# v6\n")
    result = run_gate("cd schemas && git add thing.schema.json ../docs/thing.md && git commit -m x")
    assert result.returncode == 0


def test_compound_unresolvable_cd_then_add_fails_closed(gate_repo):
    repo, run_gate = gate_repo
    # `cd -` is unresolvable; a staging command then runs in an unknown cwd, so
    # the gate cannot determine the committed set → fail closed.
    result = run_gate("cd - && git add schemas/thing.schema.json && git commit -m x")
    assert result.returncode == 2
    assert "unresolvable" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Regression: `cd` before a PATHSPEC commit (codex PR #34). The commit segment
# itself must resolve its pathspecs against the prior `cd` cwd, not just the
# staging preflight.
# ---------------------------------------------------------------------------
def test_compound_cd_then_pathspec_commit_blocks(gate_repo):
    repo, run_gate = gate_repo
    # Modify the trigger, then `cd schemas && git commit thing.schema.json`.
    # The pathspec `thing.schema.json` is relative to schemas/, i.e.
    # schemas/thing.schema.json (the trigger); companion docs/thing.md untouched.
    (repo / "schemas" / "thing.schema.json").write_text('{"v":7}\n')
    result = run_gate("cd schemas && git commit thing.schema.json -m x")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


def test_compound_cd_then_pathspec_commit_with_companion_allowed(gate_repo):
    repo, run_gate = gate_repo
    (repo / "schemas" / "thing.schema.json").write_text('{"v":8}\n')
    (repo / "docs" / "thing.md").write_text("# v8\n")
    # Commit both via pathspecs relative to schemas/ → passes.
    result = run_gate("cd schemas && git commit thing.schema.json ../docs/thing.md -m x")
    assert result.returncode == 0


def test_compound_unresolvable_cd_then_pathspec_commit_fails_closed(gate_repo):
    repo, run_gate = gate_repo
    (repo / "schemas" / "thing.schema.json").write_text('{"v":9}\n')
    # Unresolvable cd before a pathspec commit → cannot resolve paths → fail closed.
    result = run_gate("cd - && git commit schemas/thing.schema.json -m x")
    assert result.returncode == 2
    assert "unresolvable" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Regression: command separators must split so a commit after them is checked
# (codex PR #34): `&` (background), `|&` (pipe stdout+stderr), and subshell
# grouping `( ... )` previously buried a later `git commit` mid-segment.
# ---------------------------------------------------------------------------
def test_background_operator_then_commit_blocks(gate_repo):
    repo, run_gate = gate_repo
    (repo / "schemas" / "thing.schema.json").write_text('{"v":10}\n')
    _git(repo, "add", "schemas/thing.schema.json")
    result = run_gate("true & git commit -m x")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


def test_pipe_stderr_operator_then_commit_blocks(gate_repo):
    repo, run_gate = gate_repo
    (repo / "schemas" / "thing.schema.json").write_text('{"v":11}\n')
    _git(repo, "add", "schemas/thing.schema.json")
    result = run_gate("echo hi |& git commit -m x")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


def test_subshell_wrapped_commit_blocks(gate_repo):
    repo, run_gate = gate_repo
    (repo / "schemas" / "thing.schema.json").write_text('{"v":12}\n')
    _git(repo, "add", "schemas/thing.schema.json")
    result = run_gate("(git commit -m x)")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


def test_subshell_cd_then_commit_blocks(gate_repo):
    repo, run_gate = gate_repo
    # Subshell + cd + pathspec commit — exercises grouping strip AND cd tracking.
    (repo / "schemas" / "thing.schema.json").write_text('{"v":13}\n')
    result = run_gate("(cd schemas && git commit thing.schema.json -m x)")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


def test_background_operator_then_commit_with_companion_allowed(gate_repo):
    repo, run_gate = gate_repo
    (repo / "schemas" / "thing.schema.json").write_text('{"v":14}\n')
    (repo / "docs" / "thing.md").write_text("# v14\n")
    _git(repo, "add", "schemas/thing.schema.json", "docs/thing.md")
    result = run_gate("true & git commit -m x")
    assert result.returncode == 0


def test_substitution_guard_still_fires_after_segmentation_change(gate_repo):
    # Ensure the subshell-grouping strip did NOT break the $( ... ) guard.
    _, run_gate = gate_repo
    result = run_gate("$(which git) commit -m x")
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Regression: message-only commit forms bypass the gate (codex PR #34 — false
# positive). `--fixup=reword:<c>` (= --fixup=amend:<c> --only) and
# `--fixup=amend:<c> --only` record a log-message-only commit that ignores the
# index, so staged cascade-violating files must NOT block them.
# ---------------------------------------------------------------------------
def test_fixup_reword_bypasses_with_violating_index(gate_repo):
    repo, run_gate = gate_repo
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    # Stage a cascade violation (trigger without companion).
    (repo / "schemas" / "thing.schema.json").write_text('{"v":20}\n')
    _git(repo, "add", "schemas/thing.schema.json")
    # reword is message-only → must bypass despite the violating staged index.
    assert run_gate(f"git commit --fixup=reword:{head}").returncode == 0
    assert run_gate(f"git commit --fixup reword:{head}").returncode == 0


def test_fixup_amend_with_only_bypasses(gate_repo):
    repo, run_gate = gate_repo
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "schemas" / "thing.schema.json").write_text('{"v":21}\n')
    _git(repo, "add", "schemas/thing.schema.json")
    assert run_gate(f"git commit --fixup=amend:{head} --only").returncode == 0


def test_plain_fixup_still_checks_index(gate_repo):
    repo, run_gate = gate_repo
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    # Plain fixup (no reword:/amend:) INCLUDES the staged index → must still
    # block a cascade violation.
    (repo / "schemas" / "thing.schema.json").write_text('{"v":22}\n')
    _git(repo, "add", "schemas/thing.schema.json")
    result = run_gate(f"git commit --fixup={head}")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


def test_fixup_amend_without_only_still_checks_index(gate_repo):
    repo, run_gate = gate_repo
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    # amend: WITHOUT --only includes the staged index → must still block.
    (repo / "schemas" / "thing.schema.json").write_text('{"v":23}\n')
    _git(repo, "add", "schemas/thing.schema.json")
    result = run_gate(f"git commit --fixup=amend:{head}")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


# ---------------------------------------------------------------------------
# Regression: scope-boundary leakage (codex PR #34).
# F1: a path-qualified shell wrapper's argument scan must stop at the wrapper's
#     own simple command, not span a later separate command.
# F2: a `cd` inside a CLOSED subshell must not leak to the parent shell's later
#     commit pathspec resolution.
# ---------------------------------------------------------------------------
def test_wrapper_then_separate_commit_not_false_blocked(gate_repo):
    repo, run_gate = gate_repo
    # `/bin/bash -c 'echo ok'` is a self-contained wrapper command; the `;`
    # then begins a SEPARATE `git commit`. With a clean index the commit passes
    # cascade — the wrapper guard must NOT fail-block the whole line.
    result = run_gate("/bin/bash -c 'echo ok'; git commit -m x")
    assert result.returncode == 0, result.stderr


def test_wrapper_with_inarg_commit_still_fail_closed(gate_repo):
    _, run_gate = gate_repo
    # The commit verb is INSIDE the wrapper's own -c argument → still fail closed.
    result = run_gate("/bin/bash -c 'git commit -m x'")
    assert result.returncode == 2


def test_wrapper_quoted_separator_inarg_commit_still_fail_closed(gate_repo):
    _, run_gate = gate_repo
    # A `;` INSIDE the wrapper's quoted arg must not truncate the scan: the
    # in-arg `git commit` is real and must still fail closed.
    result = run_gate("/bin/bash -c 'echo a; git commit -m x'")
    assert result.returncode == 2


def test_closed_subshell_cd_does_not_leak_to_commit(gate_repo):
    repo, run_gate = gate_repo
    # `(cd schemas)` runs in a subshell that exits; the parent cwd stays at repo
    # root, so `git commit schemas/thing.schema.json` commits the trigger. The
    # gate must resolve the pathspec at the repo root (NOT schemas/schemas/...)
    # and block. Before the fix the leaked cd caused a silent bypass.
    (repo / "schemas" / "thing.schema.json").write_text('{"v":30}\n')
    result = run_gate("(cd schemas) && git commit schemas/thing.schema.json -m x")
    assert result.returncode == 2
    assert "schema-pair-cascade" in result.stderr


def test_closed_subshell_cd_commit_with_companion_allowed(gate_repo):
    repo, run_gate = gate_repo
    (repo / "schemas" / "thing.schema.json").write_text('{"v":31}\n')
    (repo / "docs" / "thing.md").write_text("# v31\n")
    result = run_gate(
        "(cd schemas) && git commit schemas/thing.schema.json docs/thing.md -m x"
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Regression: fast-forward merge must be checked per-commit, not as a union
# (codex PR #34 F1). Two incoming commits — one touching the trigger, a later
# one touching the companion — satisfy a UNION but the FF still lands the first
# (violating) commit unchanged, so the gate must block.
# ---------------------------------------------------------------------------
def test_fast_forward_merge_checked_per_commit_blocks(gate_repo):
    repo, run_gate = gate_repo
    # Build a topic branch ahead of HEAD with two commits: commit A edits the
    # trigger only; commit B edits the companion only. HEAD is an ancestor of
    # topic, so `git merge topic` fast-forwards and replays A then B unchanged.
    _git(repo, "checkout", "-b", "topic")
    (repo / "schemas" / "thing.schema.json").write_text('{"ff":1}\n')
    _git(repo, "add", "schemas/thing.schema.json")
    _git(repo, "commit", "-m", "A: trigger only")
    (repo / "docs" / "thing.md").write_text("# ff companion\n")
    _git(repo, "add", "docs/thing.md")
    _git(repo, "commit", "-m", "B: companion only")
    _git(repo, "checkout", "-")  # back to original branch (HEAD is ancestor of topic)
    result = run_gate("git merge topic")
    assert result.returncode == 2, result.stderr
    assert "schema-pair-cascade" in result.stderr


def test_fast_forward_merge_each_commit_clean_allowed(gate_repo):
    repo, run_gate = gate_repo
    # Single incoming commit touching trigger + companion together → each
    # per-commit check passes → merge allowed.
    _git(repo, "checkout", "-b", "topic2")
    (repo / "schemas" / "thing.schema.json").write_text('{"ff":2}\n')
    (repo / "docs" / "thing.md").write_text("# ff2\n")
    _git(repo, "add", "schemas/thing.schema.json", "docs/thing.md")
    _git(repo, "commit", "-m", "trigger + companion together")
    _git(repo, "checkout", "-")
    result = run_gate("git merge topic2")
    assert result.returncode == 0, result.stderr
