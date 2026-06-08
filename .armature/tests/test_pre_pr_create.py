"""Regression tests for .armature/hooks/pre-pr-create.sh.

Spawns the hook as a subprocess with controlled stdin + environment and
asserts exit codes against the Phase B contract (advisory vs enforcement).

Covers 14 security-audit rounds documented in the hook's inline comments
and carried forward from the security-audit reference implementation.

Run:
    python -m pytest .armature/tests/test_pre_pr_create.py -v
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Resolve bash — skip entire module if unavailable.
# ---------------------------------------------------------------------------
BASH_BIN = shutil.which("bash")
if BASH_BIN is None:
    pytest.skip("bash not available on PATH", allow_module_level=True)

# Use canonical path derivation (same pattern as test_red_team_check.py).
_REPO_ROOT = Path(
    subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
    ).strip()
)

# Relative path from repo root so it resolves correctly under both
# Git Bash (C:/...) and WSL bash (/mnt/c/...) when cwd is set.
HOOK = ".armature/hooks/pre-pr-create.sh"


# ---------------------------------------------------------------------------
# Local hook runner — wraps the bash subprocess call.
#
# Returns (returncode, stderr_text).
#
# Note: subprocess.run env= does NOT propagate Windows env vars to WSL bash
# (env vars need WSLENV listing). To stay cross-platform we set the env
# vars INSIDE the bash command via the `env` builtin, which is honored
# regardless of how the shell received its parent environment.
# ---------------------------------------------------------------------------

def _run_hook(command, *, enforce=False, force_red_team=False, raw_stdin=None):
    """Invoke pre-pr-create.sh with stdin JSON {tool_input: {command: ...}}.

    Returns (returncode, stderr_text).
    """
    if raw_stdin is None:
        payload = {"tool_input": {"command": command}}
        stdin_bytes = json.dumps(payload).encode("utf-8")
    else:
        stdin_bytes = raw_stdin

    env_prefix = []
    if enforce:
        env_prefix.append("ARMATURE_RED_TEAM_ENFORCE=1")
    if force_red_team:
        env_prefix.append("FORCE_RED_TEAM=1")

    if env_prefix:
        # bash -c "env VAR1=1 VAR2=1 bash hook"
        bash_cmd = "env " + " ".join(env_prefix) + " bash " + HOOK
        args = [BASH_BIN, "-c", bash_cmd]
    else:
        args = [BASH_BIN, HOOK]

    proc = subprocess.run(
        args,
        input=stdin_bytes,
        capture_output=True,
        cwd=str(_REPO_ROOT),
        timeout=15,
    )
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def _run_hook_enforce_value(
    command,
    enforce_value,
    *,
    force_red_team=True,
    inline_command=None,
):
    """Run the hook with ARMATURE_RED_TEAM_ENFORCE set to an exact string value.

    Uses subprocess env= dict to avoid shell-quoting issues with values that
    contain spaces, mixed case, or special characters.

    Args:
        command: the bash command string placed in tool_input.command.
        enforce_value: exact string to set as ARMATURE_RED_TEAM_ENFORCE,
            or None to leave the variable unset entirely.
        force_red_team: whether to set FORCE_RED_TEAM=1 (ambient env var).
        inline_command: if not None, use this as the command string instead
            (allows testing inline-override cases where the command itself
            carries the ARMATURE_RED_TEAM_ENFORCE= prefix).

    Returns (returncode, stderr_text).
    """
    cmd_str = inline_command if inline_command is not None else command
    payload = {"tool_input": {"command": cmd_str}}
    stdin_bytes = json.dumps(payload).encode("utf-8")

    env = os.environ.copy()
    if enforce_value is None:
        env.pop("ARMATURE_RED_TEAM_ENFORCE", None)
    else:
        env["ARMATURE_RED_TEAM_ENFORCE"] = enforce_value
    if force_red_team:
        env["FORCE_RED_TEAM"] = "1"
    else:
        env.pop("FORCE_RED_TEAM", None)

    proc = subprocess.run(
        [BASH_BIN, HOOK],
        input=stdin_bytes,
        capture_output=True,
        env=env,
        cwd=str(_REPO_ROOT),
        timeout=15,
    )
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


# ===========================================================================
# BackslashNewlineBypassTests
# ===========================================================================

class TestBackslashNewlineBypass:
    """Round 1: line continuation must not bypass detection."""

    def test_backslash_newline_advisory(self):
        # gh<space>\<newline><space>pr create — bash collapses backslash-newline
        # and executes `gh pr create`. The hook must recognize this.
        cmd = "gh \\\n pr create --title X"
        rc, _ = _run_hook(cmd)
        # Without ENFORCE: triggered -> advisory exit 0 (this branch trips LOC + components)
        assert rc == 0

    def test_backslash_newline_enforce_blocks(self):
        cmd = "gh \\\n pr create"
        rc, stderr = _run_hook(cmd, enforce=True, force_red_team=True)
        assert rc == 2, "backslash-newline must NOT bypass under ENFORCE"
        assert "BLOCK" in stderr

    def test_backslash_newline_between_pr_and_create(self):
        cmd = "gh pr \\\n create"
        rc, _ = _run_hook(cmd, enforce=True, force_red_team=True)
        assert rc == 2

    def test_crlf_line_continuation_enforce_blocks(self):
        """Self-audit round 2 Phase 0: CRLF line continuation (Windows-pasted
        multi-line command) was a residual bypass — round-1 regex matched only
        LF, leaving \\<CR><LF> with the backslash still present."""
        cmd = "gh \\\r\n pr create"
        rc, stderr = _run_hook(cmd, enforce=True, force_red_team=True)
        assert rc == 2, "CRLF line continuation must not bypass"
        assert "BLOCK" in stderr


# ===========================================================================
# CodexRoundTwoP1Tests
# ===========================================================================

class TestCodexRoundTwoP1:
    """Codex round 2 P1 findings: chained operators and env-prefix."""

    def test_chained_semi_unspaced_under_enforce(self):
        """shlex.split lumped `;` with adjacent token, missing segment boundary.
        punctuation_chars=True fixes it."""
        rc, stderr = _run_hook(
            "git push; gh pr create", enforce=True, force_red_team=True
        )
        assert rc == 2, "chained ; must mark segment boundary"
        assert "BLOCK" in stderr

    def test_chained_semi_no_space_under_enforce(self):
        """No space at all between push and ;."""
        rc, _ = _run_hook(
            "git push;gh pr create", enforce=True, force_red_team=True
        )
        assert rc == 2

    def test_chained_pipe_under_enforce(self):
        rc, _ = _run_hook(
            "echo data | gh pr create", enforce=True, force_red_team=True
        )
        assert rc == 2

    def test_chained_or_under_enforce(self):
        rc, _ = _run_hook(
            "false || gh pr create", enforce=True, force_red_team=True
        )
        assert rc == 2

    def test_env_prefix_under_enforce(self):
        """GH_TOKEN=x gh pr create is a normal bash invocation where bash
        treats the assignment as temporary env for the following command."""
        rc, stderr = _run_hook(
            "GH_TOKEN=abc gh pr create", enforce=True, force_red_team=True
        )
        assert rc == 2, "env-prefix gh pr create must not bypass"
        assert "BLOCK" in stderr

    def test_env_prefix_multiple_under_enforce(self):
        """Multiple env assignments before the command."""
        rc, _ = _run_hook(
            "GH_TOKEN=a GH_HOST=b gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_env_prefix_after_chain_under_enforce(self):
        """Env-prefix at a chained segment start."""
        rc, _ = _run_hook(
            "true && GH_TOKEN=x gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_lone_env_assignment_no_op(self):
        """Just a variable assignment with no command — should not trigger."""
        rc, _ = _run_hook("FOO=bar")
        assert rc == 0


# ===========================================================================
# CodexRoundThreeP2Tests
# ===========================================================================

class TestCodexRoundThreeP2:
    """Codex round 3 P2: `env` command wrapper bypass."""

    def test_env_wrapper_bare(self):
        """`env gh pr create` — env with no assignments, just the command."""
        rc, stderr = _run_hook(
            "env gh pr create", enforce=True, force_red_team=True
        )
        assert rc == 2, "env wrapper must not bypass under ENFORCE"
        assert "BLOCK" in stderr

    def test_env_wrapper_with_single_assignment(self):
        rc, _ = _run_hook(
            "env GH_TOKEN=abc gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_env_wrapper_with_multiple_assignments(self):
        rc, _ = _run_hook(
            "env GH_TOKEN=a GH_HOST=b gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_env_wrapper_with_flags(self):
        """`env -i gh pr create` clears env then runs gh."""
        rc, _ = _run_hook(
            "env -i gh pr create", enforce=True, force_red_team=True
        )
        assert rc == 2

    def test_env_wrapper_after_chain(self):
        rc, _ = _run_hook(
            "true && env GH_TOKEN=x gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_env_as_argument_no_op(self):
        """`echo env gh pr create` — `env` is an argument to echo, NOT a
        wrapper. The detector must NOT enter wrapper-handling here."""
        rc, _ = _run_hook("echo env gh pr create")
        assert rc == 0
        # Also under ENFORCE: still not a real gh-pr-create invocation
        rc, _ = _run_hook(
            "echo env gh pr create", enforce=True, force_red_team=True
        )
        assert rc == 0, "env-as-argument must not trigger under ENFORCE"


# ===========================================================================
# KnownLimitationTests
# ===========================================================================

class TestKnownLimitations:
    """Documented bypass paths that the shlex-based tokenizer CANNOT
    detect without context-aware bash parsing. These tests assert the
    LIMITATION is current behavior — if a future PR adds a real bash
    parser, these tests should flip to assert blocking."""

    def test_if_then_gh_pr_create_limitation(self):
        """`if true; then gh pr create; fi` — `then` is a bash reserved
        word command-introducer, but shlex tokenizes it as ordinary text.
        Adding `then` to SEPS would create false positives on
        `echo then gh pr create`. Documented limitation."""
        rc, _ = _run_hook(
            "if true; then gh pr create; fi",
            enforce=True,
            force_red_team=True,
        )
        # Currently NOT detected — exits 0 (allow) even under ENFORCE.
        assert rc == 0

    def test_negation_prefix_limitation(self):
        """`! gh pr create` — `!` inverts exit status. Adding to SEPS
        would create false positive on `echo ! gh pr create`. Documented
        limitation; the pattern is uncommon for side-effect commands."""
        rc, _ = _run_hook(
            "! gh pr create", enforce=True, force_red_team=True
        )
        assert rc == 0

    def test_backtick_command_substitution_limitation(self):
        """``gh pr create`` — backticks attach to adjacent tokens.
        Documented limitation; backtick syntax is deprecated in favor of
        $(...) which IS detected correctly."""
        rc, _ = _run_hook(
            "`gh pr create`", enforce=True, force_red_team=True
        )
        assert rc == 0

    def test_dollar_paren_substitution_works(self):
        """Counter to backtick limitation: `$(gh pr create)` IS detected
        because shlex tokenizes `$` and `(` as separate tokens with
        punctuation_chars=True, so `(` triggers segment_start and the
        next token is `gh`."""
        rc, _ = _run_hook(
            "$(gh pr create)", enforce=True, force_red_team=True
        )
        assert rc == 2, "command substitution via $() IS detected"

    def test_subshell_works(self):
        """`(gh pr create)` — subshell. `(` is a SEPS token, so `gh`
        is at segment_start after."""
        rc, _ = _run_hook(
            "(gh pr create)", enforce=True, force_red_team=True
        )
        assert rc == 2


# ===========================================================================
# CodexRoundFourP2Tests
# ===========================================================================

class TestCodexRoundFourP2:
    """Codex round 4 P2: `env` flags that take a separate operand token."""

    def test_env_unset_short_form(self):
        """`env -u VAR gh pr create` — `-u` takes NAME operand."""
        rc, stderr = _run_hook(
            "env -u GH_TOKEN gh pr create", enforce=True, force_red_team=True
        )
        assert rc == 2
        assert "BLOCK" in stderr

    def test_env_chdir_short_form(self):
        """`env -C /tmp gh pr create` — `-C` takes DIR operand."""
        rc, _ = _run_hook(
            "env -C /tmp gh pr create", enforce=True, force_red_team=True
        )
        assert rc == 2

    def test_env_unset_long_form_with_equals(self):
        """`env --unset=NAME` — operand embedded in same shlex token; covered
        by the pre-existing flag-skip pass."""
        rc, _ = _run_hook(
            "env --unset=GH_TOKEN gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_env_unset_long_form_with_space(self):
        """`env --unset NAME` (some env builds accept space form)."""
        rc, _ = _run_hook(
            "env --unset GH_TOKEN gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_env_chdir_long_form_with_equals(self):
        rc, _ = _run_hook(
            "env --chdir=/tmp gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_env_combined_flags_with_operand(self):
        """`env -i -u VAR gh pr create` — clear-env, then unset, then run."""
        rc, _ = _run_hook(
            "env -i -u GH_TOKEN gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_env_mixed_operand_and_assignment(self):
        """`env -u OLD NEW_VAR=val gh pr create` — operand-taking flag THEN
        env-assignment THEN command."""
        rc, _ = _run_hook(
            "env -u OLD NEW_VAR=val gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_env_dash_dash_separator(self):
        """`env -- gh pr create` — `--` ends option parsing in env."""
        rc, _ = _run_hook(
            "env -- gh pr create", enforce=True, force_red_team=True
        )
        assert rc == 2

    def test_env_unknown_short_flag_does_not_swallow_command(self):
        """`env -x gh pr create` — `-x` is not in operand-take list, so
        next token is treated as the command. (`-x` is not a real env flag
        but the test guards against false-positives in the allow-list.)"""
        rc, _ = _run_hook(
            "env -x gh pr create", enforce=True, force_red_team=True
        )
        # `-x` consumed as a generic flag (round-3 behaviour preserved);
        # next token `gh` is correctly recognised as the command.
        assert rc == 2


# ===========================================================================
# CodexRoundSevenP2Tests
# ===========================================================================

class TestCodexRoundSevenP2:
    """Codex round 7 P2: mid-word `#` was dropping rest of line.

    shlex.shlex defaults `commenters="#"` which strips `#` and everything
    after to EOL. Bash treats `#` as a comment introducer ONLY at word-
    start, so `echo issue#123; gh pr create` had `;gh pr create` dropped
    by shlex and bypassed detection. Fix: clear `lex.commenters`.
    """

    def test_mid_word_hash_does_not_drop_chained_command(self):
        """The codex P2 case: issue reference with mid-word `#`."""
        rc, stderr = _run_hook(
            "echo issue#123; gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2
        assert "BLOCK" in stderr

    def test_mid_word_hash_unspaced(self):
        """Without space before `;` — confirms tokenizer behavior."""
        rc, _ = _run_hook(
            "echo issue#123;gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_url_fragment_hash_does_not_drop_chained_command(self):
        """`url#anchor` is a common pattern; `#anchor` is not a comment."""
        rc, _ = _run_hook(
            "url=https://example.com/x#anchor; gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_env_assign_with_hash_in_value(self):
        """`VAR=val#suffix` — `#suffix` is part of the env-assign value."""
        rc, _ = _run_hook(
            "VAR=value#suffix gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_leading_comment_still_skipped(self):
        """Regression guard: `# gh pr create` (word-start `#`) is still NOT
        detected as a real invocation — it is a comment in bash."""
        rc, _ = _run_hook("# gh pr create")
        assert rc == 0
        # Also under ENFORCE
        rc, _ = _run_hook("# gh pr create", enforce=True, force_red_team=True)
        assert rc == 0

    def test_trailing_comment_still_skipped(self):
        """Regression guard: trailing `# ...` is still NOT a trigger source."""
        rc, _ = _run_hook("ls # then gh pr create maybe")
        assert rc == 0

    def test_quoted_hash_preserved(self):
        """Regression guard: `#` inside quoted string is preserved (was
        already correct because shlex respects quotes; this locks it in)."""
        rc, _ = _run_hook(
            'echo "comment # inside"; gh pr create',
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2


# ===========================================================================
# CodexRoundEightP2Tests
# ===========================================================================

class TestCodexRoundEightP2:
    """Codex round 8 P2: unquoted LF is a command separator in bash but shlex
    treats it as ordinary whitespace. Multi-line commands like
    `echo ok\\ngh pr create` bypassed detection because `gh` was not
    at_segment_start after `ok`.

    Fix: quote-aware preprocess replaces unquoted LF/CR with `;` so shlex
    tokenizes them as segment separators."""

    def test_multiline_command_blocks_under_enforce(self):
        """The codex P2 case directly: LF between cmd1 and gh pr create."""
        rc, stderr = _run_hook(
            "echo ok\ngh pr create --draft",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2
        assert "BLOCK" in stderr

    def test_three_line_script(self):
        """Multiple LF separators in one command line."""
        rc, _ = _run_hook(
            "cmd1\ncmd2\ngh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_crlf_separator_windows_input(self):
        """Windows-pasted multi-line with CRLF endings."""
        rc, _ = _run_hook(
            "echo ok\r\ngh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_cr_only_old_mac_separator(self):
        """Old-Mac CR-only line endings still produce a separator."""
        rc, _ = _run_hook(
            "echo ok\rgh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_lf_inside_double_quotes_does_not_split(self):
        """Regression guard: LF inside a double-quoted string stays literal,
        does NOT introduce a separator that could create a false positive.
        The actual gh pr create comes after the `;`, so this still
        triggers. The point: the LF inside "..." is NOT converted to ;."""
        rc, _ = _run_hook(
            'echo "line1\nline2"; gh pr create',
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_lf_inside_single_quotes_does_not_split(self):
        """Same as above but with single quotes."""
        rc, _ = _run_hook(
            "echo 'line1\nline2'; gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_multiline_no_gh_pr_create_no_op(self):
        """Multi-line command that does NOT include gh pr create stays
        allowed (regression guard against over-triggering)."""
        rc, _ = _run_hook("echo line1\necho line2\nls -la")
        assert rc == 0

    def test_multiline_gh_pr_view_not_create(self):
        """Multi-line command where the gh sub-verb is `view` not `create`."""
        rc, _ = _run_hook("echo ok\ngh pr view 123")
        assert rc == 0


# ===========================================================================
# CodexRoundNineP1Tests
# ===========================================================================

class TestCodexRoundNineP1:
    """Codex round 9 P1: gh parent-level flags between `gh` and `pr`
    (notably `-R`/`--repo`) were not skipped by detection. The
    `[gh, pr, create]` consecutive-token check missed `gh -R owner/repo
    pr create`, a valid gh CLI invocation.

    Fix: after matching `gh` at segment start, skip parent flags (with
    operand consumption for an allow-list) before checking for [pr, create]."""

    def test_repo_short_form_blocks(self):
        """The codex P1 case: `gh -R owner/repo pr create`."""
        rc, stderr = _run_hook(
            "gh -R owner/repo pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2
        assert "BLOCK" in stderr

    def test_repo_long_form_with_space(self):
        """`gh --repo owner/repo pr create` — operand as separate token."""
        rc, _ = _run_hook(
            "gh --repo owner/repo pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_repo_long_form_with_equals(self):
        """`gh --repo=owner/repo pr create` — operand in same token."""
        rc, _ = _run_hook(
            "gh --repo=owner/repo pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_hostname_flag(self):
        """`gh --hostname github.example.com pr create`."""
        rc, _ = _run_hook(
            "gh --hostname github.example.com pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_chained_with_parent_flag(self):
        """Chained command with parent flag."""
        rc, _ = _run_hook(
            "git push && gh -R x/y pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_parent_flag_with_different_verb_does_not_match(self):
        """`gh -R owner/repo pr view` is NOT a PR-create — must not trigger."""
        rc, _ = _run_hook(
            "gh -R owner/repo pr view",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0

    def test_parent_flag_with_different_subcommand_does_not_match(self):
        """`gh -R owner/repo issue create` is a different subcommand."""
        rc, _ = _run_hook(
            "gh -R owner/repo issue create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0

    def test_parent_flag_with_comment_skipped(self):
        """Leading `#` makes the whole thing a comment — no trigger."""
        rc, _ = _run_hook("# gh -R x/y pr create")
        assert rc == 0

    def test_combined_parent_flags(self):
        """Multiple parent flags + operand-flag combinations."""
        rc, _ = _run_hook(
            "gh --repo owner/repo --hostname gh.example.com pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2


# ===========================================================================
# CodexRoundElevenP2Tests
# ===========================================================================

class TestCodexRoundElevenP2:
    """Codex round 11 P2: gh CLI accepts `-R/--repo` at the `gh pr` parent
    in addition to the `gh` root, so `gh pr -R owner/repo create` is a
    valid PR creation form. Round 9 only skipped flags BETWEEN `gh` and
    `pr`; flags BETWEEN `pr` and `create` need the same skip-loop treatment."""

    def test_pr_level_repo_short_form(self):
        """The codex P2 case: `gh pr -R owner/repo create`."""
        rc, stderr = _run_hook(
            "gh pr -R owner/repo create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2
        assert "BLOCK" in stderr

    def test_pr_level_repo_long_form_with_space(self):
        rc, _ = _run_hook(
            "gh pr --repo owner/repo create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_pr_level_repo_long_form_with_equals(self):
        rc, _ = _run_hook(
            "gh pr --repo=owner/repo create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_pr_level_hostname(self):
        rc, _ = _run_hook(
            "gh pr --hostname gh.example.com create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_both_levels_simultaneously(self):
        """Flags at BOTH parent-level and pr-level."""
        rc, _ = _run_hook(
            "gh -R a/b pr --repo c/d create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_pr_level_flag_wrong_verb_does_not_match(self):
        """Regression: `gh pr -R x/y view` is NOT a PR create — must not trigger."""
        rc, _ = _run_hook(
            "gh pr -R owner/repo view",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0

    def test_pr_level_flag_chained(self):
        """Chained command with pr-level flag."""
        rc, _ = _run_hook(
            "git push && gh pr -R x/y create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2


# ===========================================================================
# CodexRoundTwelveP2Tests
# ===========================================================================

class TestCodexRoundTwelveP2:
    """Codex round 12 P2: bash inline env-prefix on the gh-pr-create command
    (e.g. `ARMATURE_RED_TEAM_ENFORCE=true gh pr create`) sets env vars ONLY
    for the next command, not for the hook process. The hook must extract
    these from the command string and honor them, not rely solely on
    os.environ."""

    def test_inline_enforce_blocks_without_env_var(self):
        """The codex P2 case: inline ENFORCE=true triggers blocking even
        though the hook process env does NOT have ARMATURE_RED_TEAM_ENFORCE."""
        # enforce=False at the harness level (no env-var passed) — relies
        # purely on the inline prefix. force_red_team=True so trigger fires.
        rc, stderr = _run_hook(
            "ARMATURE_RED_TEAM_ENFORCE=true FORCE_RED_TEAM=1 gh pr create",
            enforce=False,
            force_red_team=False,
        )
        assert rc == 2, "inline ARMATURE_RED_TEAM_ENFORCE=true must block"
        assert "BLOCK" in stderr

    def test_inline_enforce_1_value(self):
        """Numeric `=1` value should also block."""
        rc, _ = _run_hook(
            "ARMATURE_RED_TEAM_ENFORCE=1 FORCE_RED_TEAM=1 gh pr create",
            enforce=False,
            force_red_team=False,
        )
        assert rc == 2

    def test_inline_force_red_team_triggers(self):
        """Inline FORCE_RED_TEAM=1 should fire the trigger even when the
        hook process env does NOT have it set."""
        rc, _ = _run_hook(
            "FORCE_RED_TEAM=1 ARMATURE_RED_TEAM_ENFORCE=1 gh pr create",
            enforce=False,
            force_red_team=False,
        )
        assert rc == 2

    def test_inline_enforce_other_segment_does_not_apply(self):
        """Inline assignment on a DIFFERENT segment must NOT apply to the
        gh-pr-create segment (bash inline prefix is per-command, not global)."""
        rc, _ = _run_hook(
            "ARMATURE_RED_TEAM_ENFORCE=true cmd1; FORCE_RED_TEAM=1 gh pr create",
            enforce=False,
            force_red_team=False,
        )
        # The enforce on cmd1 does NOT carry over to gh pr create's segment.
        # FORCE_RED_TEAM=1 inline on gh's segment triggers; but no ENFORCE
        # on gh's segment (and no env-level ENFORCE) means advisory.
        assert rc == 0
        # The stderr should be ADVISORY, not BLOCK.

    def test_inline_inside_env_wrapper(self):
        """`env ARMATURE_RED_TEAM_ENFORCE=true gh pr create` — inside the
        env wrapper, the override should still be honored."""
        rc, _ = _run_hook(
            "env ARMATURE_RED_TEAM_ENFORCE=true FORCE_RED_TEAM=1 gh pr create",
            enforce=False,
            force_red_team=False,
        )
        assert rc == 2

    def test_inline_false_does_not_downgrade_env(self):
        """If env has ARMATURE_RED_TEAM_ENFORCE=true and operator types
        inline `=false`, current implementation keeps ENFORCING True (OR
        semantics, conservative direction). This is acceptable: the inline
        downgrade is not a documented escape hatch."""
        rc, _ = _run_hook(
            "ARMATURE_RED_TEAM_ENFORCE=false FORCE_RED_TEAM=1 gh pr create",
            enforce=True,  # env-level ENFORCE
            force_red_team=False,
        )
        # env-level ENFORCE=true still applies; inline=false does NOT downgrade.
        assert rc == 2

    def test_inline_enforce_without_force_no_trigger(self):
        """`ARMATURE_RED_TEAM_ENFORCE=true gh pr create` with no other
        triggers active. Just verify hook returns an integer exit code
        (no exception) — the result depends on whether the current branch
        has LOC/components triggers active."""
        rc, _ = _run_hook(
            "ARMATURE_RED_TEAM_ENFORCE=true gh pr create",
            enforce=False,
            force_red_team=False,
        )
        # On this PR branch, LOC+components trigger may fire; with inline
        # ENFORCE applied, expect block. The test exercises the inline-
        # override extraction path regardless of trigger source.
        assert rc in (0, 2)


# ===========================================================================
# CodexRoundThirteenP2Tests
# ===========================================================================

class TestCodexRoundThirteenP2:
    """Codex round 13 P2: round 7 cleared `lex.commenters` to treat mid-word
    `#` as a literal char. That fix REMOVED bash word-start comment handling,
    so `echo ok # comment; gh pr create` falsely triggered the gate even
    though bash treats `; gh pr create` as part of the comment.

    Fix: distinguish word-start `#` (real comment) from mid-word `#`
    (literal char) in the LF-to-separator walk."""

    def test_trailing_comment_with_chained_pr_create_does_not_trigger(self):
        """The codex P2 case: `echo ok # comment; gh pr create` — the
        `; gh pr create` is part of the trailing comment, not a real
        command."""
        rc, _ = _run_hook(
            "echo ok # comment; gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "trailing comment must not be a real command"

    def test_trailing_comment_no_op_under_enforce(self):
        """Same idea with a more elaborate comment."""
        rc, _ = _run_hook(
            "ls # then run gh pr create later maybe",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0

    def test_full_leading_comment_no_op(self):
        rc, _ = _run_hook(
            "# gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0

    def test_comment_after_separator(self):
        """`cmd1;#gh pr create` — `#` immediately after `;` is word-start."""
        rc, _ = _run_hook(
            "cmd1;#gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0

    def test_mid_word_hash_still_works_round7_regression(self):
        """Regression guard for round 7: mid-word `#` is NOT a comment.
        `echo issue#123; gh pr create` must still trigger because `; gh
        pr create` is a real subsequent command."""
        rc, _ = _run_hook(
            "echo issue#123; gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_trailing_comment_with_newline_then_gh_pr_create(self):
        """`echo ok # comment\\ngh pr create` — the comment ends at LF,
        and the next line is a real `gh pr create` that runs."""
        rc, _ = _run_hook(
            "echo ok # comment\ngh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_quoted_hash_in_dquote_preserved(self):
        """`#` inside double quotes is literal, not a comment."""
        rc, _ = _run_hook(
            'echo "comment # inside"; gh pr create',
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_trailing_comment_after_gh_pr_create_still_blocks(self):
        """`gh pr create  # trailing comment` — gh pr create RUNS,
        the trailing comment does not change that."""
        rc, _ = _run_hook(
            "gh pr create  # this is a comment",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2

    def test_url_fragment_still_works(self):
        """URL with #anchor (mid-word #) must still be preserved."""
        rc, _ = _run_hook(
            "url=x.com/y#anchor; gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2


# ===========================================================================
# FalsePositiveTests
# ===========================================================================

class TestFalsePositives:
    """Self-audit: quoted strings + comments must NOT match."""

    def test_echo_squote_no_op(self):
        rc, stderr = _run_hook("echo 'gh pr create'")
        assert rc == 0
        assert "GATE-RED-TEAM-001" not in stderr

    def test_echo_dquote_no_op(self):
        rc, stderr = _run_hook('echo "gh pr create"')
        assert rc == 0
        assert "GATE-RED-TEAM-001" not in stderr

    def test_echo_dquote_enforce_does_not_block(self):
        """Even under ENFORCE, echoing the string must not block."""
        rc, _ = _run_hook('echo "gh pr create"', enforce=True, force_red_team=True)
        assert rc == 0

    def test_var_assignment_no_op(self):
        rc, _ = _run_hook("CMD='gh pr create'")
        assert rc == 0

    def test_comment_line_no_op(self):
        rc, _ = _run_hook("# gh pr create")
        assert rc == 0

    def test_trailing_comment_no_op(self):
        # The command is `ls`, with a trailing comment that contains the tokens.
        rc, _ = _run_hook("ls # then gh pr create maybe")
        assert rc == 0


# ===========================================================================
# RoundOneACRegressionTests
# ===========================================================================

class TestRoundOneACRegression:
    """Round-1 acceptance criteria — must still pass after all refactors."""

    def test_AC3_git_status(self):
        rc, _ = _run_hook("git status")
        assert rc == 0

    def test_AC3_gh_pr_view(self):
        rc, _ = _run_hook("gh pr view 123")
        assert rc == 0

    def test_AC3_gh_issue_create(self):
        rc, _ = _run_hook("gh issue create")
        assert rc == 0

    def test_AC3_xgh_prefix(self):
        rc, _ = _run_hook("xgh pr create")
        assert rc == 0

    def test_AC4_enforce_blocks_bare(self):
        rc, stderr = _run_hook("gh pr create", enforce=True, force_red_team=True)
        assert rc == 2
        assert "BLOCK" in stderr

    def test_AC5_advisory_soft_deploy(self):
        rc, stderr = _run_hook("gh pr create", enforce=False, force_red_team=True)
        assert rc == 0
        assert "ADVISORY" in stderr

    def test_AC9_NUL_block(self):
        raw = b'{"tool_input":{"command":"gh pr create\x00"}}'
        rc, stderr = _run_hook("", raw_stdin=raw)
        assert rc == 2
        assert "NUL" in stderr

    def test_no_command_field(self):
        rc, _ = _run_hook("", raw_stdin=b"{}")
        assert rc == 0

    def test_extra_whitespace(self):
        rc, _ = _run_hook("gh   pr   create")
        assert rc == 0

    def test_chained_after_and(self):
        rc, _ = _run_hook("git push && gh pr create")
        assert rc == 0

    def test_chained_after_semi(self):
        rc, _ = _run_hook("git push; gh pr create")
        assert rc == 0

    def test_chained_under_enforce_blocks(self):
        rc, _ = _run_hook(
            "git push && gh pr create", enforce=True, force_red_team=True
        )
        assert rc == 2

    def test_draft_variant(self):
        rc, _ = _run_hook("gh pr create --draft")
        assert rc == 0


# ===========================================================================
# CodexRoundFourteenP2Tests
# ===========================================================================

class TestCodexRoundFourteenP2:
    """Codex round 14 P2 (pre-pr-create.sh:498): `gh pr create --dry-run`
    only PRINTS PR details — it does NOT create a PR (gh manual: "Print
    details instead of creating the PR"). The gate was a false positive for
    this non-creating validation path.

    Fix: exempt `--dry-run` when it is a genuine standalone boolean flag in
    the create arguments. The exemption uses a value-flag-aware state machine
    to prevent the bypass: `gh pr create --title "--dry-run"` tokenizes to
    [..., "create", "--title", "--dry-run"] (shlex strips quotes) and gh
    DOES create the PR (title is literally "--dry-run"). The naive check
    would wrongly exempt it; the value-flag-aware scan skips tokens in value
    position so "--dry-run" as a title value does NOT exempt the invocation.
    """

    # --- Exemption cases (gate must allow) ----------------------------------

    def test_dry_run_bare_exits_zero(self):
        """`gh pr create --dry-run` — standalone dry-run, gate must allow."""
        rc, stderr = _run_hook(
            "gh pr create --dry-run",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "--dry-run must not be blocked under enforce"
        assert "BLOCK" not in stderr

    def test_dry_run_after_value_flag_exits_zero(self):
        """`gh pr create --title x --dry-run` — --dry-run appears after a
        value-taking flag; it is still a standalone flag (--title consumed
        `x`, not `--dry-run`)."""
        rc, _ = _run_hook(
            "gh pr create --title x --dry-run",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0

    def test_dry_run_before_value_flag_exits_zero(self):
        """`gh pr create --dry-run --title x` — --dry-run before a value-
        taking flag is also a standalone boolean flag."""
        rc, _ = _run_hook(
            "gh pr create --dry-run --title x",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0

    def test_dry_run_advisory_also_exits_zero(self):
        """`gh pr create --dry-run` in advisory (non-enforce) mode also
        exits 0 — exemption applies regardless of enforce state."""
        rc, _ = _run_hook(
            "gh pr create --dry-run",
            enforce=False,
            force_red_team=True,
        )
        assert rc == 0

    def test_dry_run_equals_true_exits_zero(self):
        """`--dry-run=true` is an explicit dry-run enable; still exempt."""
        rc, _ = _run_hook(
            "gh pr create --dry-run=true",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0

    # --- Anti-bypass cases (gate must STILL BLOCK) --------------------------

    def test_dry_run_as_title_value_still_blocks(self):
        """`gh pr create --title "--dry-run"` — shlex strips quotes, so the
        token stream is [..., "create", "--title", "--dry-run"]. The
        "--dry-run" token is in value position (consumed by --title) and
        MUST NOT exempt the invocation. gh creates the PR with title
        literally "--dry-run"."""
        rc, stderr = _run_hook(
            'gh pr create --title "--dry-run"',
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "--dry-run as --title value must still be blocked"
        assert "BLOCK" in stderr

    def test_dry_run_as_title_value_equals_form_still_blocks(self):
        """`gh pr create --title=--dry-run` — `--dry-run` is the value of
        `--title` via `=` form (embedded in same token). gh creates the PR;
        must still block."""
        rc, stderr = _run_hook(
            "gh pr create --title=--dry-run",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "--title=--dry-run must still be blocked"
        assert "BLOCK" in stderr

    def test_dry_run_equals_false_still_blocks(self):
        """`gh pr create --dry-run=false` — explicitly disabling dry-run;
        gh WILL create the PR. Must still block."""
        rc, stderr = _run_hook(
            "gh pr create --dry-run=false",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "--dry-run=false must still be blocked"
        assert "BLOCK" in stderr

    def test_no_dry_run_still_blocks(self):
        """Regression guard: `gh pr create` without --dry-run must still
        block in enforce mode (guards against the exemption logic being
        applied unconditionally)."""
        rc, stderr = _run_hook(
            "gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "plain gh pr create must still be blocked"
        assert "BLOCK" in stderr

    def test_recover_consumes_dry_run_still_blocks(self):
        """`gh pr create --recover --dry-run` — --recover is a value-taking
        option (gh: "Recover input from a failed run of create"). At runtime
        gh consumes --dry-run as --recover's VALUE, so the PR IS created.
        The gate must treat --dry-run as a value (not a standalone flag) and
        BLOCK. This was the bypass: --recover was missing from
        GH_CREATE_VALUE_FLAGS, so the scanner did not skip --dry-run and
        wrongly exempted the invocation."""
        rc, stderr = _run_hook(
            "gh pr create --recover --dry-run",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "--recover --dry-run must be blocked (--dry-run is --recover's value)"
        assert "BLOCK" in stderr

    def test_recover_dry_run_with_title_still_blocks(self):
        """`gh pr create --recover --dry-run --title t` — same bypass vector
        with an additional value-taking flag following. --dry-run is still
        --recover's value; gate must BLOCK."""
        rc, stderr = _run_hook(
            "gh pr create --recover --dry-run --title t",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "--recover --dry-run --title t must be blocked"
        assert "BLOCK" in stderr


# ===========================================================================
# CodexRoundFifteenP2Tests
# ===========================================================================

class TestCodexRoundFifteenP2:
    """Codex round 15 P2 (pre-pr-create.sh dry-run last-value): the dry-run
    scanner broke early on the FIRST --dry-run token, so a later
    --dry-run=false override was invisible. gh's pflag parser processes ALL
    flags and the LAST value wins.

    Fix: walk ALL post-create tokens; track the LAST --dry-run value in
    _dry_run_state (None/True/False). Exempt only when _dry_run_state is True.
    """

    # --- Codex bypass case (the confirmed P2) --------------------------------

    def test_dry_run_then_dry_run_false_blocks(self):
        """`gh pr create --dry-run --dry-run=false` — the codex P2 bypass.
        Old scanner stopped at the first --dry-run (True) and exempted.
        gh's pflag sees the final --dry-run=false and CREATES the PR.
        Gate must BLOCK."""
        rc, stderr = _run_hook(
            "gh pr create --dry-run --dry-run=false",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "--dry-run --dry-run=false (final false) must be blocked"
        assert "BLOCK" in stderr

    # --- Other last-value override cases ------------------------------------

    def test_dry_run_true_then_dry_run_false_blocks(self):
        """`gh pr create --dry-run=true --dry-run=false` — final value false;
        gh CREATES the PR. Gate must BLOCK."""
        rc, stderr = _run_hook(
            "gh pr create --dry-run=true --dry-run=false",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "--dry-run=true --dry-run=false (final false) must be blocked"
        assert "BLOCK" in stderr

    def test_dry_run_false_then_dry_run_allows(self):
        """`gh pr create --dry-run=false --dry-run` — final value is bare
        --dry-run (true). Real dry-run; gate must ALLOW."""
        rc, _ = _run_hook(
            "gh pr create --dry-run=false --dry-run",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "--dry-run=false --dry-run (final true) must be allowed"

    # --- gh pflag bool truth table -------------------------------------------

    def test_dry_run_equals_1_allows(self):
        """`--dry-run=1` is a pflag-true value; dry-run on. Gate must ALLOW."""
        rc, _ = _run_hook(
            "gh pr create --dry-run=1",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0

    def test_dry_run_equals_t_allows(self):
        """`--dry-run=t` is a pflag-true value. Gate must ALLOW."""
        rc, _ = _run_hook(
            "gh pr create --dry-run=t",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0

    def test_dry_run_equals_TRUE_allows(self):
        """`--dry-run=TRUE` is a pflag-true value. Gate must ALLOW."""
        rc, _ = _run_hook(
            "gh pr create --dry-run=TRUE",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0

    def test_dry_run_equals_0_blocks(self):
        """`--dry-run=0` is a pflag-false value; gh CREATES the PR. Gate
        must BLOCK."""
        rc, stderr = _run_hook(
            "gh pr create --dry-run=0",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "--dry-run=0 must be blocked"
        assert "BLOCK" in stderr

    def test_dry_run_equals_F_blocks(self):
        """`--dry-run=F` is a pflag-false value. Gate must BLOCK."""
        rc, stderr = _run_hook(
            "gh pr create --dry-run=F",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "--dry-run=F must be blocked"
        assert "BLOCK" in stderr

    # --- Regression guards (existing behavior preserved) --------------------

    def test_dry_run_bare_still_allows(self):
        """Regression: `gh pr create --dry-run` still exits 0."""
        rc, _ = _run_hook(
            "gh pr create --dry-run",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0

    def test_no_dry_run_still_blocks(self):
        """Regression: `gh pr create` (no --dry-run) still blocked."""
        rc, stderr = _run_hook(
            "gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2
        assert "BLOCK" in stderr

    def test_dry_run_as_title_value_still_blocks(self):
        """Regression: `gh pr create --title "--dry-run"` — --dry-run in
        value position must not exempt. Gate must BLOCK."""
        rc, stderr = _run_hook(
            'gh pr create --title "--dry-run"',
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2
        assert "BLOCK" in stderr

    def test_recover_consumes_dry_run_still_blocks(self):
        """Regression: `gh pr create --recover --dry-run` — --dry-run is
        --recover's value. Gate must BLOCK."""
        rc, stderr = _run_hook(
            "gh pr create --recover --dry-run",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2
        assert "BLOCK" in stderr

    # --- Interleaved value flags ---------------------------------------------

    def test_interleaved_value_flags_final_false_blocks(self):
        """`gh pr create --title x --dry-run --label y --dry-run=false` —
        interleaved value-taking flags; final --dry-run value is false.
        Gate must BLOCK."""
        rc, stderr = _run_hook(
            "gh pr create --title x --dry-run --label y --dry-run=false",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "final --dry-run=false after interleaved flags must block"
        assert "BLOCK" in stderr

    def test_dry_run_equals_false_still_blocks(self):
        """Regression: `gh pr create --dry-run=false` (already covered in
        round 14) still blocks under the new last-value logic."""
        rc, stderr = _run_hook(
            "gh pr create --dry-run=false",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2
        assert "BLOCK" in stderr


# ===========================================================================
# TestRedTeamComprehensive
# ===========================================================================

class TestRedTeamComprehensive:
    """Red-team findings applied to pre-pr-create.sh dry-run scanner and
    temp-file cleanup.

    MEDIUM-1: honor `--` end-of-options in the dry-run scanner.
      gh uses pflag, which treats bare `--` as end-of-options. Tokens AFTER
      `--` are positional arguments and `gh pr create` rejects positionals
      (it errors — does NOT create and does NOT dry-run). Therefore a
      `--dry-run` that appears after `--` must NOT count as a dry-run flag
      and must NOT exempt the gate.

    LOW-1: temp-file cleanup trap extended to INT/TERM/HUP signals so an
      interrupted hook does not leak the mktemp temp file. (Verified via
      grep; not exercised by subprocess tests.)
    """

    # --- MEDIUM-1: post-`--` --dry-run must NOT exempt -----------------------

    def test_post_double_dash_dry_run_blocks(self):
        """`gh pr create -- --dry-run` — MEDIUM-1 core case.

        The bare `--` is gh/pflag end-of-options. The `--dry-run` that
        follows is a positional argument; `gh pr create` errors on
        positionals and does NOT dry-run. The gate must BLOCK."""
        rc, stderr = _run_hook(
            "gh pr create -- --dry-run",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "post-`--` --dry-run must NOT exempt the gate (MEDIUM-1)"
        assert "BLOCK" in stderr

    def test_post_double_dash_dry_run_then_dry_run_false_blocks(self):
        """`gh pr create -- --dry-run --dry-run=false` — regression check.

        Both tokens are positionals (after `--`); neither is a real flag.
        The gate was already blocking this form but this test pins the
        expected behavior explicitly after the MEDIUM-1 fix."""
        rc, stderr = _run_hook(
            "gh pr create -- --dry-run --dry-run=false",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "post-`--` flags must not exempt (regression)"
        assert "BLOCK" in stderr

    def test_pre_double_dash_dry_run_allows(self):
        """`gh pr create --dry-run --` — pre-`--` --dry-run IS a real flag.

        The `--dry-run` comes before `--`, so pflag parses it as the
        dry-run flag (true). The trailing `--` does not change that. The
        scanner should stop at `--` and honor the pre-`--` _dry_run_state
        of True. Gate must ALLOW."""
        rc, _ = _run_hook(
            "gh pr create --dry-run --",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "pre-`--` --dry-run with trailing `--` must still be allowed"

    def test_title_then_double_dash_then_dry_run_blocks(self):
        """`gh pr create --title x -- --dry-run` — a value-taking flag before
        `--`, then `--dry-run` as a positional after `--`.

        The scan consumes `--title x` (x is --title's value), hits `--`
        (end-of-options sentinel), stops, and _dry_run_state is None.
        Gate must BLOCK."""
        rc, stderr = _run_hook(
            "gh pr create --title x -- --dry-run",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "--title x -- --dry-run must be blocked"
        assert "BLOCK" in stderr


# ===========================================================================
# TestAbsoluteGhPath (codex P2 — basename matching)
# ===========================================================================

class TestAbsoluteGhPath:
    """Codex P2 fix (pre-pr-create.sh:469): command-position match was an
    exact `tok == "gh"` check, so absolute/relative-path invocations such as
    `/usr/bin/gh pr create` and `./gh pr create` did not match, allowing the
    gate to exit 0 under ARMATURE_RED_TEAM_ENFORCE=1.

    Fix: extract the basename of the command token by splitting on both `/`
    and `\\` (os.path.basename is platform-dependent), then match basename
    `== "gh"` (POSIX) OR `basename.lower() == "gh.exe"` (Windows).
    """

    # --- BLOCK under enforce + trigger: absolute/relative POSIX paths --------

    def test_usr_bin_gh_blocks(self):
        """`/usr/bin/gh pr create` must be detected and blocked."""
        rc, stderr = _run_hook(
            "/usr/bin/gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "/usr/bin/gh pr create must be blocked"
        assert "BLOCK" in stderr

    def test_opt_homebrew_gh_blocks(self):
        """`/opt/homebrew/bin/gh pr create` (Homebrew on macOS) must block."""
        rc, stderr = _run_hook(
            "/opt/homebrew/bin/gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "/opt/homebrew/bin/gh pr create must be blocked"
        assert "BLOCK" in stderr

    def test_dotslash_gh_blocks(self):
        """`./gh pr create` (relative path in cwd) must block."""
        rc, stderr = _run_hook(
            "./gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "./gh pr create must be blocked"
        assert "BLOCK" in stderr

    def test_dotdot_bin_gh_blocks(self):
        """`../bin/gh pr create` (relative path one level up) must block."""
        rc, stderr = _run_hook(
            "../bin/gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "../bin/gh pr create must be blocked"
        assert "BLOCK" in stderr

    # --- BLOCK: Windows path forms -------------------------------------------

    def test_gh_exe_bare_blocks(self):
        """`gh.exe pr create` (Windows bare form) must block."""
        rc, stderr = _run_hook(
            "gh.exe pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "gh.exe pr create must be blocked"
        assert "BLOCK" in stderr

    def test_windows_full_path_gh_exe_blocks(self):
        """Quoted Windows full path `"C:\\Program Files\\GitHub CLI\\gh.exe" pr create`
        fed as a single token must block.

        The JSON command string is:
            "C:\\Program Files\\GitHub CLI\\gh.exe" pr create
        shlex (posix=True) strips the outer quotes; the resulting token is
        `C:\\Program Files\\GitHub CLI\\gh.exe` (with backslashes). The
        basename extractor splits on `\\` and returns `gh.exe`.
        """
        rc, stderr = _run_hook(
            '"C:\\\\Program Files\\\\GitHub CLI\\\\gh.exe" pr create',
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "Windows full-path gh.exe must be blocked"
        assert "BLOCK" in stderr

    # --- BLOCK: composition cases (env prefix + path) ------------------------

    def test_env_prefix_with_absolute_path_blocks(self):
        """`GH_TOKEN=x /usr/bin/gh pr create` — env prefix + absolute path."""
        rc, stderr = _run_hook(
            "GH_TOKEN=x /usr/bin/gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "env-prefix + /usr/bin/gh must be blocked"
        assert "BLOCK" in stderr

    def test_env_wrapper_with_absolute_path_blocks(self):
        """`env GH_HOST=h /usr/bin/gh pr create` — env wrapper + absolute path."""
        rc, stderr = _run_hook(
            "env GH_HOST=h /usr/bin/gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "env wrapper + /usr/bin/gh must be blocked"
        assert "BLOCK" in stderr

    def test_absolute_path_with_dry_run_false_blocks(self):
        """`/usr/bin/gh pr --dry-run=false create` — path + still creates."""
        rc, stderr = _run_hook(
            "/usr/bin/gh pr --dry-run=false create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "/usr/bin/gh pr --dry-run=false create must be blocked"
        assert "BLOCK" in stderr

    # --- ALLOW: real dry-run via absolute path is still exempt ---------------

    def test_absolute_path_with_dry_run_allows(self):
        """`/usr/bin/gh pr create --dry-run` — real dry-run via absolute path
        must still be allowed (dry-run exemption applies regardless of path
        form used to invoke gh)."""
        rc, _ = _run_hook(
            "/usr/bin/gh pr create --dry-run",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "/usr/bin/gh pr create --dry-run must be allowed"

    # --- NEGATIVE: must NOT match similar-but-different basenames ------------

    def test_mygh_does_not_match(self):
        """`mygh pr create` — basename is `mygh`, not `gh`. Gate must no-op."""
        rc, _ = _run_hook(
            "mygh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "mygh pr create must not trigger (different binary)"

    def test_gh_wrapper_does_not_match(self):
        """`gh-wrapper pr create` — basename is `gh-wrapper`, not `gh`."""
        rc, _ = _run_hook(
            "gh-wrapper pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "gh-wrapper pr create must not trigger"

    def test_ghx_does_not_match(self):
        """`/usr/bin/ghx pr create` — basename is `ghx`, not `gh`."""
        rc, _ = _run_hook(
            "/usr/bin/ghx pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "/usr/bin/ghx pr create must not trigger"

    # --- Regression: bare `gh pr create` still blocks ------------------------

    def test_bare_gh_still_blocks(self):
        """Regression guard: bare `gh pr create` (no path prefix) must still
        block under enforce+trigger (basename of `gh` is `gh`)."""
        rc, stderr = _run_hook(
            "gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "bare gh pr create must still be blocked"
        assert "BLOCK" in stderr


# ===========================================================================
# TestCodexP1CwdIndependentRepoRoot (codex P1 enforcement-bypass fix)
# ===========================================================================

def _setup_tmp_armature_repo(tmp_path: Path) -> Path:
    """Create a minimal tmp git repo with .armature/hooks/ (hook + lib) installed.

    Returns the repo root path. The hook and lib are copied from the real
    repo so they represent the current implementation under test. The repo
    is committed so red_team_check evaluate_red_team sees no untracked LOC.
    """
    repo = tmp_path / "tmp_repo"
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
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        check=True, capture_output=True, cwd=str(repo),
    )

    armature_dir = repo / ".armature"
    hooks_dir = armature_dir / "hooks"
    hooks_dir.mkdir(parents=True)
    (armature_dir / "session").mkdir(parents=True)

    # Copy hook script and lib from the real repo
    real_hooks_dir = _REPO_ROOT / ".armature" / "hooks"
    shutil.copy(
        str(real_hooks_dir / "pre-pr-create.sh"),
        str(hooks_dir / "pre-pr-create.sh"),
    )
    real_lib_dir = real_hooks_dir / "lib"
    if real_lib_dir.is_dir():
        shutil.copytree(str(real_lib_dir), str(hooks_dir / "lib"))

    # Commit all so evaluate_red_team doesn't count them as untracked LOC.
    subprocess.run(
        ["git", "add", "."], check=True, capture_output=True, cwd=str(repo),
    )
    subprocess.run(
        ["git", "commit", "-m", "add hooks"],
        check=True, capture_output=True, cwd=str(repo),
    )
    return repo


def _to_bash_path(p: Path) -> str:
    """Convert a Path to a bash-compatible path string.

    On Windows, Git Bash requires paths in POSIX form (forward slashes;
    drive letter as /c/... not C:/...). subprocess.run cwd= accepts Windows
    paths, but paths embedded inside a bash -c "..." command string must be
    POSIX-form for Git Bash to resolve them.

    Converts `C:\\Users\\...` -> `/c/Users/...`.
    On non-Windows systems, returns str(p) unchanged.
    """
    s = str(p).replace("\\", "/")
    # Windows drive letter: `C:/path` -> `/c/path`
    if len(s) >= 2 and s[1] == ":":
        s = "/" + s[0].lower() + s[2:]
    return s


def _run_hook_outside_cwd(
    command: str,
    hook_path: Path,
    outside_cwd: Path,
    *,
    enforce: bool = False,
    force_red_team: bool = False,
    claude_project_dir: str | None = None,
) -> tuple[int, str]:
    """Run the hook from an OUTSIDE cwd (not the repo) with controlled env.

    The hook is specified by its absolute path (converted to POSIX form for
    Git Bash) so bash can find it regardless of cwd. Environment variables
    are passed via subprocess env= so they survive cross-platform spawning
    without embedded-quoting issues.

    Returns (returncode, stderr_text).
    """
    payload = {"tool_input": {"command": command}}
    stdin_bytes = json.dumps(payload).encode("utf-8")

    # Build env for the subprocess: inherit the current environment and
    # overlay our test variables. Using env= avoids shell-quoting problems
    # with special characters in paths (spaces, backslashes on Windows).
    env = os.environ.copy()
    if enforce:
        env["ARMATURE_RED_TEAM_ENFORCE"] = "1"
    else:
        env.pop("ARMATURE_RED_TEAM_ENFORCE", None)
    if force_red_team:
        env["FORCE_RED_TEAM"] = "1"
    else:
        env.pop("FORCE_RED_TEAM", None)
    if claude_project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = claude_project_dir
    else:
        env.pop("CLAUDE_PROJECT_DIR", None)

    # Convert hook path to POSIX form for Git Bash on Windows.
    hook_bash_path = _to_bash_path(hook_path)

    proc = subprocess.run(
        [BASH_BIN, hook_bash_path],
        input=stdin_bytes,
        capture_output=True,
        env=env,
        cwd=str(outside_cwd),
        timeout=15,
    )
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


class TestCodexP1CwdIndependentRepoRoot:
    """Codex P1 fix: REPO_ROOT must resolve cwd-INDEPENDENTLY.

    Before the fix, `git rev-parse --show-toplevel` ran in the hook's cwd.
    When the hook was invoked from a directory that is NOT the project root
    (e.g. /tmp, or a different repo), it returned an unrelated path or fell
    back to pwd. The Python core then failed to import red_team_check.py
    (module-unavailable), and the hook exited 0 even under
    ARMATURE_RED_TEAM_ENFORCE=1 / FORCE_RED_TEAM=1 — enforcement bypassed.

    After the fix the hook resolves REPO_ROOT via:
      1. CLAUDE_PROJECT_DIR (authoritative, set by Claude Code harness)
      2. Hook's own install location via BASH_SOURCE two levels up
      3. Last-resort: git rev-parse (original cwd-dependent fallback)

    All three tests here use an outside-cwd invocation to prove the gate
    evaluates against the correct project root instead of failing open.
    """

    def test_claude_project_dir_resolves_outside_cwd(self, tmp_path):
        """Variant 1: CLAUDE_PROJECT_DIR set — must resolve REPO_ROOT correctly.

        Invoke the hook with cwd=outside_dir (a plain temp directory that is
        NOT a git repo) and CLAUDE_PROJECT_DIR=tmp_repo. With enforce=True and
        force_red_team=True the gate must exit 2 (BLOCK), proving the lib was
        found and evaluated. Before the fix this would exit 0 (fail-open via
        module-unavailable).
        """
        tmp_repo = _setup_tmp_armature_repo(tmp_path)
        hook_path = tmp_repo / ".armature" / "hooks" / "pre-pr-create.sh"

        # outside_cwd is a plain directory unrelated to the repo, not a git repo
        outside_cwd = tmp_path / "outside"
        outside_cwd.mkdir()

        rc, stderr = _run_hook_outside_cwd(
            "gh pr create",
            hook_path,
            outside_cwd,
            enforce=True,
            force_red_team=True,
            claude_project_dir=str(tmp_repo),
        )
        assert rc == 2, (
            "Gate must BLOCK (exit 2) when CLAUDE_PROJECT_DIR provides the "
            "correct root even when cwd is outside the repo. "
            f"Got exit {rc}. stderr: {stderr!r}"
        )
        assert "BLOCK" in stderr, f"Expected BLOCK in stderr; got: {stderr!r}"

    def test_bash_source_fallback_resolves_outside_cwd(self, tmp_path):
        """Variant 2: NO CLAUDE_PROJECT_DIR — hook-location (BASH_SOURCE) fallback.

        Invoke the hook from outside_cwd WITHOUT setting CLAUDE_PROJECT_DIR.
        The hook must derive REPO_ROOT from its own install path two levels up,
        find red_team_check.py, and BLOCK. Covers the Codex scenario where
        CLAUDE_PROJECT_DIR is absent.
        """
        tmp_repo = _setup_tmp_armature_repo(tmp_path)
        hook_path = tmp_repo / ".armature" / "hooks" / "pre-pr-create.sh"

        outside_cwd = tmp_path / "outside2"
        outside_cwd.mkdir()

        rc, stderr = _run_hook_outside_cwd(
            "gh pr create",
            hook_path,
            outside_cwd,
            enforce=True,
            force_red_team=True,
            claude_project_dir=None,  # explicitly absent
        )
        assert rc == 2, (
            "Gate must BLOCK (exit 2) when BASH_SOURCE two-levels-up fallback "
            "provides the correct root with cwd outside the repo. "
            f"Got exit {rc}. stderr: {stderr!r}"
        )
        assert "BLOCK" in stderr, f"Expected BLOCK in stderr; got: {stderr!r}"

    def test_normal_in_repo_invocation_still_blocks(self):
        """Regression guard: normal in-repo invocation (original cwd) still blocks.

        Ensures the three-candidate resolution does not regress the baseline
        case where cwd IS inside the project repo.
        """
        rc, stderr = _run_hook(
            "gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, (
            "Normal in-repo invocation must still BLOCK under enforce+trigger. "
            f"Got exit {rc}. stderr: {stderr!r}"
        )
        assert "BLOCK" in stderr, f"Expected BLOCK in stderr; got: {stderr!r}"


# ===========================================================================
# TestRedTeamFailClosedBypass (red-team: fail-closed + Fix 2 HIGH-1 regression)
# ===========================================================================

def _make_libless_dir(parent: Path, name: str = "libless") -> Path:
    """Create a real directory that does NOT contain the Armature lib.

    Used to simulate a wrong/stale CLAUDE_PROJECT_DIR or a root that was
    returned by Candidate 3 (git rev-parse) when the project has no lib.
    """
    d = parent / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _setup_tmp_armature_repo_with_hook_at(
    tmp_path: Path, repo_name: str = "tmp_repo2"
) -> Path:
    """Like _setup_tmp_armature_repo but returns the repo path.

    Separate helper to avoid reuse confusion with the original helper that
    already exists in this module (also used by other test classes).
    """
    return _setup_tmp_armature_repo(tmp_path)


class TestRedTeamFailClosed:
    """Red-team bypass fix: fail-closed when evaluation fails under enforce.

    Covers:
      - Fix 1 (core): detected gh pr create + enforce + lib unresolvable
        → exit 2 (BLOCK).
      - Fix 2 (HIGH-1): wrong CLAUDE_PROJECT_DIR falls through to BASH_SOURCE
        and the gate still evaluates (not just blocks due to fail-closed, but
        correctly resolves and evaluates).
      - Advisory mode stays fail-open when lib is unresolvable.
      - Non-gh commands are never blocked even when root is unresolvable.
      - Symlinked hook invocation (skipped if symlinks can't be created).
    """

    def test_wrong_claude_project_dir_falls_through_to_bash_source(self, tmp_path):
        """HIGH-1 regression: CLAUDE_PROJECT_DIR points at a real dir WITHOUT
        the lib. Fix 2 must make Candidate 1 fail its sanity check and fall
        through to Candidate 2 (BASH_SOURCE), which resolves the correct root.

        Expected behavior: gate evaluates correctly and exits 2 (BLOCK) under
        enforce + trigger. Before Fix 2, Candidate 1 accepted the lib-less
        CLAUDE_PROJECT_DIR as authoritative, the lib import failed, and the
        hook exited 0 even under ARMATURE_RED_TEAM_ENFORCE (fail-open bypass).
        After Fix 2, Candidate 1 is rejected (no lib), Candidate 2 resolves
        the real repo root via BASH_SOURCE, and the gate evaluates + blocks.
        """
        tmp_repo = _setup_tmp_armature_repo(tmp_path)
        hook_path = tmp_repo / ".armature" / "hooks" / "pre-pr-create.sh"

        # A real directory that EXISTS but does NOT have .armature/hooks/lib/
        # Simulates a stale or wrong CLAUDE_PROJECT_DIR (e.g. previous project).
        wrong_dir = _make_libless_dir(tmp_path, "wrong_project_dir")

        outside_cwd = tmp_path / "outside_fix2"
        outside_cwd.mkdir()

        rc, stderr = _run_hook_outside_cwd(
            "gh pr create",
            hook_path,
            outside_cwd,
            enforce=True,
            force_red_team=True,
            claude_project_dir=str(wrong_dir),
        )
        assert rc == 2, (
            "Gate must BLOCK (exit 2) even when CLAUDE_PROJECT_DIR is a "
            "lib-less dir — Candidate 2 (BASH_SOURCE) must resolve the "
            "correct root and evaluate the gate. "
            f"Got exit {rc}. stderr: {stderr!r}"
        )
        assert "BLOCK" in stderr, (
            f"Expected BLOCK in stderr; got: {stderr!r}"
        )

    def test_unresolvable_root_under_enforce_fails_closed(self, tmp_path):
        """Genuinely unresolvable root: all candidates point at lib-less dirs.

        Simulate a detected gh pr create where the lib is truly unfindable:
          - CLAUDE_PROJECT_DIR = a plain dir without the lib
          - hook runs from a dir without .armature (BASH_SOURCE two-up has no lib)
          - cwd is also outside any git repo so git rev-parse falls back to pwd

        Under ARMATURE_RED_TEAM_ENFORCE this must exit 2 (fail-closed).
        This is the core Fix 1 test.

        Implementation: copy just the hook script to a standalone location
        (no lib alongside it), set CLAUDE_PROJECT_DIR to another lib-less dir,
        and run from a non-repo cwd. All three candidates resolve to lib-less
        paths; the module import fails and the fail-closed branch fires.
        """
        # Create a standalone hook dir with ONLY the hook script (no lib).
        standalone_dir = tmp_path / "standalone_hooks"
        standalone_dir.mkdir()
        # We need .armature/hooks/ structure for the hook's BASH_SOURCE path
        # derivation, but without the lib so Candidate 2 sanity check fails.
        armature_hooks_dir = standalone_dir / ".armature" / "hooks"
        armature_hooks_dir.mkdir(parents=True)

        real_hook = _REPO_ROOT / ".armature" / "hooks" / "pre-pr-create.sh"
        standalone_hook = armature_hooks_dir / "pre-pr-create.sh"
        shutil.copy(str(real_hook), str(standalone_hook))

        # Wrong CLAUDE_PROJECT_DIR — real dir but no lib.
        wrong_cpd = _make_libless_dir(tmp_path, "wrong_cpd")
        # cwd — also not a git repo root.
        outside_cwd = tmp_path / "non_repo_cwd"
        outside_cwd.mkdir()

        rc, stderr = _run_hook_outside_cwd(
            "gh pr create",
            standalone_hook,
            outside_cwd,
            enforce=True,
            force_red_team=True,
            claude_project_dir=str(wrong_cpd),
        )
        assert rc == 2, (
            "Gate must BLOCK (exit 2) when the lib is truly unresolvable "
            "for a detected gh pr create under ARMATURE_RED_TEAM_ENFORCE. "
            f"Got exit {rc}. stderr: {stderr!r}"
        )
        assert "BLOCK" in stderr, (
            f"Expected BLOCK in stderr; got: {stderr!r}"
        )

    def test_unresolvable_root_advisory_mode_fails_open(self, tmp_path):
        """Same unresolvable-root condition in ADVISORY mode (enforce unset).

        The fail-open behavior for advisory mode must be preserved: when the
        lib is genuinely unresolvable but ARMATURE_RED_TEAM_ENFORCE is not
        set, the hook must exit 0 (allow).
        """
        standalone_dir = tmp_path / "standalone_hooks_adv"
        standalone_dir.mkdir()
        armature_hooks_dir = standalone_dir / ".armature" / "hooks"
        armature_hooks_dir.mkdir(parents=True)

        real_hook = _REPO_ROOT / ".armature" / "hooks" / "pre-pr-create.sh"
        standalone_hook = armature_hooks_dir / "pre-pr-create.sh"
        shutil.copy(str(real_hook), str(standalone_hook))

        wrong_cpd = _make_libless_dir(tmp_path, "wrong_cpd_adv")
        outside_cwd = tmp_path / "non_repo_cwd_adv"
        outside_cwd.mkdir()

        rc, stderr = _run_hook_outside_cwd(
            "gh pr create",
            standalone_hook,
            outside_cwd,
            enforce=False,   # ADVISORY mode — enforce NOT set
            force_red_team=True,
            claude_project_dir=str(wrong_cpd),
        )
        assert rc == 0, (
            "Gate must stay fail-open (exit 0) in advisory mode when lib "
            "is unresolvable. "
            f"Got exit {rc}. stderr: {stderr!r}"
        )

    def test_non_gh_command_unresolvable_root_under_enforce_exits_zero(
        self, tmp_path
    ):
        """Non-gh commands must never be blocked, even with unresolvable root
        under ARMATURE_RED_TEAM_ENFORCE.

        The fail-closed path is guarded by post-detection logic: the hook
        only fails closed when _is_gh_pr_create(...).detected is True. For
        any other command the hook exits 0 regardless of root resolution.
        """
        standalone_dir = tmp_path / "standalone_hooks_ngh"
        standalone_dir.mkdir()
        armature_hooks_dir = standalone_dir / ".armature" / "hooks"
        armature_hooks_dir.mkdir(parents=True)

        real_hook = _REPO_ROOT / ".armature" / "hooks" / "pre-pr-create.sh"
        standalone_hook = armature_hooks_dir / "pre-pr-create.sh"
        shutil.copy(str(real_hook), str(standalone_hook))

        wrong_cpd = _make_libless_dir(tmp_path, "wrong_cpd_ngh")
        outside_cwd = tmp_path / "non_repo_cwd_ngh"
        outside_cwd.mkdir()

        rc, stderr = _run_hook_outside_cwd(
            "git push origin main",   # NOT a gh pr create
            standalone_hook,
            outside_cwd,
            enforce=True,
            force_red_team=True,
            claude_project_dir=str(wrong_cpd),
        )
        assert rc == 0, (
            "Non-gh commands must never be blocked even when the root is "
            "unresolvable under enforce. "
            f"Got exit {rc}. stderr: {stderr!r}"
        )

    def test_symlinked_hook_resolves_and_blocks(self, tmp_path):
        """Symlinked hook invocation: Fix 3 (readlink -f canonicalization).

        When the hook is invoked through a symlink, BASH_SOURCE[0] is the
        symlink path. The hook must canonicalize it via readlink -f before
        deriving dirname(dirname) so it finds the real lib location.

        Skipped with a clear reason if symlink creation is not supported on
        the test platform (Windows without developer mode / admin rights).
        """
        import platform

        # Attempt to create a symlink; skip if not possible.
        tmp_repo = _setup_tmp_armature_repo(tmp_path)
        real_hook = tmp_repo / ".armature" / "hooks" / "pre-pr-create.sh"

        symlink_dir = tmp_path / "symlink_dir"
        symlink_dir.mkdir()
        symlink_hook = symlink_dir / "pre-pr-create.sh"

        try:
            symlink_hook.symlink_to(real_hook)
        except (OSError, NotImplementedError):
            pytest.skip(
                "Symlink creation not supported on this platform "
                "(Windows without developer mode or insufficient privileges). "
                "Fix 3 (readlink -f canonicalization) cannot be exercised."
            )

        outside_cwd = tmp_path / "outside_symlink"
        outside_cwd.mkdir()

        rc, stderr = _run_hook_outside_cwd(
            "gh pr create",
            symlink_hook,
            outside_cwd,
            enforce=True,
            force_red_team=True,
            claude_project_dir=None,  # force BASH_SOURCE path derivation
        )
        assert rc == 2, (
            "Symlinked hook invocation must resolve the correct root via "
            "readlink -f canonicalization and BLOCK under enforce+trigger. "
            f"Got exit {rc}. stderr: {stderr!r}"
        )
        assert "BLOCK" in stderr, f"Expected BLOCK in stderr; got: {stderr!r}"


# ===========================================================================
# EnforceTruthinessTests
# ===========================================================================

class TestEnforceTruthiness:
    """Red-team advisory: ARMATURE_RED_TEAM_ENFORCE truthy-value normalization.

    Prior to this fix, only exact {"1","true"} values enabled enforcement.
    Mixed-case values (TRUE, True), alias forms (yes, on), and
    whitespace-padded values silently failed OPEN (advisory mode) even though
    the operator believed they had enabled enforcement.

    All tests use FORCE_RED_TEAM to guarantee a trigger fires so the
    enforcing/advisory branch is always exercised.

    Baseline command for all cases: a plain `gh pr create` invocation.
    """

    _CMD = "gh pr create"

    # --- env-var truthy values: must block (exit 2) ---

    def test_env_TRUE_uppercase_blocks(self):
        """ARMATURE_RED_TEAM_ENFORCE=TRUE must block (exit 2)."""
        rc, stderr = _run_hook_enforce_value(self._CMD, "TRUE")
        assert rc == 2, f"Expected block for =TRUE; got {rc}. stderr: {stderr!r}"
        assert "BLOCK" in stderr

    def test_env_True_mixedcase_blocks(self):
        """ARMATURE_RED_TEAM_ENFORCE=True must block (exit 2)."""
        rc, stderr = _run_hook_enforce_value(self._CMD, "True")
        assert rc == 2, f"Expected block for =True; got {rc}. stderr: {stderr!r}"
        assert "BLOCK" in stderr

    def test_env_yes_blocks(self):
        """ARMATURE_RED_TEAM_ENFORCE=yes must block (exit 2)."""
        rc, stderr = _run_hook_enforce_value(self._CMD, "yes")
        assert rc == 2, f"Expected block for =yes; got {rc}. stderr: {stderr!r}"
        assert "BLOCK" in stderr

    def test_env_YES_blocks(self):
        """ARMATURE_RED_TEAM_ENFORCE=YES must block (exit 2)."""
        rc, stderr = _run_hook_enforce_value(self._CMD, "YES")
        assert rc == 2, f"Expected block for =YES; got {rc}. stderr: {stderr!r}"
        assert "BLOCK" in stderr

    def test_env_on_blocks(self):
        """ARMATURE_RED_TEAM_ENFORCE=on must block (exit 2)."""
        rc, stderr = _run_hook_enforce_value(self._CMD, "on")
        assert rc == 2, f"Expected block for =on; got {rc}. stderr: {stderr!r}"
        assert "BLOCK" in stderr

    def test_env_whitespace_padded_true_blocks(self):
        """ARMATURE_RED_TEAM_ENFORCE=' true ' (whitespace-padded) must block."""
        rc, stderr = _run_hook_enforce_value(self._CMD, " true ")
        assert rc == 2, f"Expected block for =' true '; got {rc}. stderr: {stderr!r}"
        assert "BLOCK" in stderr

    # --- regression: original accepted values must still block ---

    def test_env_1_still_blocks(self):
        """Regression: ARMATURE_RED_TEAM_ENFORCE=1 must still block."""
        rc, stderr = _run_hook_enforce_value(self._CMD, "1")
        assert rc == 2, f"Regression: =1 must still block; got {rc}. stderr: {stderr!r}"
        assert "BLOCK" in stderr

    def test_env_true_lowercase_still_blocks(self):
        """Regression: ARMATURE_RED_TEAM_ENFORCE=true must still block."""
        rc, stderr = _run_hook_enforce_value(self._CMD, "true")
        assert rc == 2, f"Regression: =true must still block; got {rc}. stderr: {stderr!r}"
        assert "BLOCK" in stderr

    # --- falsy values: must NOT block (advisory, exit 0) ---

    def test_env_0_advisory(self):
        """ARMATURE_RED_TEAM_ENFORCE=0 must NOT block (advisory, exit 0)."""
        rc, _ = _run_hook_enforce_value(self._CMD, "0")
        assert rc == 0, f"Expected advisory for =0; got {rc}"

    def test_env_false_advisory(self):
        """ARMATURE_RED_TEAM_ENFORCE=false must NOT block (advisory, exit 0)."""
        rc, _ = _run_hook_enforce_value(self._CMD, "false")
        assert rc == 0, f"Expected advisory for =false; got {rc}"

    def test_env_no_advisory(self):
        """ARMATURE_RED_TEAM_ENFORCE=no must NOT block (advisory, exit 0)."""
        rc, _ = _run_hook_enforce_value(self._CMD, "no")
        assert rc == 0, f"Expected advisory for =no; got {rc}"

    def test_env_off_advisory(self):
        """ARMATURE_RED_TEAM_ENFORCE=off must NOT block (advisory, exit 0)."""
        rc, _ = _run_hook_enforce_value(self._CMD, "off")
        assert rc == 0, f"Expected advisory for =off; got {rc}"

    def test_env_empty_advisory(self):
        """ARMATURE_RED_TEAM_ENFORCE= (empty string) must NOT block."""
        rc, _ = _run_hook_enforce_value(self._CMD, "")
        assert rc == 0, f"Expected advisory for empty string; got {rc}"

    def test_env_unset_advisory(self):
        """Unset ARMATURE_RED_TEAM_ENFORCE must NOT block (advisory)."""
        rc, _ = _run_hook_enforce_value(self._CMD, None)
        assert rc == 0, f"Expected advisory when unset; got {rc}"

    # --- inline-override parity: command-string prefix ---

    def test_inline_TRUE_blocks(self):
        """Inline ARMATURE_RED_TEAM_ENFORCE=TRUE in command prefix must block."""
        rc, stderr = _run_hook_enforce_value(
            self._CMD,
            None,  # env unset
            inline_command="ARMATURE_RED_TEAM_ENFORCE=TRUE FORCE_RED_TEAM=1 gh pr create",
            force_red_team=False,
        )
        assert rc == 2, f"Inline =TRUE must block; got {rc}. stderr: {stderr!r}"
        assert "BLOCK" in stderr

    def test_inline_yes_blocks(self):
        """Inline ARMATURE_RED_TEAM_ENFORCE=yes in command prefix must block."""
        rc, stderr = _run_hook_enforce_value(
            self._CMD,
            None,  # env unset
            inline_command="ARMATURE_RED_TEAM_ENFORCE=yes FORCE_RED_TEAM=1 gh pr create",
            force_red_team=False,
        )
        assert rc == 2, f"Inline =yes must block; got {rc}. stderr: {stderr!r}"
        assert "BLOCK" in stderr

    def test_inline_0_with_env_true_still_blocks(self):
        """Inline =0 cannot weaken an ambient env-level =true.

        The hook uses OR semantics: if env is truthy the result is ENFORCING
        regardless of inline value.  Inline cannot downgrade enforcement.
        """
        rc, stderr = _run_hook_enforce_value(
            self._CMD,
            "true",  # env-level enforce is truthy
            inline_command="ARMATURE_RED_TEAM_ENFORCE=0 FORCE_RED_TEAM=1 gh pr create",
            force_red_team=False,
        )
        # env says enforce=true; inline =0 must NOT weaken it.
        assert rc == 2, (
            f"Inline =0 must not weaken env-level enforce=true; got {rc}. "
            f"stderr: {stderr!r}"
        )


# ===========================================================================
# TestGhPrNewAlias (codex P1 — gh pr new is the documented alias for create)
# ===========================================================================

class TestGhPrNewAlias:
    """Codex P1 fix (pre-pr-create.sh:607): `gh pr new` is the official
    gh-documented alias for `gh pr create` (listed under ALIASES in
    `gh pr create --help`). The prior implementation matched only the literal
    `create` subcommand, so `gh pr new ...` evaded the gate entirely.

    Fix: match both `create` and `new` via the _GH_PR_CREATE_SUBCMDS tuple.
    All dry-run, composition, and negative cases that apply to `create` apply
    identically to `new`.
    """

    # --- BLOCK: bare and flag forms under enforce + trigger ------------------

    def test_gh_pr_new_bare_blocks(self):
        """`gh pr new` — the alias form with no flags must block."""
        rc, stderr = _run_hook(
            "gh pr new",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "gh pr new must be blocked under enforce+trigger"
        assert "BLOCK" in stderr

    def test_gh_pr_new_with_title_and_body_blocks(self):
        """`gh pr new --title X --body Y` — flags do not prevent detection."""
        rc, stderr = _run_hook(
            "gh pr new --title X --body Y",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "gh pr new --title X --body Y must be blocked"
        assert "BLOCK" in stderr

    def test_gh_pr_level_repo_new_blocks(self):
        """`gh pr -R o/r new` — pr-level -R flag then `new` subcommand."""
        rc, stderr = _run_hook(
            "gh pr -R o/r new",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "gh pr -R o/r new must be blocked"
        assert "BLOCK" in stderr

    def test_gh_parent_level_repo_pr_new_blocks(self):
        """`gh -R o/r pr new` — parent-level -R flag then `pr new`."""
        rc, stderr = _run_hook(
            "gh -R o/r pr new",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "gh -R o/r pr new must be blocked"
        assert "BLOCK" in stderr

    # --- BLOCK: composition cases (env prefix, env wrapper, path forms) ------

    def test_env_prefix_gh_pr_new_blocks(self):
        """`GH_TOKEN=x gh pr new` — bash inline env-prefix with alias."""
        rc, stderr = _run_hook(
            "GH_TOKEN=x gh pr new",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "GH_TOKEN=x gh pr new must be blocked"
        assert "BLOCK" in stderr

    def test_env_wrapper_chdir_gh_pr_new_blocks(self):
        """`env -C /x gh pr new` — env wrapper with chdir operand + alias."""
        rc, stderr = _run_hook(
            "env -C /tmp gh pr new",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "env -C /tmp gh pr new must be blocked"
        assert "BLOCK" in stderr

    def test_absolute_path_gh_pr_new_blocks(self):
        """`/usr/bin/gh pr new` — absolute path invocation with alias."""
        rc, stderr = _run_hook(
            "/usr/bin/gh pr new",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "/usr/bin/gh pr new must be blocked"
        assert "BLOCK" in stderr

    def test_gh_exe_pr_new_blocks(self):
        """`gh.exe pr new` — Windows executable form with alias."""
        rc, stderr = _run_hook(
            "gh.exe pr new",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "gh.exe pr new must be blocked"
        assert "BLOCK" in stderr

    # --- Dry-run exemption parity: `new` mirrors `create` behavior -----------

    def test_gh_pr_new_dry_run_allows(self):
        """`gh pr new --dry-run` — real dry-run via alias must be allowed.

        `gh pr new --dry-run` prints PR details without creating, same as
        `gh pr create --dry-run`. The dry-run exemption applies equally to
        the `new` alias."""
        rc, stderr = _run_hook(
            "gh pr new --dry-run",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "gh pr new --dry-run must be allowed (dry-run exemption)"
        assert "BLOCK" not in stderr

    def test_gh_pr_new_dry_run_false_blocks(self):
        """`gh pr new --dry-run --dry-run=false` — final dry-run value is false;
        gh CREATES the PR. Gate must BLOCK."""
        rc, stderr = _run_hook(
            "gh pr new --dry-run --dry-run=false",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "gh pr new --dry-run --dry-run=false (final false) must block"
        assert "BLOCK" in stderr

    def test_gh_pr_new_dry_run_as_title_value_blocks(self):
        """`gh pr new --title "--dry-run"` — `--dry-run` is the value of
        `--title` (shlex strips quotes). gh creates the PR; gate must BLOCK."""
        rc, stderr = _run_hook(
            'gh pr new --title "--dry-run"',
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "--dry-run as --title value for `gh pr new` must block"
        assert "BLOCK" in stderr

    # --- NEGATIVE: non-create `gh pr` verbs must NOT match -------------------

    def test_gh_pr_view_does_not_match(self):
        """`gh pr view 123` — `view` is not a PR-creation subcommand."""
        rc, _ = _run_hook(
            "gh pr view 123",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "gh pr view must not trigger the gate"

    def test_gh_pr_edit_does_not_match(self):
        """`gh pr edit 1 --title x` — `edit` is not a PR-creation subcommand."""
        rc, _ = _run_hook(
            "gh pr edit 1 --title x",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "gh pr edit must not trigger the gate"

    def test_gh_pr_list_does_not_match(self):
        """`gh pr list` — `list` is not a PR-creation subcommand."""
        rc, _ = _run_hook(
            "gh pr list",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "gh pr list must not trigger the gate"

    def test_gh_issue_new_does_not_match(self):
        """`gh issue new` — a different gh resource type; must not trigger.

        The `new` subcommand is only matched under `gh pr`, not under other
        gh resource groups."""
        rc, _ = _run_hook(
            "gh issue new",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "gh issue new must not trigger the gate (wrong resource)"

    def test_gh_pr_bare_no_subcommand_does_not_match(self):
        """`gh pr` with no subcommand — no PR-creation verb present."""
        rc, _ = _run_hook(
            "gh pr",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 0, "bare `gh pr` with no subcommand must not trigger"

    # --- Regression: `gh pr create` existing forms still block ---------------

    def test_gh_pr_create_regression_bare_blocks(self):
        """Regression: bare `gh pr create` still blocks under enforce+trigger."""
        rc, stderr = _run_hook(
            "gh pr create",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "gh pr create regression: bare form must still block"
        assert "BLOCK" in stderr

    def test_gh_pr_create_regression_with_flags_blocks(self):
        """Regression: `gh pr create --title X` still blocks."""
        rc, stderr = _run_hook(
            "gh pr create --title X",
            enforce=True,
            force_red_team=True,
        )
        assert rc == 2, "gh pr create --title X regression: must still block"
        assert "BLOCK" in stderr

    # --- Advisory (soft-deploy) mode for `new` alias -------------------------

    def test_gh_pr_new_advisory_mode(self):
        """`gh pr new` in advisory (non-enforce) mode exits 0 with ADVISORY."""
        rc, stderr = _run_hook(
            "gh pr new",
            enforce=False,
            force_red_team=True,
        )
        assert rc == 0, "gh pr new in advisory mode must exit 0"
        assert "ADVISORY" in stderr
