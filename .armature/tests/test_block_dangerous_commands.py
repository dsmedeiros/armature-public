"""
Tests for block-dangerous-commands.sh (HOOK-001).

Hook behaviour (verified from source, all 333 lines read):

BLOCK patterns (exit 2 + "BLOCK" on stderr):
  1. rm -rf on non-safe targets (incl. bare rm -rf, path traversal, abs paths)
  2. git push --force / git push -f
  3. git reset --hard
  4. git clean -f (any -f combination: -fd, -fx, -fdx, etc.)
  5. DROP TABLE / TRUNCATE (case-insensitive, grep -i)
  6. chmod -R 777 or chmod 777 -R
  7. --no-verify / --skip-hooks (whole-flag match, space-bounded)
  8. git add -A / --all / -u / --update / git add . (bare dot only)
  9. git checkout -- . (bare dot as sole path arg)
  10. git restore . (bare dot, with or without --staged/--worktree/--source=)
  11. git branch -D (uppercase -D, alone or combined)
  12. git stash drop / git stash clear
  13. dd if= (raw disk read/write)
  14. mkfs (filesystem format)
  15. Fork bomb: :|: or (){  patterns

ALLOW paths (exit 0, "BLOCK" not in stderr):
  - Safe commands: echo, ls, git-status, git-log, cat, mkdir, etc.
  - rm -rf on safe targets: node_modules, __pycache__, dist, build,
    .pytest_cache, .tdd-dirty, .code-dirty, .venv, .mypy_cache,
    .ruff_cache, __pypackages__
  - rm -f without -r (non-recursive)
  - rm -r without -f (non-forced)
  - git push --force-with-lease (explicitly excluded from force block)
  - git push origin main (no force flag)
  - git branch -d (lowercase, safe delete)
  - git add specific-file.py (explicit path, not bare dot)
  - git checkout -- specific-file.py (not bare dot)
  - git restore specific-file.py (not bare dot)
  - git stash pop / list / show
  - fail-open: invalid JSON, empty command

Bypass normalization (SHOULD block):
  - \rm -rf / (backslash-bypass, N-1 fix)
  - newline-embedded rm -rf (N-3 fix)
  - echo "rm -rf /" | <any-shell> (B-3 filter removed in cycle-3; all pipe-to-shell variants now blocked by rm-rf rule directly)
  - echo "rm -rf ..." (B-3 filter removed in cycle-3; echo with rm-rf now BLOCKS)

Documentation gap vs §5.2.2:
  - §5.2.2 lists all the block rules ✓
  - Hook has EXTRA safe-rm targets not named in §5.2.2's example list:
      .tdd-dirty, .code-dirty, .mypy_cache, .ruff_cache, __pypackages__
    (§5.2.2 only names node_modules and __pycache__ as examples — minor doc gap)
  - --skip-hooks: present in hook, present in §5.2.2 ✓
  - git add -u / --update: present in hook, present in §5.2.2 ✓
  - chmod 777 -R (reversed order): present in hook, not explicitly called out
    in §5.2.2 (which says "chmod -R 777") — minor doc gap
"""

import json

import pytest

from .helpers import bash_event


# ===========================================================================
# Helpers
# ===========================================================================

HOOK = "block-dangerous-commands.sh"


def _allow(run_hook, command: str):
    """Assert the hook allows this command (exit 0, no BLOCK in stderr)."""
    result = run_hook(HOOK, bash_event(command))
    assert result.returncode == 0, (
        f"Expected ALLOW for {command!r} but got exit {result.returncode}.\n"
        f"stderr: {result.stderr}"
    )
    assert "BLOCK" not in result.stderr, (
        f"Expected no BLOCK for {command!r} but stderr contained 'BLOCK'.\n"
        f"stderr: {result.stderr}"
    )


def _block(run_hook, command: str, expected_reason: str | None = None):
    """Assert the hook blocks this command (exit 2, BLOCK in stderr).

    Parameters
    ----------
    expected_reason:
        Optional substring that must appear in stderr in addition to the
        literal string "BLOCK".  Use this to assert that the *correct* rule
        fired, not just that some rule blocked the command.  Existing callers
        that omit this parameter retain the original (substring "BLOCK" only)
        assertion so no existing test needs to be updated.
    """
    result = run_hook(HOOK, bash_event(command))
    assert result.returncode == 2, (
        f"Expected BLOCK (exit 2) for {command!r} but got exit {result.returncode}.\n"
        f"stderr: {result.stderr}"
    )
    assert "BLOCK" in result.stderr, (
        f"Expected 'BLOCK' in stderr for {command!r} but stderr was:\n{result.stderr}"
    )
    if expected_reason is not None:
        assert expected_reason in result.stderr, (
            f"Expected reason {expected_reason!r} in stderr for {command!r} but stderr was:\n"
            f"{result.stderr}"
        )


# ===========================================================================
# TestAllowCases — safe commands that must not be blocked
# ===========================================================================

class TestAllowCases:
    """Safe commands that should exit 0 with no BLOCK on stderr."""

    def test_echo_hello(self, run_hook):
        _allow(run_hook, "echo hello")

    def test_ls_la(self, run_hook):
        _allow(run_hook, "ls -la")

    def test_git_status(self, run_hook):
        _allow(run_hook, "git status")

    def test_git_log_oneline(self, run_hook):
        _allow(run_hook, "git log --oneline")

    def test_cat_file(self, run_hook):
        _allow(run_hook, "cat file.txt")

    def test_mkdir_foo(self, run_hook):
        _allow(run_hook, "mkdir foo")

    def test_git_push_force_with_lease(self, run_hook):
        """--force-with-lease is the safe push mode; must NOT be blocked."""
        _allow(run_hook, "git push --force-with-lease")

    def test_allow_git_push_force_with_lease_param(self, run_hook):
        """--force-with-lease=<ref> (parameterized form) must also be allowed (H1).

        The hook regex --force([[:space:]]|$) requires space or EOL after
        --force, so --force-with-lease=refs/heads/main does not match.
        This test pins the parameterized form explicitly so a future regex
        tightening (e.g. to --force[[:alnum:]-]*) can't silently break it.
        """
        _allow(run_hook, "git push --force-with-lease=refs/heads/main")

    def test_git_push_force_with_lease_and_branch(self, run_hook):
        _allow(run_hook, "git push origin main --force-with-lease")

    def test_git_push_origin_main_no_force(self, run_hook):
        """Plain push with no force flag must be allowed."""
        _allow(run_hook, "git push origin main")

    def test_git_branch_lowercase_d(self, run_hook):
        """Lowercase -d is safe delete; must be allowed."""
        _allow(run_hook, "git branch -d mybranch")

    def test_git_add_specific_file(self, run_hook):
        """Staging a named file must be allowed."""
        _allow(run_hook, "git add specific-file.py")

    def test_git_add_specific_path(self, run_hook):
        """Staging a path inside a subdirectory must be allowed."""
        _allow(run_hook, "git add src/module.py")

    def test_git_checkout_specific_file(self, run_hook):
        """git checkout -- <specific-file> must be allowed."""
        _allow(run_hook, "git checkout -- specific-file.py")

    def test_git_restore_specific_file(self, run_hook):
        """git restore <specific-file> must be allowed."""
        _allow(run_hook, "git restore specific-file.py")

    def test_git_restore_staged_specific_file(self, run_hook):
        """git restore --staged <specific-file> must be allowed."""
        _allow(run_hook, "git restore --staged specific-file.py")

    def test_git_stash_pop(self, run_hook):
        _allow(run_hook, "git stash pop")

    def test_git_stash_list(self, run_hook):
        _allow(run_hook, "git stash list")

    def test_git_stash_show(self, run_hook):
        _allow(run_hook, "git stash show")

    def test_rm_f_without_r(self, run_hook):
        """rm -f without -r is not recursive force-delete; must be allowed."""
        _allow(run_hook, "rm -f file.txt")

    def test_rm_r_without_f(self, run_hook):
        """rm -r without -f is not force; must be allowed."""
        _allow(run_hook, "rm -r somedir")

    def test_echo_containing_rm_rf_string(self, run_hook):
        """echo "rm -rf ..." now BLOCKS — B-3 filter removed in cycle-3.

        The B-3 string-literal filter was removed after two successive cycles
        each produced new HIGH-severity bypass vectors.  The filter's only
        purpose was to allow `echo "rm -rf ..."` for documentation strings.
        Removing the filter is the correct safety trade-off: the use case is
        rare, workarounds exist (e.g. split tokens, obfuscated spelling), and
        every filter implementation shipped exploitable bypasses.
        Deliberately changed from _allow to _block.
        """
        _block(run_hook, 'echo "rm -rf is dangerous"', expected_reason="rm -rf")

    def test_git_diff_head(self, run_hook):
        _allow(run_hook, "git diff HEAD")

    def test_python_command(self, run_hook):
        _allow(run_hook, "python -m pytest .armature/tests/ -v")

    def test_invalid_json_fail_open(self, run_hook):
        """Completely invalid JSON must fail open (exit 0)."""
        result = run_hook(HOOK, "{{not json at all")
        assert result.returncode == 0

    def test_empty_command_fail_open(self, run_hook):
        """Empty command field must fail open (exit 0)."""
        payload = json.dumps({"tool_input": {"command": ""}})
        result = run_hook(HOOK, payload)
        assert result.returncode == 0


# ===========================================================================
# TestSafeRmBoundary — rm -rf allow/block boundary conditions
# ===========================================================================

class TestSafeRmBoundary:
    """
    Boundary tests for the is_safe_rm_target / all_rm_targets_safe logic.

    Safe rm targets (from hook source):
      node_modules, __pycache__, dist, build, .pytest_cache, .tdd-dirty,
      .code-dirty, .venv, .mypy_cache, .ruff_cache, __pypackages__
    """

    # --- Each safe target must be allowed ---

    def test_safe_rm_node_modules(self, run_hook):
        _allow(run_hook, "rm -rf node_modules")

    def test_safe_rm_pycache(self, run_hook):
        _allow(run_hook, "rm -rf __pycache__")

    def test_safe_rm_dist(self, run_hook):
        _allow(run_hook, "rm -rf dist")

    def test_safe_rm_build(self, run_hook):
        _allow(run_hook, "rm -rf build")

    def test_safe_rm_pytest_cache(self, run_hook):
        _allow(run_hook, "rm -rf .pytest_cache")

    def test_safe_rm_tdd_dirty(self, run_hook):
        _allow(run_hook, "rm -rf .tdd-dirty")

    def test_safe_rm_code_dirty(self, run_hook):
        _allow(run_hook, "rm -rf .code-dirty")

    def test_safe_rm_venv(self, run_hook):
        _allow(run_hook, "rm -rf .venv")

    def test_safe_rm_mypy_cache(self, run_hook):
        _allow(run_hook, "rm -rf .mypy_cache")

    def test_safe_rm_ruff_cache(self, run_hook):
        _allow(run_hook, "rm -rf .ruff_cache")

    def test_safe_rm_pypackages(self, run_hook):
        _allow(run_hook, "rm -rf __pypackages__")

    # --- Trailing slash stripped → still allowed ---

    def test_safe_rm_node_modules_trailing_slash(self, run_hook):
        """Trailing slash must be stripped before safe-target check."""
        _allow(run_hook, "rm -rf node_modules/")

    def test_safe_rm_pycache_trailing_slash(self, run_hook):
        _allow(run_hook, "rm -rf __pycache__/")

    # --- ./ prefix stripped → still allowed ---

    def test_safe_rm_dot_slash_node_modules(self, run_hook):
        """./node_modules has basename node_modules → allowed."""
        _allow(run_hook, "rm -rf ./node_modules")

    def test_safe_rm_dot_slash_venv(self, run_hook):
        _allow(run_hook, "rm -rf ./.venv")

    # --- Path traversal → always blocked ---

    def test_block_rm_rf_dotdot_node_modules(self, run_hook):
        """../node_modules contains '..' — path traversal must be blocked."""
        _block(run_hook, "rm -rf ../node_modules")

    def test_block_rm_rf_dotdot_dist(self, run_hook):
        _block(run_hook, "rm -rf ../dist")

    # --- Absolute path with subdirectory → blocked ---

    def test_block_rm_rf_absolute_with_subdir_node_modules(self, run_hook):
        """/home/user/node_modules has subdirectory path components → blocked."""
        _block(run_hook, "rm -rf /home/user/node_modules")

    def test_block_rm_rf_absolute_with_subdir_generic(self, run_hook):
        _block(run_hook, "rm -rf /var/project/dist")

    # --- Bare rm -rf (no target) → blocked ---

    def test_block_rm_rf_no_target(self, run_hook):
        """No non-flag arguments → all_rm_targets_safe returns 1 → block."""
        _block(run_hook, "rm -rf")

    # --- Broad / well-known dangerous targets → blocked ---

    def test_block_rm_rf_root(self, run_hook):
        _block(run_hook, "rm -rf /")

    def test_block_rm_rf_tilde(self, run_hook):
        _block(run_hook, "rm -rf ~")

    def test_block_rm_rf_dot(self, run_hook):
        _block(run_hook, "rm -rf .")

    def test_block_rm_rf_arbitrary_dir(self, run_hook):
        _block(run_hook, "rm -rf /tmp/foo")

    def test_block_sudo_rm_rf(self, run_hook):
        """sudo prefix must not bypass detection."""
        _block(run_hook, "sudo rm -rf /tmp/foo")

    # -----------------------------------------------------------------------
    # HIGH-2 (C2): long-form --recursive / --force flags
    # -----------------------------------------------------------------------

    def test_block_rm_long_recursive_force_root(self, run_hook):
        """rm --recursive --force / must be blocked (both long-form flags)."""
        _block(run_hook, "rm --recursive --force /", expected_reason="rm -rf")

    def test_block_rm_long_recursive_short_force(self, run_hook):
        """rm --recursive -f / must be blocked (mixed long/short flags)."""
        _block(run_hook, "rm --recursive -f /", expected_reason="rm -rf")

    def test_block_rm_short_recursive_long_force(self, run_hook):
        """rm -r --force / must be blocked (mixed short/long flags)."""
        _block(run_hook, "rm -r --force /", expected_reason="rm -rf")

    # -----------------------------------------------------------------------
    # S1: basename-at-root safe-target semantics
    # -----------------------------------------------------------------------

    def test_block_rm_rf_root_node_modules(self, run_hook):
        """rm -rf /node_modules is BLOCKED (cycle-20 hardening).

        Previously allowed via basename allow-listing on top-level absolute
        paths; this gap let `rm -rf /build`, `/dist`, `/node_modules`, etc.
        wipe filesystem-root directories outside the repo. The safe-name
        allowlist is for REPO-LOCAL caches; absolute targets are never safe.
        Repo-local equivalents (`rm -rf node_modules`, `rm -rf ./node_modules`)
        remain allowed.
        """
        _block(run_hook, "rm -rf /node_modules", expected_reason="rm -rf")

    def test_block_rm_rf_root_build(self, run_hook):
        """rm -rf /build is BLOCKED (absolute path, even with safe basename)."""
        _block(run_hook, "rm -rf /build", expected_reason="rm -rf")

    def test_block_rm_rf_root_dist(self, run_hook):
        """rm -rf /dist is BLOCKED (absolute path, even with safe basename)."""
        _block(run_hook, "rm -rf /dist", expected_reason="rm -rf")

    def test_block_rm_rf_root_etc(self, run_hook):
        """rm -rf /etc must be blocked (/etc basename is not a safe target)."""
        _block(run_hook, "rm -rf /etc", expected_reason="rm -rf")

    def test_allow_rm_rf_quoted_node_modules(self, run_hook):
        """rm -rf \"node_modules\" must be allowed (quote-stripping in is_safe_rm_target).

        The is_safe_rm_target helper strips surrounding double-quotes before
        checking basename, so \"node_modules\" resolves to the safe target
        node_modules.
        """
        _allow(run_hook, 'rm -rf "node_modules"')


# ===========================================================================
# TestBlockCommands — every §5.2.2 block rule must have an explicit test
# ===========================================================================

class TestBlockCommands:
    """
    Block-pattern tests. Each test asserts exit 2 AND 'BLOCK' in stderr.
    Organized to map directly to hook source rule sections.
    """

    # -----------------------------------------------------------------------
    # Rule: git push --force / git push -f
    # -----------------------------------------------------------------------

    def test_block_git_push_force(self, run_hook):
        _block(run_hook, "git push --force")

    def test_block_git_push_force_origin_main(self, run_hook):
        _block(run_hook, "git push --force origin main")

    def test_block_git_push_force_f_flag(self, run_hook):
        _block(run_hook, "git push -f")

    def test_block_git_push_force_f_with_remote(self, run_hook):
        _block(run_hook, "git push -f origin main")

    # -----------------------------------------------------------------------
    # Rule: git reset --hard
    # -----------------------------------------------------------------------

    def test_block_git_reset_hard(self, run_hook):
        _block(run_hook, "git reset --hard")

    def test_block_git_reset_hard_head(self, run_hook):
        _block(run_hook, "git reset --hard HEAD~1")

    def test_block_git_reset_hard_sha(self, run_hook):
        _block(run_hook, "git reset --hard abc1234")

    # -----------------------------------------------------------------------
    # Rule: git clean -f / -fd / -fx / -fdx
    # -----------------------------------------------------------------------

    def test_block_git_clean_f(self, run_hook):
        _block(run_hook, "git clean -f")

    def test_block_git_clean_fd(self, run_hook):
        _block(run_hook, "git clean -fd")

    def test_block_git_clean_fx(self, run_hook):
        _block(run_hook, "git clean -fx")

    def test_block_git_clean_fdx(self, run_hook):
        _block(run_hook, "git clean -fdx")

    # -----------------------------------------------------------------------
    # Rule: DROP TABLE / TRUNCATE (case-insensitive)
    # -----------------------------------------------------------------------

    def test_block_drop_table_uppercase(self, run_hook):
        _block(run_hook, "DROP TABLE users;")

    def test_block_drop_table_lowercase(self, run_hook):
        _block(run_hook, "drop table users;")

    def test_block_drop_table_mixed_case(self, run_hook):
        _block(run_hook, "Drop Table users;")

    def test_block_truncate_uppercase(self, run_hook):
        _block(run_hook, "TRUNCATE logs;")

    def test_block_truncate_lowercase(self, run_hook):
        _block(run_hook, "truncate logs;")

    def test_block_psql_drop_table(self, run_hook):
        """DROP TABLE inside a psql command string must still be blocked."""
        _block(run_hook, 'psql -c "DROP TABLE users;"')

    # -----------------------------------------------------------------------
    # Rule: chmod -R 777 / chmod 777 -R
    # -----------------------------------------------------------------------

    def test_block_chmod_r_777(self, run_hook):
        _block(run_hook, "chmod -R 777 .")

    def test_block_chmod_777_r(self, run_hook):
        """Reversed order chmod 777 -R must also be blocked."""
        _block(run_hook, "chmod 777 -R .")

    # -----------------------------------------------------------------------
    # Rule: --no-verify / --skip-hooks
    # -----------------------------------------------------------------------

    def test_block_no_verify(self, run_hook):
        _block(run_hook, "git commit --no-verify -m 'msg'")

    def test_block_skip_hooks(self, run_hook):
        _block(run_hook, "git commit --skip-hooks -m 'msg'")

    def test_block_no_verify_standalone(self, run_hook):
        _block(run_hook, "git push --no-verify")

    def test_block_no_verify_suffix_not_blocked(self, run_hook):
        """
        --no-verify-ssl must NOT be blocked (whole-flag match requirement).
        The hook uses space-bounded anchoring so --no-verify-ssl should pass.
        """
        _allow(run_hook, "curl --no-verify-ssl https://example.com")

    def test_allow_no_verify_suffix_variants(self, run_hook):
        """Additional --no-verify-<suffix> forms must be allowed (S3, LOW).

        The hook regex (^|[[:space:]])--no-verify([[:space:]]|$) requires
        --no-verify to be followed by space or EOL, so any hyphenated or
        other suffix causes the rule to not fire.  This behavior is
        INTENTIONAL — suffix variants are not git hook bypass flags.
        Pins the documented surface so a future regex tightening is visible.
        """
        _allow(run_hook, "tool --no-verify-stuff arg")
        _allow(run_hook, "tool --no-verify-ssl arg")

    # -----------------------------------------------------------------------
    # Rule: git add -A / --all / -u / --update / git add . (bare dot)
    # -----------------------------------------------------------------------

    def test_block_git_add_capital_a(self, run_hook):
        _block(run_hook, "git add -A")

    def test_block_git_add_capital_a_with_path(self, run_hook):
        _block(run_hook, "git add -A .")

    def test_block_git_add_all(self, run_hook):
        _block(run_hook, "git add --all")

    def test_block_git_add_u(self, run_hook):
        _block(run_hook, "git add -u")

    def test_block_git_add_update(self, run_hook):
        _block(run_hook, "git add --update")

    def test_block_git_add_bare_dot(self, run_hook):
        _block(run_hook, "git add .")

    # Cycle-19: git add -- . — `--` is option terminator, `.` is the
    # pathspec; same broad-stage risk as bare `git add .`.
    def test_block_git_add_dashdash_dot(self, run_hook):
        _block(run_hook, "git add -- .")

    def test_block_git_add_dashdash_dot_chained(self, run_hook):
        """git add -- . && git commit -- chained form must still block."""
        _block(run_hook, "git add -- . && git commit -m 'wip'")

    def test_block_git_add_dashdash_dot_extra_space(self, run_hook):
        """git add  --  .  with extra whitespace must still block."""
        _block(run_hook, "git add  --  .")

    # -----------------------------------------------------------------------
    # Rule: git checkout -- . (bare dot)
    # -----------------------------------------------------------------------

    def test_block_git_checkout_dot(self, run_hook):
        _block(run_hook, "git checkout -- .")

    def test_allow_git_checkout_specific_file_with_dashdash(self, run_hook):
        """git checkout -- <specific-file> must be allowed (not bare dot)."""
        _allow(run_hook, "git checkout -- README.md")

    # -----------------------------------------------------------------------
    # Rule: git restore . (bare dot)
    # -----------------------------------------------------------------------

    def test_block_git_restore_dot(self, run_hook):
        _block(run_hook, "git restore .")

    def test_block_git_restore_staged_dot(self, run_hook):
        _block(run_hook, "git restore --staged .")

    def test_block_git_restore_worktree_dot(self, run_hook):
        _block(run_hook, "git restore --worktree .")

    # Cycle-19 sibling extension: `--` option terminator before bare dot
    def test_block_git_restore_dashdash_dot(self, run_hook):
        _block(run_hook, "git restore -- .")

    def test_block_git_restore_staged_dashdash_dot(self, run_hook):
        _block(run_hook, "git restore --staged -- .")

    # -----------------------------------------------------------------------
    # Rule: git branch -D (uppercase, force-delete)
    # -----------------------------------------------------------------------

    def test_block_git_branch_uppercase_d(self, run_hook):
        _block(run_hook, "git branch -D mybranch")

    def test_block_git_branch_uppercase_d_combined(self, run_hook):
        """Combined flags like -Dr must still be blocked if D is present."""
        _block(run_hook, "git branch -Dr mybranch")

    def test_allow_git_branch_lowercase_d(self, run_hook):
        """Lowercase -d is safe merge-check delete; must be allowed."""
        _allow(run_hook, "git branch -d mybranch")

    # -----------------------------------------------------------------------
    # Rule: git stash drop / git stash clear
    # -----------------------------------------------------------------------

    def test_block_git_stash_drop(self, run_hook):
        _block(run_hook, "git stash drop")

    def test_block_git_stash_drop_with_index(self, run_hook):
        _block(run_hook, "git stash drop stash@{0}")

    def test_block_git_stash_clear(self, run_hook):
        _block(run_hook, "git stash clear")

    # -----------------------------------------------------------------------
    # Rule: dd if= (raw disk operations)
    # -----------------------------------------------------------------------

    def test_block_dd_if_dev_sda(self, run_hook):
        _block(run_hook, "dd if=/dev/sda of=/dev/sdb")

    def test_block_sudo_dd_if_zero(self, run_hook):
        """sudo prefix must not bypass dd detection."""
        _block(run_hook, "sudo dd if=/dev/zero of=/dev/sda")

    def test_block_dd_if_input_file(self, run_hook):
        """dd if= on any source must be blocked."""
        _block(run_hook, "dd if=backup.img of=/dev/sda")

    # -----------------------------------------------------------------------
    # Rule: mkfs (filesystem format)
    # -----------------------------------------------------------------------

    def test_block_mkfs_ext4(self, run_hook):
        _block(run_hook, "mkfs.ext4 /dev/sda1")

    def test_block_mkfs_bare(self, run_hook):
        _block(run_hook, "mkfs /dev/sda")

    def test_block_mkfs_vfat(self, run_hook):
        _block(run_hook, "mkfs.vfat /dev/sdb1")

    # -----------------------------------------------------------------------
    # Rule: fork bomb  :(){ :|:& };:
    # -----------------------------------------------------------------------

    def test_block_fork_bomb_classic(self, run_hook):
        _block(run_hook, ":(){ :|:& };:")

    def test_block_fork_bomb_pipe_pattern(self, run_hook):
        """Function-definition fork bomb: f(){ f|f& };f.

        Tests the \\(\\)[[:space:]]*\\{ branch of the fork-bomb regex with
        no space between () and {.  The :|: self-pipe branch is tested
        separately in test_block_fork_bomb_pipe_signature.
        """
        _block(run_hook, "f(){ f|f& };f")

    def test_block_fork_bomb_pipe_signature(self, run_hook):
        _block(run_hook, "bash -c ':(){ :|:& };:'")

    def test_block_fork_bomb_no_space(self, run_hook):
        """Fork bomb with no whitespace after (){  must be blocked (H4 fix).

        Minified fork bombs often drop whitespace: f(){f|f&};f contains
        (){  with no space after the brace.  The old regex \\(\\)\\{[[:space:]]
        required whitespace and missed this form.  The relaxed \\(\\)\\{
        catches it.
        """
        _block(run_hook, "f(){f|f&};f")

    # -----------------------------------------------------------------------
    # Rule: mkfs — command-position anchoring (S2 fix)
    # -----------------------------------------------------------------------

    def test_allow_mkfs_substring_in_unrelated_string(self, run_hook):
        """cat foommkfs.x4 must be allowed (mkfs only as substring, not command).

        The old mkfs([.[:space:]]|$) regex matched anywhere in the string,
        causing cat foommkfs.x4 to be false-positively blocked.  The anchored
        regex (^|[;&|[:space:]])mkfs([.[:space:]]|$) requires mkfs to appear
        at command-position (start or after a separator).
        """
        _allow(run_hook, "cat foommkfs.x4")

    def test_block_mkfs_at_command_start(self, run_hook):
        """mkfs at start of command must still be blocked after anchoring fix."""
        _block(run_hook, "mkfs /dev/sda")

    def test_block_mkfs_after_separator(self, run_hook):
        """mkfs after && separator must still be blocked after anchoring fix."""
        _block(run_hook, "cd /tmp && mkfs.ext4 /dev/sda")

    # -----------------------------------------------------------------------
    # Rule: git restore --source= (H3)
    # -----------------------------------------------------------------------

    def test_block_git_restore_source_dot(self, run_hook):
        """git restore --source=HEAD . must be blocked.

        The restore regex modifier group includes --source=<ref>, so this form
        (restore all files to a historical commit) is correctly blocked.
        Previously flagged as a coverage gap with no explicit test.
        """
        _block(run_hook, "git restore --source=HEAD .")

    # -----------------------------------------------------------------------
    # Rule: git checkout -- . broader pattern (H2)
    # -----------------------------------------------------------------------

    def test_block_git_checkout_branch_dashdash_dot(self, run_hook):
        """git checkout main -- . must be blocked.

        The hook regex git[[:space:]].*checkout[[:space:]].*--[[:space:]]+\\.
        greedily matches any checkout ending with -- ., not just the bare form.
        This pins the broader documented behavior.
        """
        _block(run_hook, "git checkout main -- .")

    def test_block_git_checkout_ref_dashdash_dot(self, run_hook):
        """git checkout HEAD~5 -- . must be blocked (same broader pattern)."""
        _block(run_hook, "git checkout HEAD~5 -- .")


# ===========================================================================
# TestBypassNormalization — N-1 (backslash) and N-3 (newline) bypass fixes
# ===========================================================================

class TestBypassNormalization:
    """
    Tests for bypass-normalization preprocessors in the hook.

    N-1 fix: \rm → rm (strip backslash 0x5C; replace CR 0x0D with 'r')
    N-3 fix: literal LF and JSON \\n replaced with ' && ' before matching
    """

    def test_block_backslash_rm_rf_root(self, run_hook):
        r"""
        \rm -rf / is a shell trick to bypass aliases.
        Hook strips backslash (0x5C) so \rm becomes rm — must be blocked.
        The JSON string r'\rm -rf /' encodes the backslash as 0x5C.
        """
        _block(run_hook, r"\rm -rf /")

    def test_block_newline_embedded_rm_rf(self, run_hook):
        r"""
        Multi-line command with literal \n (JSON escape) before rm -rf.
        N-3 fix replaces \n with ' && ' so the rm command is still visible
        to the pattern matcher.
        """
        # JSON-escaped newline in the command string
        command = "echo start\\nrm -rf /\\necho end"
        _block(run_hook, command)

    def test_block_multiline_literal_lf(self, repo_root):
        """
        Literal LF (0x0A) embedded in the JSON payload (invalid JSON per spec
        but the hook pre-processes it via 'tr \\012 ' before parsing).
        The hook collapses the LF to a space so the full command is visible.

        Uses bytes-mode subprocess directly because Python's text=True mode
        on Windows translates '\\n' to '\\r\\n', defeating tr '\\012' in the hook.
        Sending raw bytes guarantees the hook receives the exact 0x0A byte.
        """
        import shutil as _shutil
        bash_bin = _shutil.which("bash")
        if bash_bin is None:
            pytest.skip("bash not available")
        hook_path = repo_root / ".armature" / "hooks" / HOOK
        # Payload with a real 0x0A byte inside the JSON command value.
        # This is technically invalid JSON but the hook handles it.
        payload = b'{"tool_input": {"command": "echo safe\nrm -rf /"}}'
        result = __import__("subprocess").run(
            [bash_bin, str(hook_path)],
            input=payload,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 2
        assert b"BLOCK" in result.stderr

    def test_allow_safe_command_after_normalization(self, run_hook):
        """
        Normalization must not cause false positives on safe commands.
        A safe multi-line command should still be allowed.
        """
        payload = '{"tool_input": {"command": "echo hello\ngit status"}}'
        result = run_hook(HOOK, payload)
        assert result.returncode == 0
        assert "BLOCK" not in result.stderr

    # -----------------------------------------------------------------------
    # HIGH-1 (C1): eval / pipe-to-bash bypass via B-3 quote heuristic
    # These test the corrected state-machine B-3 filter.
    # -----------------------------------------------------------------------

    def test_block_eval_rm_rf_root(self, run_hook):
        """eval executes its argument; rm inside eval's double-quotes must be blocked.

        The old odd-quote-count B-3 heuristic falsely suppressed this because
        eval \"rm -rf /\" has one \" before rm (odd count → skip rule).  The
        new state-machine filter requires the prefix to be an echo/printf verb,
        so eval is NOT treated as a string context.
        """
        _block(run_hook, 'eval "rm -rf /"', expected_reason="rm -rf")

    def test_block_echo_pipe_bash_rm_rf(self, run_hook):
        """echo \"rm -rf /\" | bash executes the echoed string via bash.

        The pipe-to-shell makes this dangerous regardless of the echo context.
        The B-3 filter must not fire when | bash appears after the rm token.
        """
        _block(run_hook, 'echo "rm -rf /" | bash', expected_reason="rm -rf")

    def test_allow_echo_rm_rf_legitimate_string(self, run_hook):
        """echo "rm -rf ..." now BLOCKS — B-3 filter removed in cycle-3.

        This test previously asserted ALLOW for the canonical B-3 string-literal
        case.  The B-3 filter was removed in cycle-3 after every implementation
        produced exploitable HIGH-severity bypasses (cycle-1: quote-parity bypass;
        cycle-2: 2-element pipe denylist bypass with alternative shells / spacing).
        The usability cost is accepted.  Deliberately changed from _allow to _block.
        """
        _block(run_hook, 'echo "rm -rf is dangerous"', expected_reason="rm -rf")

    def test_block_echo_single_quote_rm_rf(self, run_hook):
        """Single-quoted echo with rm -rf / is blocked.

        echo 'rm -rf /' has no double-quote before rm, so the rm-rf rule fires.
        With B-3 removed in cycle-3, single-quote and double-quote echo forms
        are treated identically — both block.
        """
        _block(run_hook, "echo 'rm -rf /'", expected_reason="rm -rf")


# ===========================================================================
# TestCycle3Fixes — cycle-3 RED-TEAM remediation
#
# Covers:
#   C1: pipe-to-shell variants (B-3 removal; rm-rf rule now fires directly)
#   H1: fork bomb extra-whitespace variant (regex fix)
# ===========================================================================

class TestCycle3Fixes:
    """
    Regression tests introduced in cycle-3 to close all RED-TEAM FAIL findings.

    B-3 removal (C1): With no string-literal exemption, echo/printf/print
    followed by rm -rf and ANY subsequent shell operator is blocked by the
    rm-rf rule directly, regardless of shell name, path-qualification,
    spacing, or pipe character encoding.

    Fork bomb regex (H1): The `\\(\\)[[:space:]]*\\{` pattern now matches
    `() {` (space between `()` and `{`) as well as `(){` (no space).
    """

    # -----------------------------------------------------------------------
    # C1 fixes: pipe-to-shell variants — all must now exit 2 (BLOCK)
    # -----------------------------------------------------------------------

    def test_block_echo_rm_rf_pipe_bin_bash(self, run_hook):
        """echo \"rm -rf /\" | /bin/bash — path-qualified bash must block."""
        _block(run_hook, 'echo "rm -rf /" | /bin/bash', expected_reason="rm -rf")

    def test_block_echo_rm_rf_pipe_zsh(self, run_hook):
        """echo \"rm -rf /\" | zsh — alternative shell must block."""
        _block(run_hook, 'echo "rm -rf /" | zsh', expected_reason="rm -rf")

    def test_block_echo_rm_rf_pipe_ksh(self, run_hook):
        """echo \"rm -rf /\" | ksh — alternative shell must block."""
        _block(run_hook, 'echo "rm -rf /" | ksh', expected_reason="rm -rf")

    def test_block_echo_rm_rf_pipe_dash(self, run_hook):
        """echo \"rm -rf /\" | dash — alternative shell must block."""
        _block(run_hook, 'echo "rm -rf /" | dash', expected_reason="rm -rf")

    def test_block_echo_rm_rf_pipe_ash(self, run_hook):
        """echo \"rm -rf /\" | ash — alternative shell must block."""
        _block(run_hook, 'echo "rm -rf /" | ash', expected_reason="rm -rf")

    def test_block_echo_rm_rf_pipe_busybox_sh(self, run_hook):
        """echo \"rm -rf /\" | busybox sh — busybox shell must block."""
        _block(run_hook, 'echo "rm -rf /" | busybox sh', expected_reason="rm -rf")

    def test_block_echo_rm_rf_pipe_bash_no_space(self, run_hook):
        """echo \"rm -rf /\" |bash — no-space pipe must block."""
        _block(run_hook, 'echo "rm -rf /" |bash', expected_reason="rm -rf")

    def test_block_echo_rm_rf_pipe_bash_no_spaces_anywhere(self, run_hook):
        """echo \"rm -rf /\"|bash — no spaces at all around pipe must block."""
        _block(run_hook, 'echo "rm -rf /"|bash', expected_reason="rm -rf")

    def test_block_echo_rm_rf_pipe_bash_tab_separated(self, run_hook):
        """echo \"rm -rf /\" <TAB>|<TAB> bash — tab-separated pipe must block."""
        _block(run_hook, 'echo "rm -rf /"\t|\tbash', expected_reason="rm -rf")

    # -----------------------------------------------------------------------
    # Cycle-17: shell-expanded whitespace bypass (${IFS} / $IFS)
    # -----------------------------------------------------------------------

    def test_block_rm_ifs_braced_substitution(self, run_hook):
        """rm${IFS}-rf / — braced $IFS expands to whitespace at runtime;
        validator must normalize it before checking."""
        _block(run_hook, "rm${IFS}-rf /", expected_reason="rm -rf")

    def test_block_rm_ifs_bare_substitution(self, run_hook):
        """rm$IFS-rf$IFS/ — bare $IFS form must also be normalized."""
        _block(run_hook, "rm$IFS-rf$IFS/", expected_reason="rm -rf")

    def test_block_rm_ifs_multiple_segments(self, run_hook):
        """${IFS}rm${IFS}-rf${IFS}/ — leading IFS plus multiple separators."""
        _block(run_hook, "${IFS}rm${IFS}-rf${IFS}/", expected_reason="rm -rf")

    def test_block_rm_ifs_inside_chained_command(self, run_hook):
        """git status && rm${IFS}-rf / — chained command with IFS bypass."""
        _block(run_hook, "git status && rm${IFS}-rf /", expected_reason="rm -rf")

    # Cycle-17 + PR #23 cycle-4 review: bash parameter-expansion variants of
    # IFS that still evaluate to whitespace at runtime. The original exact-
    # string substitution missed these; the sed regex closes the class.

    def test_block_rm_ifs_substring_expansion(self, run_hook):
        """rm${IFS:0:1}-rf / — IFS substring expansion (first char) must block."""
        _block(run_hook, "rm${IFS:0:1}-rf /", expected_reason="rm -rf")

    def test_block_rm_ifs_pattern_removal(self, run_hook):
        """rm${IFS%??}-rf / — IFS pattern-removal expansion must block."""
        _block(run_hook, "rm${IFS%??}-rf /", expected_reason="rm -rf")

    def test_block_rm_ifs_prefix_removal(self, run_hook):
        """rm${IFS#x}-rf / — IFS prefix-removal expansion must block."""
        _block(run_hook, "rm${IFS#x}-rf /", expected_reason="rm -rf")

    def test_block_rm_ifs_substitution(self, run_hook):
        """rm${IFS/x/y}-rf / — IFS substitution expansion must block."""
        _block(run_hook, "rm${IFS/x/y}-rf /", expected_reason="rm -rf")

    def test_allow_unrelated_ifsx_variable(self, run_hook):
        """${IFSx} is a DIFFERENT variable from IFS (not a param-expansion of
        IFS) and must NOT be normalized to a space. echo "${IFSx}foo" is
        a safe command and should be allowed."""
        _allow(run_hook, 'echo "${IFSx}foo"')

    # -----------------------------------------------------------------------
    # H1 fix: fork bomb extra-whitespace variant
    # -----------------------------------------------------------------------

    def test_block_fork_bomb_extra_space(self, run_hook):
        """f() { f | f & }; f — spaces between () and { must block.

        The cycle-2 regex \\(\\)\\{ required `(){` with no intervening space.
        The classic-spaced form `() {` bypassed it.  The cycle-3 fix uses
        \\(\\)[[:space:]]*\\{ which matches zero or more spaces between
        the closing paren and the opening brace.
        """
        _block(run_hook, "f() { f | f & }; f")

    def test_block_fork_bomb_no_space_preserved(self, run_hook):
        """f(){f|f&};f — no-space form must still block (cycle-2 fix preserved)."""
        _block(run_hook, "f(){f|f&};f")


# ---------------------------------------------------------------------------
# No-Python fallback path: pattern checks still apply (L001 NUL guard inactive)
# ---------------------------------------------------------------------------

class TestNoPythonFallback:
    """When neither python3 nor python is on PATH, the hook falls back to a
    sed-based JSON extractor. The L001 NUL-byte guard is documented as
    inactive in this path, but the downstream bash pattern checks (rm -rf,
    git reset --hard, chmod 777, etc.) still BLOCK dangerous commands.

    Without this coverage, a regression to fail-open (exit 0) on Python-less
    hosts would silently allow naked `rm -rf /`. The PR #23 review caught
    exactly this regression after the L001 guard was added.

    Strategy: write a wrapper bash script that defines and exports a
    `command` shell function which intercepts `command -v python3` /
    `command -v python` calls and returns 1, then exec the hook. All
    other `command` invocations delegate to the builtin via `builtin
    command "$@"`. This approach is robust to merged-/usr layouts
    (Debian/Ubuntu/Fedora where /bin -> /usr/bin and python3 + cat/sed/tr
    all live in /usr/bin together — PATH-stripping would lose the GNU
    tools the sed fallback needs), works regardless of how many Python
    installs are on PATH, and doesn't depend on filesystem layout.
    """

    @staticmethod
    def _run_no_python(hook_path, stdin_json, cwd):
        """Invoke a hook with `command -v python[3]` overridden to return 1.

        Paths are normalized to forward-slash form so that Git Bash on
        Windows (which interprets backslashes inside double-quoted
        strings as escape sequences) can resolve them correctly across
        the wrapper -> inner bash exec chain.
        """
        import os
        import shutil
        import subprocess
        import tempfile
        bash_bin = shutil.which("bash") or "bash"
        wrapper_content = (
            "#!/usr/bin/env bash\n"
            "# Override the `command` builtin to intercept python lookups.\n"
            "command() {\n"
            "    if [[ \"$1\" == \"-v\" && ( \"$2\" == \"python3\" || \"$2\" == \"python\" ) ]]; then\n"
            "        return 1\n"
            "    fi\n"
            "    builtin command \"$@\"\n"
            "}\n"
            "export -f command\n"
            "exec bash \"$@\"\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False, encoding="utf-8"
        ) as wrapper_file:
            wrapper_file.write(wrapper_content)
            wrapper_path = wrapper_file.name
        try:
            os.chmod(wrapper_path, 0o755)
            # Forward-slash form for Git Bash compatibility on Windows.
            wrapper_arg = wrapper_path.replace("\\", "/")
            hook_arg = str(hook_path).replace("\\", "/")
            return subprocess.run(
                [bash_bin, wrapper_arg, hook_arg],
                input=stdin_json,
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=15,
            )
        finally:
            try:
                os.unlink(wrapper_path)
            except OSError:
                pass

    def test_no_python_pattern_check_still_blocks_rm_rf_slash(
        self, repo_root
    ):
        """Without Python, rm -rf / must still be BLOCKed by pattern check."""
        hook_path = repo_root / ".armature" / "hooks" / "block-dangerous-commands.sh"
        result = self._run_no_python(
            hook_path,
            '{"tool_input":{"command":"rm -rf /"}}',
            repo_root,
        )
        assert result.returncode == 2, (
            f"no-Python fallback must still BLOCK rm -rf /, "
            f"got exit {result.returncode}; stderr={result.stderr[:300]!r}"
        )
        assert "BLOCK" in result.stderr

    def test_no_python_pattern_check_still_blocks_git_reset_hard(
        self, repo_root
    ):
        """Without Python, git reset --hard must still be BLOCKed."""
        hook_path = repo_root / ".armature" / "hooks" / "block-dangerous-commands.sh"
        result = self._run_no_python(
            hook_path,
            '{"tool_input":{"command":"git reset --hard"}}',
            repo_root,
        )
        assert result.returncode == 2, (
            f"no-Python fallback must still BLOCK git reset --hard, "
            f"got exit {result.returncode}; stderr={result.stderr[:300]!r}"
        )

    def test_no_python_safe_command_still_allowed(self, repo_root):
        """Without Python, a safe command (echo) must still ALLOW (exit 0)."""
        hook_path = repo_root / ".armature" / "hooks" / "block-dangerous-commands.sh"
        result = self._run_no_python(
            hook_path,
            '{"tool_input":{"command":"echo hello"}}',
            repo_root,
        )
        assert result.returncode == 0, (
            f"no-Python fallback must still ALLOW safe commands, "
            f"got exit {result.returncode}; stderr={result.stderr[:300]!r}"
        )
        assert "ADVISORY" in result.stderr  # advisory about no-Python fallback

    def test_block_fork_bomb_classic_preserved(self, run_hook):
        """:(){ :|:& };: — classic form must still block (preserved)."""
        _block(run_hook, ":(){ :|:& };:")
