#!/usr/bin/env bash
# Armature PreToolUse(Bash) gate for cascade-rule enforcement (DRIFT-002).
#
# Claude Code invokes this hook with the tool input JSON on stdin. We extract
# the Bash command being run; if it is a commit-producing git subcommand we
# delegate to check-cascade.sh and propagate its exit code (blocking on
# cascade violations).
#
# ── SCOPE: best-effort PreToolUse first line of defense ──
# This gate runs BEFORE the Bash command executes, so it can only preflight the
# repository state that exists at hook time. It cannot observe state changes the
# command itself will make. The one structural consequence worth calling out:
#
#   Edit-before-stage in a single compound command is undetectable here, e.g.
#       printf '...' > .armature/invariants/registry.yaml \
#         && git add .armature/invariants/registry.yaml && git commit -m x
#   At hook time the `printf` has not run, so the `git add --dry-run` preflight
#   sees no change and the commit passes the gate; the real shell then writes,
#   stages, and commits the violation. There is no reliable fix at PreToolUse:
#   almost any earlier command (printf/sed/tee/make/build steps) can mutate the
#   worktree, so "fail closed when an earlier segment might edit" would block
#   the extremely common `make && git add . && git commit` and similar.
#
# Defense in depth: this gate is the fast first line of defense; the
# AUTHORITATIVE DRIFT-002 layer is cascade-ci.sh, which runs in CI
# (.github/workflows/governance.yml, job `cascade-backstop`) and evaluates
# check-cascade.sh per-commit against the actual committed changeset with NO
# command-string parsing. Anything this PreToolUse gate cannot model —
# edit-before-stage, exotic shell forms — is caught there. A violation that
# slips past this gate is therefore not a silent bypass: it fails CI on the PR.
#
# Gated commit-producing subcommands and the check mode used:
#
#   git commit           → files mode (accounts for -a/--all and pathspecs;
#                          falls back to --staged-only when none are present)
#   git cherry-pick <ref> --continue  → --staged-only (resolved from staging area)
#   git merge --continue              → --staged-only
#   git rebase --continue             → --staged-only
#   git am <patch>                    → --staged-only fallback (patch-preview not
#                                       implemented; documented limitation)
#
#   git cherry-pick <ref>   (initial) → --files <list from git show --name-only>
#   git revert <ref>        (initial) → --files <list from git show --name-only>
#   git merge <branch>      (initial) → --files <list from git diff --name-only HEAD...branch>
#   git rebase <upstream>   (initial, simple) → --files <list from git log --name-only upstream..HEAD>
#   git rebase --onto ...             → --staged-only fallback (complex form)
#   git rebase -i / --interactive     → --staged-only fallback (complex form)
#
# For initial-form cherry-pick/revert/merge/rebase, the gate pre-flights the
# file list the operation WILL touch (via git show/diff/log introspection) and
# checks THAT list against cascade rules — before the operation runs and creates
# any staging-area state.
#
# Fail-open semantics: if git introspection fails (ref not found, subprocess
# error, etc.) the gate falls back to --staged-only. This is conservative:
# it may miss a cascade violation on a bad ref, but it never deadlocks the
# developer's workflow.
#
# Subcommands that accept --no-commit or -n as an explicit opt-out are allowed
# through when those flags are present.
#
# For all other Bash commands — including recovery commands like `git add`,
# `git reset`, `git restore`, `git stash` — we exit 0 without running the
# check, so developers can recover from a partial cascade.
#
# Git invocation forms recognized:
#   - Literal:          git commit
#   - Absolute path:    /usr/bin/git commit
#   - Relative path:    ./bin/git commit
#   - Wrapping prefix:  command git commit, exec git commit, builtin git commit
#   - Combined wrapping: command command git commit
#
# Known limitation: command-substitution-prefixed invocations such as
#   $(which git) commit  or  `which git` commit
# are handled via a fail-closed early-exit: if the command string contains
# a substitution pattern ($( or `) AND a commit-producing verb keyword, the
# gate blocks with exit 2. The gate cannot safely tokenize or evaluate shell
# substitutions, so it cannot determine what command will actually run.
# Use a literal `git` invocation instead of $(which git) or backtick forms.
#
# Exit codes:
#   0   allow (not a commit, or commit passes cascade)
#   2   block (commit fails cascade — Claude Code PreToolUse blocking exit)

set -euo pipefail

ARMATURE_DIR="${ARMATURE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
export ARMATURE_DIR
# Export the full path to check-cascade.sh resolved in this (MSYS) bash context
# so the Python heredoc can invoke it portably without path-style conversion.
_CHECK_CASCADE_SCRIPT="${ARMATURE_DIR}/hooks/check-cascade.sh"
export _CHECK_CASCADE_SCRIPT
# Export the path to this bash interpreter so Python can spawn the same one.
_GATE_BASH="$(command -v bash)"
export _GATE_BASH

# Find Python (mirror check-cascade.sh / post-stop.sh)
if command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
else
    # Fail-open if no Python — better to allow than to break all Bash
    exit 0
fi

# Read stdin (Claude Code's tool input JSON). If empty (e.g., direct invocation
# for testing), exit 0 — there is nothing to gate on.
STDIN_DATA="$(cat || true)"
if [ -z "$STDIN_DATA" ]; then
    exit 0
fi

# Extract the command from tool_input.command
CMD="$( printf '%s' "$STDIN_DATA" | "$PYTHON" -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('tool_input', {}).get('command', ''))
except Exception:
    pass
" 2>/dev/null || true)"

if [ -z "$CMD" ]; then
    # JSON parse failure or no command — fail open
    exit 0
fi

# The entire decision logic (subcommand detection, alias resolution, opt-out
# detection, pre-flight introspection for initial-form operations, and
# invocation of check-cascade.sh) lives in this Python heredoc. Python is the
# single invocation point — there is no bash `exec` fallback path.
export _GATE_CMD="$CMD"
"$PYTHON" <<'PYEOF'
import os, shlex, re, sys, subprocess

# Long global options that take a separate value token when used in the
# space-separated form (--opt value). When the same option is written as
# --opt=value it is a single token and the existing single-token path
# handles it correctly.  Per `man git`, the full set is:
VALUE_TAKING_LONG_OPTS = {
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--super-prefix",
    "--exec-path",
    "--attr-source",
    "--list-cmds",
    "--literal-pathspec-from-file",
    "--config-env",  # takes a separate <name>=<envvar> token in space-separated form
}

# Matches shell env-var assignment prefixes of the form VAR=value that may
# appear before the command (e.g. `FOO=1 git commit`).  A valid shell
# variable name starts with a letter or underscore, followed by letters,
# digits, or underscores, then an `=`.  This intentionally does NOT match
# `--foo=bar`, `-c key=val`, `/path=file`, or bare `=value`.
ENV_VAR_ASSIGN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')

# Subcommands that can write commits from staged content.
# These are blocked the same way `commit` is, unless an explicit
# no-commit opt-out flag is present.
COMMIT_PRODUCING_SUBCOMMANDS = {
    "commit",
    "merge",
    "cherry-pick",
    "rebase",
    "revert",
    "am",
}

# Subcommand-specific no-commit opt-out flags beyond the universal --no-commit.
#
# -n means --no-commit only for cherry-pick and revert; for `git merge` the -n
# short flag means --no-stat (suppresses the diffstat) — it does NOT prevent the
# merge commit.  For `git am`, -n is unrelated too.  Scope -n narrowly.
#
# NOTE: `merge` has been removed from this table.  Merge FF-semantics are complex
# enough to require a dedicated check (_merge_skips_history_change); see
# is_commit_producing() below.  The generic --no-commit / SUBCMD_SPECIFIC path
# is intentionally bypassed for merge.
SUBCMD_SPECIFIC_NO_COMMIT_FLAGS = {
    "cherry-pick": {"-n"},
    "revert": {"-n"},
    "commit": {"--dry-run"},
}

# Flags that indicate a continuation of an in-progress operation.
# For these, the staging area already holds the resolved content, so --staged-only
# is the correct check mode (same as git commit).
CONTINUATION_FLAGS = {"--continue"}

# Flags that signal recovery/control paths that do NOT produce a commit.
# (e.g. aborting or skipping a conflicted rebase/cherry-pick/merge/am/revert)
# These must bypass the gate entirely — they never write commits, and blocking
# them when a cascade-violating file is staged would deadlock the developer.
RECOVERY_FLAGS = {"--abort", "--quit", "--skip"}

# ---------------------------------------------------------------------------
# F1: wrapping prefix stripping, path-based git detection, substitution guard
# ---------------------------------------------------------------------------

# Shell builtins / exec that wrap a command without changing its semantics for
# our purposes.  `exec git commit` replaces the shell process with git — same
# observable outcome; gate it.  `builtin git commit` looks up the git builtin
# (effectively same as `git commit`).
# `env` is a common launcher wrapper used to set or clear environment variables
# before running a command: `env git commit`, `env VAR=val git commit`,
# `env -i git commit`, `env -u SHELL git commit`, etc.
WRAPPING_PREFIXES = {"command", "builtin", "exec", "env"}


def is_git_executable(token):
    """Return True if token names the git executable, whether by literal name,
    absolute path, or relative path.

    Examples that return True:
      git, /usr/bin/git, /usr/local/bin/git, ./bin/git, bin/git, git.exe
    """
    if token == "git":
        return True
    # Path-like token (contains a path separator): check the basename.
    if "/" in token or "\\" in token:
        name = os.path.basename(token)
        # Strip .exe suffix for Windows portability.
        if name.lower().endswith(".exe"):
            name = name[:-4]
        return name == "git"
    return False


# Bare commit-verb pattern — used for substitution-as-executable guard where
# there is no preceding "git" token to provide context.  `am` is intentionally
# EXCLUDED here: "am" is a common English word and would produce false positives
# in commands like `$(echo am)`.  The accepted trade-off: `$(which git) am patch`
# is a blind spot for this guard; users should invoke `git am` directly.
_COMMIT_VERB_RE = re.compile(r'\b(commit|merge|cherry-pick|rebase|revert)\b', re.IGNORECASE)
# Context-aware pattern — requires the literal word "git" followed by whitespace
# and then the verb.  Includes `am` because in this context `git am` is
# unambiguous and the false-positive risk from the bare English word is absent.
# Used for shell-wrapper guard, raw pre-scan, and shell-alias detection where
# the token stream or alias body contains a literal "git verb" phrase.
_GIT_COMMIT_VERB_RE = re.compile(
    r'\bgit\s+(commit|merge|cherry-pick|rebase|revert|am)\b',
    re.IGNORECASE,
)


# NOTE: The substitution-as-executable guard is performed per-segment inside
# the main loop (a substitution is only treated as fail-closed when it is the
# segment's executable — the first token after env-var and wrapping-prefix
# stripping — not when it appears as an argument to a non-git command). An
# earlier top-level has_substitution_with_commit_verb() helper was removed as
# dead code; the per-segment check supersedes it.


def load_aliases():
    """Return {alias_name: expansion_str} from `git config --get-regexp ^alias\\.`.
    Returns empty dict on any failure (fail-open)."""
    try:
        result = subprocess.run(
            ["git", "config", "--get-regexp", r"^alias\."],
            capture_output=True, text=True, timeout=2
        )
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return {}
    if result.returncode != 0:
        return {}
    aliases = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        key, _, value = line.partition(" ")
        if key.startswith("alias."):
            aliases[key[len("alias."):]] = value
    return aliases


ALIASES = load_aliases()


# Global git options that take a separate value token in the space-separated
# form (--opt value).  When written as --opt=value they are a single token and
# need no special handling in the walker below.
GLOBAL_VALUE_TAKING_LONG_OPTS = {
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--super-prefix",
    "--exec-path",
    "--attr-source",
    "--list-cmds",
    "--literal-pathspec-from-file",
    "--config-env",  # takes a separate <name>=<envvar> token in space-separated form
}


def _skip_global_git_opts(toks):
    """Walk past global git options and return the index of the first
    non-option token (the subcommand position), or len(toks) if none found.

    Handles:
      -C <path>   : short flag that takes a separate value token
      -c <key=v>  : short flag that takes a separate value token
      other -X    : single-token short flag (e.g. -p, -P)
      --opt=value : single-token long option
      --opt value : value-taking long option in space-separated form
                    (only for opts in GLOBAL_VALUE_TAKING_LONG_OPTS)
      --flag      : value-less long flag (e.g. --no-pager)

    This mirrors the logic in the main detection loop so that alias
    expansions containing global options (e.g. "-c core.editor=true commit")
    are resolved correctly.
    """
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in ("-C", "-c"):
            i += 2
            continue
        if t.startswith("-") and not t.startswith("--"):
            # Other single-char short flag (no separate value)
            i += 1
            continue
        if t.startswith("--"):
            if "=" in t:
                # --opt=value form — single token
                i += 1
                continue
            if t in GLOBAL_VALUE_TAKING_LONG_OPTS:
                # --opt value form — consume option + value
                i += 2
                continue
            # Value-less long flag (e.g. --no-pager)
            i += 1
            continue
        # Non-option token: this is the subcommand position
        return i
    return i


def _skip_global_git_opts_with_capture(toks):
    """Walk past global git options and return (verb_idx, cwd_override).

    verb_idx: index of the first non-option token (the subcommand position),
              or len(toks) if no subcommand is found.
    cwd_override: the last -C <path> value seen during the walk, or None.

    Mirrors _skip_global_git_opts() but additionally captures the -C argument
    so callers can resolve relative file paths against the git working directory
    specified by -C.  Used in the main detection loop; _skip_global_git_opts()
    is kept for alias resolution (where -C is rare and cwd is not needed).
    """
    i = 0
    cwd_override = None
    while i < len(toks):
        t = toks[i]
        if t == "-C" and i + 1 < len(toks):
            new_c = toks[i + 1]
            if os.path.isabs(new_c) or cwd_override is None:
                cwd_override = new_c
            else:
                cwd_override = os.path.join(cwd_override, new_c)
            i += 2
            continue
        if t == "-c":
            i += 2
            continue
        if t.startswith("-") and not t.startswith("--"):
            # Other single-char short flag (no separate value)
            i += 1
            continue
        if t.startswith("--"):
            if "=" in t:
                # --opt=value form — single token
                i += 1
                continue
            if t in GLOBAL_VALUE_TAKING_LONG_OPTS:
                # --opt value form — consume option + value
                i += 2
                continue
            # Value-less long flag (e.g. --no-pager)
            i += 1
            continue
        # Non-option token: this is the subcommand position
        return i, cwd_override
    return i, cwd_override


def _resolve_subcmd(token):
    """Return (canonical_subcmd, expansion_args) for commit-producing tokens, or None.

    canonical_subcmd: one of COMMIT_PRODUCING_SUBCOMMANDS
    expansion_args: additional tokens that the alias expansion injects before the
                    user-supplied remaining tokens.  These are the flags embedded
                    in the alias definition — e.g. alias.cia = "commit -a" yields
                    expansion_args=["-a"].  For direct hits and shell aliases the
                    list is always empty (shell aliases are opaque).

    Handles:
      - direct match (token in COMMIT_PRODUCING_SUBCOMMANDS)
        → (token, [])
      - plain alias whose expansion starts with a commit verb
        → (verb, expansion_toks[1:])
      - one level of alias-of-alias (plain only)
        → (verb, nested_toks[1:] + outer_toks[1:])
      - shell alias ('!...') containing a commit verb
        → (verb, [])  — shell semantics are opaque; flags cannot be extracted safely
      - alias-of-alias where intermediate is a shell alias
        → (verb, outer_toks[1:])  — conservative; shell layer flags lost

    Returns None when the token does not resolve to a commit-producing subcommand.

    NOTE: callers that previously unpacked (canonical, is_shell) must be updated.
    The is_shell signal has been replaced: a non-empty expansion_args signals that
    alias-injected flags are present; shell-alias hits always return expansion_args=[].
    The caller separately checks whether opt-out detection should be suppressed for
    shell aliases.  We retain a second return value for that: we return
    (canonical, expansion_args, is_shell) internally via a 3-tuple but expose it
    as a named tuple to keep the API clean.

    For backward compatibility the existing callers that check `is_shell` continue to
    work because we keep it as the third element.
    """
    if token in COMMIT_PRODUCING_SUBCOMMANDS:
        return (token, [], False)

    expansion = ALIASES.get(token)
    if expansion is None:
        return None

    if expansion.startswith("!"):
        # Shell alias — conservative: if a git commit-producing verb appears
        # in a "git verb" phrase, treat as commit-producing.  Shell aliases
        # typically contain literal `!git commit ...` forms so the contextual
        # _GIT_COMMIT_VERB_RE match is accurate and avoids bare-word false
        # positives (e.g. an alias body referencing "commit" as plain English).
        # Cannot extract embedded flags safely.
        m = _GIT_COMMIT_VERB_RE.search(expansion)
        if m:
            return (m.group(1), [], True)
        return None

    # Plain alias: tokenize so we can extract the trailing args.
    try:
        expansion_toks = shlex.split(expansion)
    except ValueError:
        return None
    if not expansion_toks:
        return None

    # Walk past any global git options that may precede the subcommand in the
    # alias expansion (e.g. alias.ci = "-c core.editor=true commit").
    verb_idx = _skip_global_git_opts(expansion_toks)
    if verb_idx >= len(expansion_toks):
        return None
    first_token = expansion_toks[verb_idx]
    # expansion_args = everything except the verb itself (global opts before
    # the verb + remaining args after the verb).  The main flow prepends these
    # to user-supplied args; the main parser's global-option walker then
    # processes any leading global opts in the combined arg list correctly.
    outer_args = expansion_toks[:verb_idx] + expansion_toks[verb_idx + 1:]

    if first_token in COMMIT_PRODUCING_SUBCOMMANDS:
        return (first_token, outer_args, False)

    # One level of alias-of-alias
    nested = ALIASES.get(first_token)
    if nested is None:
        return None
    if nested.startswith("!"):
        m = _GIT_COMMIT_VERB_RE.search(nested)
        if m:
            # Shell layer is opaque; outer alias args are preserved.
            return (m.group(1), outer_args, True)
        return None
    try:
        nested_toks = shlex.split(nested)
    except ValueError:
        return None
    if not nested_toks:
        return None
    # Walk past global opts in the nested expansion too.
    nested_verb_idx = _skip_global_git_opts(nested_toks)
    if nested_verb_idx >= len(nested_toks):
        return None
    nested_first = nested_toks[nested_verb_idx]
    if nested_first in COMMIT_PRODUCING_SUBCOMMANDS:
        # Combine: nested expansion provides earlier args (global opts + flags
        # from nested alias); outer alias provides later args; user provides
        # final args.  Order: nested_without_verb + outer_args
        nested_args = nested_toks[:nested_verb_idx] + nested_toks[nested_verb_idx + 1:]
        return (nested_first, nested_args + outer_args, False)
    return None


def _standalone_flags(tokens, value_takers):
    """Iterate `tokens` and yield only those that are STANDALONE option tokens
    (or positionals) — never the value of a preceding value-taking option.

    A naive `flag in tokens` check is wrong for flag-detection because a string
    like "--no-commit" can appear as the VALUE of a value-taking option (e.g.
    `git commit -m --no-commit` has message="--no-commit", not a no-commit
    flag). This walker consumes the value of each value-taking option so it is
    not yielded, restoring the invariant that yielded tokens are the ones git
    will interpret as options.

    value_takers: set of option strings whose next token is consumed as a value
        in the space-separated form `--opt value` / `-o value`. The attached
        `--opt=value` form is a single token and needs no special handling.

    Stops at the `--` end-of-options marker: every token after it is a
    pathspec and cannot be a flag, so it is irrelevant for flag detection.

    This helper backs both _merge_skips_history_change() and the opt-out
    detection inside is_commit_producing(); is_recovery() does an equivalent
    walk inline.
    """
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "--":
            return
        yield t
        # --opt=value: single token, no separate value to skip.
        if t.startswith("--") and "=" in t:
            i += 1
            continue
        # Value-taking option in space-separated form: skip its value.
        if t in value_takers and i + 1 < len(tokens):
            i += 2
            continue
        i += 1


def _merge_skips_history_change(remaining_toks):
    """True if the merge will NOT change HEAD or write a commit.

    Per `man git-merge`:
    - --squash: stages content, no commit, no FF -> HEAD unchanged
    - --no-ff --no-commit: forced non-FF + no commit -> stages but no HEAD move

    All other combinations (including bare --no-commit and --ff-only) MAY
    change HEAD via fast-forward, bringing in commits from the merged branch.
    Cascade enforcement is required for those forms because the branch's
    commits become part of HEAD's history.

    Specifically:
    - --no-commit alone: stages, but FF CAN still happen -> HEAD MAY move  (not a bypass)
    - --ff-only: only allows FF; if FF possible, HEAD moves to branch tip   (not a bypass)
    - --no-ff alone: forces merge commit -> clearly commit-producing         (not a bypass)
    - (default, no flags): may FF or merge-commit                            (not a bypass)

    Flag detection honours value-taking options: `git merge -m --squash topic`
    is a normal merge whose message is "--squash", NOT a squash merge. Without
    this distinction the gate would skip cascade enforcement on the bypass-
    label form, allowing a violation through.
    """
    merge_value_takers = SUBCMD_VALUE_TAKING_OPTS.get("merge", set())
    standalone = set(_standalone_flags(remaining_toks, merge_value_takers))
    has_squash = "--squash" in standalone
    has_no_commit = "--no-commit" in standalone
    has_no_ff = "--no-ff" in standalone
    return has_squash or (has_no_commit and has_no_ff)


def is_commit_producing(token, remaining_toks):
    """Return True if this subcommand token will write a commit with staged
    content, respecting --no-commit / -n opt-outs.

    remaining_toks: all tokens after the subcommand token in the same segment.
    Note: expansion_args from alias resolution are prepended to remaining_toks
    by the caller before this function is invoked, so opt-out flags embedded
    in an alias (e.g. alias.cnc = "commit --no-commit") are visible here.
    """
    result = _resolve_subcmd(token)
    if result is None:
        return False
    canonical, _expansion_args, is_shell = result
    if is_shell:
        # Shell alias — cannot inspect flags reliably; treat as commit
        return True

    # Merge has FF semantics that complicate the bare --no-commit / --ff-only
    # treatment.  Use a dedicated check rather than the generic opt-out table.
    # --ff-only does NOT prevent a HEAD update (fast-forward moves HEAD to the
    # branch tip); bare --no-commit does NOT prevent fast-forward either.
    # Only --squash and (--no-ff + --no-commit) together are genuine bypasses.
    if canonical == "merge":
        if _merge_skips_history_change(remaining_toks):
            return False
        return True

    # `commit` itself doesn't have a --no-commit flag; neither does `am`.
    # For the subcommands that do support opt-out, check for the flags.
    #
    # Flag detection honours value-taking options. A naive `if "--no-commit"
    # in remaining_toks` is wrong because `git commit -m --no-commit` has
    # message="--no-commit" — the string appears in remaining_toks as the value
    # of `-m`, NOT as a standalone flag, and the commit will still produce a
    # commit. _standalone_flags() consumes value-taker values so they are not
    # yielded; `--opt=value` forms are already single tokens and handled
    # naturally. The per-canonical value-taker set covers both the generic
    # commit options (when canonical == "commit") and subcommand-specific ones
    # (cherry-pick / revert / am).
    if canonical == "commit":
        value_takers = COMMIT_VALUE_TAKING_OPTS
    else:
        value_takers = SUBCMD_VALUE_TAKING_OPTS.get(canonical, set())
    standalone = set(_standalone_flags(remaining_toks, value_takers))
    if "--no-commit" in standalone:
        return False
    opt_outs = SUBCMD_SPECIFIC_NO_COMMIT_FLAGS.get(canonical, set())
    if standalone & opt_outs:
        return False
    return True


cmd = os.environ.get("_GATE_CMD", "")


def normalize_newlines(cmd):
    """Replace unquoted newlines with ';' so they segment the command properly.

    POSIX shell treats newline as a statement terminator equivalent to ';'.
    shlex with punctuation_chars=True treats '\\n' as whitespace, which means
    multi-line commands collapse into a single segment. Pre-processing
    newlines into ';' (only outside quotes) restores correct segmentation.

    Quote tracking is approximate but sufficient for command detection:
    single quotes block double-quote state, and vice versa.
    """
    out = []
    in_single = False
    in_double = False
    escape = False
    for ch in cmd:
        if escape:
            out.append(ch)
            escape = False
            continue
        if ch == "\\" and not in_single:
            out.append(ch)
            escape = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(ch)
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            continue
        if ch == "\n" and not in_single and not in_double:
            out.append(";")
            continue
        out.append(ch)
    return "".join(out)


def tokenize_command(cmd):
    """Tokenize a shell command string into individual tokens.

    Uses shlex.shlex with punctuation_chars=True so that shell operators
    (;, &&, ||, |, <, >, (, )) are returned as standalone tokens even
    when not surrounded by whitespace. Quotes are still respected — content
    inside quotes is treated as a single token regardless of any operators
    inside.

    Newlines are pre-processed to ';' via normalize_newlines() because POSIX
    shell treats newline as a statement terminator but shlex treats it as
    whitespace, which would collapse multi-line commands into one segment.

    Returns the token list, or None on parse failure (caller fail-opens).
    """
    cmd = normalize_newlines(cmd)
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return None


def shell_segments(cmd):
    """Yield lists of tokens, one per shell segment, split on operator tokens."""
    all_toks = tokenize_command(cmd)
    if all_toks is None:
        return
    SEPARATORS = {
        # Command separators (the full Bash control-operator set that ends one
        # simple command and begins another). `&` (background) and `|&` (pipe
        # stdout+stderr) were missing, so `true & git commit` / `cmd |& git
        # commit` buried the commit mid-segment and skipped the cascade check.
        # The `;;` / `;&` / `;;&` case-terminators are included for completeness
        # (harmless to split on; they never co-occur with `$(`).
        ";", "&&", "||", "|", "&", "|&", ";;", ";&", ";;&",
        # Redirection operators (terminate the command — the following token is
        # a filename/fd, not part of the command)
        ">", ">>", "<", "<<", "&>", "&>>", "2>", "2>>",
    }
    segment = []
    for tok in all_toks:
        if tok in SEPARATORS:
            if segment:
                yield segment
                segment = []
        else:
            segment.append(tok)
    if segment:
        yield segment


def _strip_subshell_grouping(toks):
    """Remove subshell grouping tokens from a segment: `( git commit )` → `git
    commit`. Without this, a segment like `(git commit -m x)` has first token
    `(`, is not recognised as git, and the commit bypasses the cascade check.

    Only bare `(` / `)` grouping tokens are stripped. This does NOT affect
    `$( ... )` command substitution: those segments begin with `$` (the
    substitution-as-executable guard handles them), so a leading `(` is never
    the substitution marker here. A trailing `)` that is actually a real
    pathspec named ")" is pathological and not supported.
    """
    while toks and toks[0] == "(":
        toks = toks[1:]
    while toks and toks[-1] == ")":
        toks = toks[:-1]
    return toks


# ---------------------------------------------------------------------------
# Pre-flight introspection helpers for initial-form operations
# ---------------------------------------------------------------------------

def is_continuation(remaining_toks):
    """Return True if the remaining tokens contain a --continue flag.

    --continue means the operation will write a commit from the current
    staging area, so --staged-only cascade check is applied.
    """
    return any(t in CONTINUATION_FLAGS for t in remaining_toks)


# Value-taking options for `git commit` that consume the next token as a value
# in the space-separated form (--opt value / -o value).  Defined at module level
# so both files_for_commit() and is_recovery() can share it without duplication.
#
# NOTE: --pathspec-from-file is intentionally NOT listed here; it is intercepted
# separately in files_for_commit() so the file can be read and its entries
# converted to pathspec_args.
COMMIT_VALUE_TAKING_OPTS = {
    "-m", "--message",
    "-F", "--file",
    "-t", "--template",
    "-C", "--reuse-message",
    "-c", "--reedit-message",
    "--cleanup",
    "--date",
    "--author",
    "--squash",
    "--fixup",
    "--trailer",
    "--pathspec-from-file",
}


def is_recovery(canonical_subcmd, remaining_toks):
    """True if a recovery flag appears as a standalone option in remaining_toks.

    Context-aware: walks tokens honoring value-takers so that a RECOVERY_FLAG
    that appears as the VALUE of a prior value-taking option is not mistaken for
    a standalone recovery flag.  Also stops scanning at '--' (everything after
    the pathspec separator is a pathspec, not an option).

    Examples:
      git commit -m --abort         → False  (--abort is -m's value)
      git commit -F /tmp/--abort    → False  (-F's value is a file path)
      git commit -- --abort         → False  (--abort is a pathspec after --)
      git cherry-pick --abort       → True   (standalone recovery flag)
      git rebase --abort            → True   (standalone recovery flag)
    """
    # Merge per-subcommand value-takers with commit-specific ones when relevant.
    value_takers = SUBCMD_VALUE_TAKING_OPTS.get(canonical_subcmd, set())
    if canonical_subcmd == "commit":
        value_takers = value_takers | COMMIT_VALUE_TAKING_OPTS

    i = 0
    while i < len(remaining_toks):
        t = remaining_toks[i]
        if t == "--":
            return False  # everything after -- is a pathspec, not an option
        if t in RECOVERY_FLAGS:
            return True
        # --opt=value: single token, no separate value consumed
        if t.startswith("--") and "=" in t:
            i += 1
            continue
        # Value-taking flag in space form: consume this token + the next (its value)
        if t in value_takers and i + 1 < len(remaining_toks):
            i += 2
            continue
        # Any other flag (short or long without =, not a known value-taker)
        if t.startswith("-"):
            i += 1
            continue
        # Non-option positional token (ref, path, etc.)
        i += 1
    return False


# Per-subcommand options that take a separate value token in the space-separated
# form (--opt value / -o value).  The --opt=value / -ovalue attached forms are
# always single-token and do not need special handling.
#
# Notes:
#  - -S / --gpg-sign: the keyid is OPTIONAL (man git: -S[<keyid>]).  The common
#    forms are bare `-S` or attached `-Skeyid` / `--gpg-sign=keyid`.  Treating
#    `-S` / `--gpg-sign` as value-taking would risk consuming a real ref when the
#    flag is used bare.  So they are intentionally NOT listed here.
#  - --onto for rebase: rebase falls back to staged-only whenever --onto is present
#    (complex form), so extract_positionals is never reached for that case.  The
#    entry is harmless but kept for completeness.
#  - -i / --interactive for rebase: these are flag-only (no value), excluded.
SUBCMD_VALUE_TAKING_OPTS = {
    "merge": {
        "-m", "--message",
        "-F", "--file",
        "-s", "--strategy",
        "-X", "--strategy-option",
    },
    "cherry-pick": {
        "-m", "--mainline",
        "-X", "--strategy-option",
    },
    "revert": {
        "-m", "--mainline",
    },
    "rebase": {
        "-s", "--strategy",
        "-X", "--strategy-option",
        "--exec", "-x",
        "--onto",
    },
}


def extract_positionals(subcmd, remaining_toks):
    """Return positional tokens from remaining_toks, skipping options and their values.

    Handles:
      - --opt=value  single-token (no skip)
      - --opt value  double-token when --opt is in SUBCMD_VALUE_TAKING_OPTS[subcmd]
      - -o value     double-token when -o  is in SUBCMD_VALUE_TAKING_OPTS[subcmd]
      - all other -flags  single-token (no skip)
      - non-option tokens  collected as positionals

    Note on -S / --gpg-sign: these accept an optional keyid but are treated as
    single-token here to avoid consuming a real ref.  The space-separated form
    `git cherry-pick -S keyid ref` would misidentify `keyid` as a positional,
    but that form is uncommon compared to bare `-S` or `-Skeyid`.
    """
    value_takers = SUBCMD_VALUE_TAKING_OPTS.get(subcmd, set())
    positionals = []
    i = 0
    while i < len(remaining_toks):
        t = remaining_toks[i]
        if t.startswith("--"):
            if "=" in t:
                # --opt=value form — single token, no value to skip
                i += 1
                continue
            if t in value_takers and i + 1 < len(remaining_toks):
                # --opt value form — consume both tokens
                i += 2
                continue
            # Value-less long flag (e.g. --no-ff, --squash)
            i += 1
            continue
        if t.startswith("-") and len(t) > 1:
            # Short flag (possibly combined, e.g. -ms is treated as a single token by shlex)
            if t in value_takers and i + 1 < len(remaining_toks):
                # -o value form — consume both tokens
                i += 2
                continue
            i += 1
            continue
        # Bare positional token (a ref, branch name, etc.)
        positionals.append(t)
        i += 1
    return positionals


def _extract_mainline_opt(args):
    """Return the mainline parent number (int) or None if not present.

    Recognizes all three forms accepted by git cherry-pick / git revert:
      -m <N>            space-separated short form
      --mainline <N>    space-separated long form
      --mainline=<N>    attached long form
    """
    i = 0
    while i < len(args):
        t = args[i]
        if t in ("-m", "--mainline"):
            if i + 1 < len(args):
                try:
                    return int(args[i + 1])
                except ValueError:
                    return None
            return None
        if t.startswith("--mainline="):
            try:
                return int(t[len("--mainline="):])
            except ValueError:
                return None
        i += 1
    return None


def files_for_show(refs, mainline=None):
    """For each ref, return the union of files touched across all refs.

    When mainline is set, uses a mainline-aware diff (correct for merge
    commits being cherry-picked/reverted with -m <N>).  Otherwise uses
    git show (correct for non-merge commits).

    Returns a list of paths, or None on any introspection failure (caller
    falls back to --staged-only).
    """
    per_commit = files_for_show_per_commit(refs, mainline=mainline)
    if per_commit is None:
        return None
    files = set()
    for inner in per_commit:
        files.update(inner)
    return list(files)


def files_for_diff_range(spec):
    """Return files in a git diff for the given ref spec (e.g. 'HEAD...branch').

    Returns a list of paths, or None on failure.
    """
    try:
        r = subprocess.run(
            # --no-renames so a renamed trigger file surfaces BOTH its old and
            # new paths (delete + add) in the cascade-checked set; the default
            # rename detection would report only the destination path and let a
            # pure rename of a trigger bypass its rule.
            ["git", "diff", "--name-only", "--no-renames", spec],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0:
            return None
        return [l.strip() for l in r.stdout.splitlines() if l.strip()]
    except (subprocess.SubprocessError, OSError):
        return None


def files_for_log_range(spec):
    """Return files touched by all commits in a log range (e.g. 'upstream..HEAD').

    Returns a list of paths, or None on failure.
    """
    try:
        r = subprocess.run(
            ["git", "log", "--name-only", "--no-renames", "--format=", spec],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0:
            return None
        files = set()
        for line in r.stdout.splitlines():
            line = line.strip()
            if line:
                files.add(line)
        return list(files)
    except (subprocess.SubprocessError, OSError):
        return None


def files_for_show_per_commit(refs, mainline=None):
    """Return list of per-commit file lists for cherry-pick/revert multi-ref forms.

    Each inner list contains the files touched by the corresponding ref, in the
    same order as refs.  Returns None on any subprocess failure (caller falls
    back to staged-only).

    When mainline is set, uses `git diff --name-only <ref>^<mainline> <ref>`
    for each ref.  This is the correct approach for merge commits being
    cherry-picked or reverted with `-m <N>` / `--mainline <N>`: git show
    returns no paths for merge commits by default, producing an empty file
    list that would cause cascade rules to be silently skipped.  The mainline
    diff explicitly computes the delta between the selected parent and the
    merge commit, matching what git will apply when replaying it.

    When mainline is None, falls back to `git show --name-only` (correct for
    ordinary non-merge commits).
    """
    results = []
    for ref in refs:
        files = None
        if mainline is not None:
            # Mainline-aware diff: <ref>^<mainline> is the selected parent.
            spec = f"{ref}^{mainline}"
            try:
                r = subprocess.run(
                    ["git", "diff", "--name-only", "--no-renames", spec, ref],
                    capture_output=True, text=True, timeout=5
                )
                if r.returncode == 0:
                    files = [line.strip() for line in r.stdout.splitlines() if line.strip()]
                else:
                    # Mainline diff failed (e.g. parent index N out of range for
                    # this merge commit). Honour fail-open: signal introspection
                    # failure so the caller falls back to --staged-only. Do NOT
                    # fall through to the git-show branch below — for a merge
                    # commit `git show --name-only` yields an empty list, which
                    # would let the cascade pass silently instead of degrading
                    # to the staged-only check.
                    return None
            except (subprocess.SubprocessError, OSError):
                return None
        if files is None:
            # Fall back to git show for non-merge commits (mainline is None).
            try:
                r = subprocess.run(
                    ["git", "show", "--name-only", "--no-renames", "--format=", ref],
                    capture_output=True, text=True, timeout=5
                )
                if r.returncode != 0:
                    return None
                files = [line.strip() for line in r.stdout.splitlines() if line.strip()]
            except (subprocess.SubprocessError, OSError):
                return None
        results.append(files)
    return results


def files_for_rebase_per_commit(upstream, branch="HEAD"):
    """Return list of per-commit file lists for the rebase range upstream..branch.

    Resolves the commit SHAs in upstream..branch order (oldest-first via reverse)
    then returns one inner file list per commit.  Returns None on any failure;
    returns [] when the range is empty (nothing to rebase).
    """
    try:
        r = subprocess.run(
            ["git", "log", "--format=%H", "--reverse", f"{upstream}..{branch}"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0:
            return None
        shas = [line.strip() for line in r.stdout.splitlines() if line.strip()]
    except (subprocess.SubprocessError, OSError):
        return None
    if not shas:
        return []
    return files_for_show_per_commit(shas)


def _is_ancestor(maybe_ancestor, descendant):
    """Return True if `maybe_ancestor` is an ancestor of `descendant`, False if
    not, or None if it cannot be determined (subprocess/ref error).

    `git merge-base --is-ancestor A B` exits 0 when A is an ancestor of B
    (so a `git merge B` from A would fast-forward), 1 when it is not, and other
    codes on error.
    """
    try:
        r = subprocess.run(
            ["git", "merge-base", "--is-ancestor", maybe_ancestor, descendant],
            capture_output=True, timeout=5
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if r.returncode == 0:
        return True
    if r.returncode == 1:
        return False
    return None


# ---------------------------------------------------------------------------
# F2: git commit file-set determination (-a/--all and pathspec support)
# ---------------------------------------------------------------------------

# Short flags for `git commit` that consume the next character(s) as an
# attached value when used in combined form (e.g. -mMsg, -Ffile).
# When one of these appears in a cluster, everything after it is the value,
# not more flags.  Per `man git-commit`:
#   -m <msg>, -F <file>, -t <file>, -C <commit>, -c <commit>, -S[<keyid>]
# Note: -S is included because -Skeyid is a valid attached-value form even
# though the keyid is optional.
COMMIT_SHORT_VALUE_TAKERS = {"m", "F", "t", "C", "c", "S"}


def _unquote_pathspec_entry(entry):
    """Decode a pathspec entry quoted per git's core.quotePath C-style rules.

    Quoted entries start and end with double quotes and may contain C-escapes
    (\\n, \\t, \\\\, \\\", octal \\NNN, hex \\xNN).  Unquoted entries are
    returned as-is.

    Examples:
      'normal/path.txt'             -> 'normal/path.txt'
      '"quoted path with spaces.txt"' -> 'quoted path with spaces.txt'
      '"path\\twith\\ttab.txt"'     -> 'path\twith\ttab.txt' (literal tab)
      '"path with \\"quotes\\".txt"' -> 'path with "quotes".txt'
      '""'                          -> ''
    """
    entry = entry.strip()
    if not entry:
        return entry
    if not (entry.startswith('"') and entry.endswith('"') and len(entry) >= 2):
        return entry
    inner = entry[1:-1]
    try:
        import codecs
        decoded_bytes, _ = codecs.escape_decode(inner.encode("utf-8"))
        return decoded_bytes.decode("utf-8", errors="replace")
    except (UnicodeError, ValueError):
        try:
            import ast
            return ast.literal_eval(entry)
        except (ValueError, SyntaxError):
            return inner


def _read_pathspec_file(path, nul_separated=False):
    """Read pathspec entries from a file.  Returns list of paths or None on error.

    path: file path string, or '-' for stdin.
    nul_separated: if True, entries are NUL-delimited (--pathspec-file-nul was given).
                   if False, entries are newline-delimited.

    Returns None when:
      - path is '-' (stdin): the hook contract consumes stdin for the JSON payload;
        stdin is not available for pathspec input.  Callers fall back to --staged-only.
      - file cannot be opened/read (OSError / IOError).

    Blank lines are ignored for newline-separated mode (consistent with git behaviour).
    NUL-terminated entries: a trailing NUL after the last entry is silently dropped.

    Entries quoted in git's core.quotePath C-style format are unquoted via
    _unquote_pathspec_entry().
    """
    if path == "-":
        # Stdin is consumed by Claude Code's hook contract for the JSON; not
        # available for pathspec input.  Fall back conservatively to staged-only.
        return None
    try:
        with open(path, "rb") as f:
            data = f.read()
    except (OSError, IOError):
        return None
    if nul_separated:
        raw = [s.decode("utf-8", errors="replace") for s in data.split(b"\x00") if s]
    else:
        raw = [line for line in data.decode("utf-8", errors="replace").splitlines() if line.strip()]
    return [_unquote_pathspec_entry(e) for e in raw]


def _has_short_flag(token, target_char):
    """Return True if `target_char` appears as a flag in this short-flag cluster.

    Walks the cluster char-by-char after the leading '-'.  If target_char
    appears before any value-taking short flag, return True.  If a value-taker
    appears first, everything after it is the attached value (not more flags),
    so return False.

    Examples (target_char='a'):
      -a      → True
      -am     → True  (a before m)
      -ma     → False (m is value-taker; 'a' is part of -m's value)
      -Sgpgkey-abc → False (S is value-taker; 'a' is part of -S's value)
      -mama   → False (m is value-taker; 'ama' is -m's value)

    Examples (target_char='i'):
      -i      → True
      -im     → True  (i before m)
      -mi     → False (m is value-taker; 'i' is part of -m's value)
    """
    if not token.startswith("-") or token.startswith("--") or len(token) < 2:
        return False
    for c in token[1:]:
        if c == target_char:
            return True
        if c in COMMIT_SHORT_VALUE_TAKERS:
            return False
    return False


def _has_a_flag(token):
    """Return True if `-a` appears as a flag in this short-flag cluster.

    Thin wrapper around _has_short_flag(token, 'a') for backward compatibility.
    """
    return _has_short_flag(token, "a")


def _resolve_implicit_merge_head():
    """Find the implicit merge head for `git merge` with no args.

    Returns the resolved ref name (string), or None if undeterminable.

    Tries in order:
      1. FETCH_HEAD — present when a recent `git fetch` or `git pull --no-merge`
         downloaded refs without merging them.
      2. @{upstream} — the configured upstream branch for the current branch
         (branch.<name>.merge / branch.<name>.remote in git config).

    Returns None when neither is resolvable (caller falls back to staged-only
    conservatively).
    """
    # FETCH_HEAD first (recent fetch without merge)
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", "FETCH_HEAD"],
            capture_output=True, text=True, timeout=2
        )
        if r.returncode == 0 and r.stdout.strip():
            return "FETCH_HEAD"
    except (subprocess.SubprocessError, OSError):
        pass
    # Configured upstream
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            capture_output=True, text=True, timeout=2
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def files_for_commit(remaining_toks, cwd_override=None, cwd_unknown=False):
    """Determine the complete file set that `git commit` will actually commit.

    Handles four modes:
      1. Default (no -a, no pathspec, no --pathspec-from-file) → ('staged-only', None)
      2. -a / --all → staged files UNION tracked-modified files
      3. Explicit pathspecs only (no -a) → ONLY pathspec-scoped files
         (working-tree vs HEAD restricted to pathspecs, UNION staged content
         of those same pathspec paths).  Files outside the pathspec that are
         staged are NOT included — they will not enter the commit.
      4. --pathspec-from-file=<file> / --pathspec-from-file <file> → read pathspec
         entries from the file; treat them the same as explicit positional pathspecs.
         If <file> is '-' (stdin), fail closed (exit 2) — stdin is consumed by the
         hook contract and unavailable for inspection.
         If the file cannot be read, fail closed (exit 2) — the gate cannot determine
         what will be committed, so it refuses rather than silently allowing it.
         --pathspec-file-nul modifies parsing to NUL-separated entries.

    cwd_override: when provided (from a -C <path> global option), relative
         pathspec-from-file paths are resolved relative to this directory rather
         than the hook process CWD.  Absolute paths are unaffected.  This matches
         git's own -C semantics where relative file arguments are interpreted in
         the -C directory.

    Per `man git-commit`: when pathspecs are given, the command records ONLY
    changes to the named paths.  Files outside the pathspec stay staged but
    are not committed.  Therefore, for cascade checking purposes, the file
    set must be restricted to the pathspec files, not the full staged set.

    Combined short flags (e.g. -am) are recognized via _has_a_flag(), which
    walks the cluster and stops at value-taking short flags so that attached
    values (e.g. -Sgpgkey-abc) are not misidentified as flag characters.

    Value-taking options for `git commit` are skipped correctly so their values
    are not mistaken for pathspecs.

    Returns ('staged-only', None) when no -a and no pathspecs are detected.
    Falls back to ('staged-only', None) on any git introspection failure.
    """
    # Options for `git commit` that consume the next token as a value.
    # NOTE: --pathspec-from-file is intentionally NOT listed here; it is
    # intercepted first (below) so we can read the file and populate pathspec_args.
    # We use the module-level COMMIT_VALUE_TAKING_OPTS constant (minus
    # --pathspec-from-file, which is handled separately above).
    commit_value_takers = COMMIT_VALUE_TAKING_OPTS - {"--pathspec-from-file"}

    # Detect --pathspec-file-nul anywhere in the token list (flag-only, no value).
    nul_sep = "--pathspec-file-nul" in remaining_toks

    has_all = False
    has_include = False
    has_amend = False
    has_only = False
    has_patch = False
    has_interactive = False
    has_reword_fixup = False   # --fixup=reword:<c>  (message-only: amend + --only)
    has_amend_fixup = False    # --fixup=amend:<c>   (message-only only with --only)
    pathspec_args = []
    saw_double_dash = False
    i = 0
    while i < len(remaining_toks):
        t = remaining_toks[i]
        if saw_double_dash:
            pathspec_args.append(t)
            i += 1
            continue
        if t == "--":
            saw_double_dash = True
            i += 1
            continue

        # --pathspec-file-nul is a flag-only modifier; consumed implicitly via
        # the nul_sep pre-scan above.  Skip it here so it is not treated as a
        # pathspec or unknown option.
        if t == "--pathspec-file-nul":
            i += 1
            continue

        # --pathspec-from-file=<file>  (single-token = form)
        if t.startswith("--pathspec-from-file="):
            file_path = t[len("--pathspec-from-file="):]
            if file_path == "-":
                print(
                    "FAIL: cascade gate: --pathspec-from-file=- reads pathspecs from stdin, "
                    "which is consumed by the PreToolUse hook contract and unavailable for "
                    "the gate to inspect. DRIFT-002 cannot be enforced for stdin-fed "
                    "pathspec commits. Use a literal pathspec list or a regular file instead.",
                    file=sys.stderr
                )
                return ("fail-closed", None)
            # Resolve relative paths against cwd_override (-C <path>) when set.
            if cwd_override and not os.path.isabs(file_path):
                file_path = os.path.join(cwd_override, file_path)
            entries = _read_pathspec_file(file_path, nul_separated=nul_sep)
            if entries is None:
                # File is unreadable — fail closed; the gate cannot determine
                # what will be committed, so it refuses rather than silently allowing it.
                print(
                    f"FAIL: cascade gate: --pathspec-from-file={t[len('--pathspec-from-file='):]} is unreadable. "
                    "DRIFT-002 cannot be enforced for commits with an unreadable pathspec file.",
                    file=sys.stderr
                )
                return ("fail-closed", None)
            pathspec_args.extend(entries)
            i += 1
            continue

        # --pathspec-from-file <file>  (space-separated form)
        if t == "--pathspec-from-file":
            if i + 1 < len(remaining_toks):
                file_path = remaining_toks[i + 1]
                if file_path == "-":
                    print(
                        "FAIL: cascade gate: --pathspec-from-file - reads pathspecs from stdin, "
                        "which is consumed by the PreToolUse hook contract and unavailable for "
                        "the gate to inspect. DRIFT-002 cannot be enforced for stdin-fed "
                        "pathspec commits. Use a literal pathspec list or a regular file instead.",
                        file=sys.stderr
                    )
                    return ("fail-closed", None)
                # Resolve relative paths against cwd_override (-C <path>) when set.
                resolved_path = file_path
                if cwd_override and not os.path.isabs(file_path):
                    resolved_path = os.path.join(cwd_override, file_path)
                entries = _read_pathspec_file(resolved_path, nul_separated=nul_sep)
                if entries is None:
                    # File is unreadable — fail closed.
                    print(
                        f"FAIL: cascade gate: --pathspec-from-file {file_path} is unreadable. "
                        "DRIFT-002 cannot be enforced for commits with an unreadable pathspec file.",
                        file=sys.stderr
                    )
                    return ("fail-closed", None)
                pathspec_args.extend(entries)
                i += 2
            else:
                # Bare --pathspec-from-file with no following token — malformed;
                # fall back safely.
                return ("staged-only", None)
            continue

        # --fixup=<value> / --fixup <value>: detect message-only variants before
        # the generic option branches consume the token. `reword:<c>` is git's
        # shorthand for `amend:<c> --only` (a log-message-only commit that
        # ignores the index); `amend:<c>` is message-only only when combined
        # with --only. Plain `fixup:<c>` (no prefix) includes the staged index
        # and is checked normally.
        fixup_val = None
        fixup_consume = 1
        if t.startswith("--fixup="):
            fixup_val = t[len("--fixup="):]
        elif t == "--fixup" and i + 1 < len(remaining_toks):
            fixup_val = remaining_toks[i + 1]
            fixup_consume = 2
        if fixup_val is not None:
            if fixup_val.startswith("reword:"):
                has_reword_fixup = True
            elif fixup_val.startswith("amend:"):
                has_amend_fixup = True
            i += fixup_consume
            continue

        # Long options with =value form: single token, no value to skip.
        if t.startswith("--") and "=" in t:
            i += 1
            continue
        # Long options that take a separate value token.
        if t in commit_value_takers:
            i += 2 if i + 1 < len(remaining_toks) else 1
            continue
        # Long flags (no value).
        if t.startswith("--"):
            if t == "--all":
                has_all = True
            elif t == "--include":
                has_include = True
            elif t == "--only":
                has_only = True
            elif t == "--amend":
                has_amend = True
            elif t == "--patch":
                has_patch = True
            elif t == "--interactive":
                has_interactive = True
            i += 1
            continue
        # Short flag(s).  May be combined, e.g. -am, -ma.
        if t.startswith("-") and len(t) > 1:
            # Check for combined -a / -i / -o / -p using _has_short_flag(), which
            # walks the cluster and stops at value-taking short flags.  This
            # correctly handles -a, -am (True for 'a') and -i, -im (True for 'i'),
            # but NOT -ma or -mi where 'a'/'i' is part of an attached value rather
            # than a flag.  Likewise -p detects --patch in combined clusters like
            # -ap or -ip.
            if _has_short_flag(t, "a"):
                has_all = True
            if _has_short_flag(t, "i"):
                has_include = True
            if _has_short_flag(t, "o"):
                has_only = True
            if _has_short_flag(t, "p"):
                has_patch = True
            # Skip value if it's a known single-char value-taker embedded
            # as a standalone short flag (e.g. plain -m or -F).
            if t in commit_value_takers:
                i += 2 if i + 1 < len(remaining_toks) else 1
                continue
            i += 1
            continue
        # Non-option, non-flag token: treat as pathspec.
        pathspec_args.append(t)
        i += 1

    # Message-only commit forms: git records a log-message-only commit using the
    # existing tree, NOT the current index, so no staged file enters the commit
    # and the gate must bypass (checking files the commit will never include
    # would be a false positive). All require no explicit pathspec and no -a
    # (those would scope real content into the commit). The forms:
    #   - --amend --only            : message-only amend
    #   - --fixup=reword:<c>        : shorthand for --fixup=amend:<c> --only
    #   - --fixup=amend:<c> --only  : amend! commit restricted to no paths
    message_only = (
        (has_amend and has_only)
        or has_reword_fixup
        or (has_amend_fixup and has_only)
    )
    if message_only and not pathspec_args and not has_all:
        return ("bypass", None)

    # --patch (-p) and --interactive open an interactive TUI/hunk-selector
    # during the commit, allowing the user to selectively stage and commit
    # hunks or files on-the-fly.  The gate cannot preflight what the user
    # will select, so it fails closed rather than silently allowing a commit
    # that may contain cascade-violating changes.
    # To enforce DRIFT-002, stage changes explicitly (e.g. `git add -p`) then
    # run `git commit` separately without interactive flags.
    if has_patch or has_interactive:
        print(
            "FAIL: cascade gate: `git commit --patch`/`--interactive` "
            "interactively selects content during the commit, so the gate "
            "cannot preflight what will be committed. To use cascade "
            "enforcement, stage changes explicitly (e.g., `git add -p`) "
            "then run `git commit` separately.",
            file=sys.stderr
        )
        return ("fail-closed", None)

    # Fast path: default commit with no -a and no pathspecs.
    if not has_all and not pathspec_args:
        return ("staged-only", None)

    # Pathspecs are interpreted relative to the shell cwd. If a prior
    # unresolvable `cd` left that cwd unknown (and there is no absolute
    # git -C / env --chdir override to anchor it), the gate cannot resolve the
    # pathspecs to repo-relative paths — fail closed rather than check the
    # wrong paths. (-a / --include without pathspecs is cwd-independent: it
    # commits all tracked modifications repo-wide, so it is safe to proceed.)
    if pathspec_args and cwd_unknown and not (cwd_override and os.path.isabs(cwd_override)):
        print(
            "FAIL: cascade gate: a prior unresolvable `cd` precedes a pathspec "
            "commit, so the gate cannot resolve which paths will be committed. "
            "Run the commit as a separate command, or use `git -C <dir>` instead "
            "of `cd`.",
            file=sys.stderr,
        )
        return ("fail-closed", None)

    # --include mode (-i / --include): union of ALL staged files PLUS pathspec
    # working-tree files.  Per `man git-commit`: -i stages the given pathspecs
    # and then commits the ENTIRE staging area (pre-existing staged content plus
    # the newly staged pathspecs).  Without pathspecs, -i is a no-op modifier
    # that falls through to default staged-only semantics.
    if has_include and pathspec_args and not has_all:
        files = set()
        # Collect all currently staged files (the full staging area).
        try:
            r = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--no-renames"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    line = line.strip()
                    if line:
                        files.add(line)
        except (subprocess.SubprocessError, OSError):
            return ("staged-only", None)
        # Also include pathspec working-tree files (what -i stages before committing).
        # When cwd_override is set (from `git -C <dir>`), pass -C so git resolves
        # the relative pathspecs against the correct working directory.  git diff
        # always outputs paths relative to the repo root regardless of -C, so
        # the returned paths are directly comparable to cascade rule globs.
        try:
            _git_cmd = ["git"]
            if cwd_override:
                _git_cmd.extend(["-C", cwd_override])
            _git_cmd.extend(["diff", "--name-only", "--no-renames", "HEAD", "--"] + pathspec_args)
            r = subprocess.run(
                _git_cmd,
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    line = line.strip()
                    if line:
                        files.add(line)
        except (subprocess.SubprocessError, OSError):
            pass  # Best-effort; staged contribution already captured.
        return ("files", sorted(files))

    # Pathspec-only mode (no -a / --all, no -i / --include; explicit --only
    # semantics or the implicit default when pathspecs are given).
    # Per `man git-commit`: when pathspecs are given, ONLY the named paths are
    # committed.  Files outside the pathspec stay staged but are NOT in this
    # commit.  So we restrict the cascade-check file set entirely to the
    # pathspec paths — the broader staged set is irrelevant for this commit.
    if pathspec_args and not has_all:
        files = set()
        # Working-tree vs HEAD restricted to the pathspecs (covers unstaged
        # modifications that git commit will pull in from the working tree).
        # When cwd_override is set (from `git -C <dir>`), pass -C so git resolves
        # the relative pathspecs against the correct working directory.  Paths
        # returned by git diff are always relative to the repo root, so they
        # are directly comparable to cascade rule globs without further adjustment.
        try:
            _git_cmd = ["git"]
            if cwd_override:
                _git_cmd.extend(["-C", cwd_override])
            _git_cmd.extend(["diff", "--name-only", "--no-renames", "HEAD", "--"] + pathspec_args)
            r = subprocess.run(
                _git_cmd,
                capture_output=True, text=True, timeout=5
            )
            if r.returncode != 0:
                return ("staged-only", None)
            for line in r.stdout.splitlines():
                line = line.strip()
                if line:
                    files.add(line)
        except (subprocess.SubprocessError, OSError):
            return ("staged-only", None)
        # Also include the staged content of the pathspec paths (covers files
        # that are already staged for those paths but not modified in the
        # working tree beyond what is staged).
        try:
            _git_cmd = ["git"]
            if cwd_override:
                _git_cmd.extend(["-C", cwd_override])
            _git_cmd.extend(["diff", "--cached", "--name-only", "--no-renames", "HEAD", "--"] + pathspec_args)
            r = subprocess.run(
                _git_cmd,
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    line = line.strip()
                    if line:
                        files.add(line)
        except (subprocess.SubprocessError, OSError):
            pass  # Best-effort; working-tree contribution already captured.
        return ("files", sorted(files))

    # -a / --all mode: build the union of staged + tracked-modified files.
    files = set()

    # Start with currently staged paths.
    try:
        r = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--no-renames"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                line = line.strip()
                if line:
                    files.add(line)
    except (subprocess.SubprocessError, OSError):
        return ("staged-only", None)

    # -a stages all modifications to tracked files during the commit.
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "--no-renames"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                line = line.strip()
                if line:
                    files.add(line)
    except (subprocess.SubprocessError, OSError):
        return ("staged-only", None)

    return ("files", sorted(files))


def determine_check_target(canonical_subcmd, remaining_toks, cwd_override=None, cwd_unknown=False):
    """Return ('bypass', None), ('staged-only', None), ('files', [paths]),
    ('files-multi', [[paths], ...]), or ('fail-closed', None).

    'bypass' — recovery/control flags (--abort, --quit, --skip); no commit is
    written so the gate must not run at all.  Caller must exit 0 immediately.

    'staged-only' — continuation flags (--continue) or fallback; staging area
    holds resolved content; check-cascade.sh is invoked with --staged-only.

    'files' — initial-form operations; pre-flighted file list supplied to
    check-cascade.sh with --files.

    'files-multi' — multi-commit operations (cherry-pick/revert with multiple
    refs, rebase replay); files is a List[List[str]] where each inner list is
    one commit's file set.  The dispatcher checks each commit independently and
    blocks on the FIRST violating commit (preserving per-commit semantics).
    git merge retains 'files' mode (union) because it produces one merge commit.

    'fail-closed' — the gate cannot safely determine what will be committed
    (e.g. stdin pathspec, unreadable pathspec file); caller must exit 2
    immediately.  DRIFT-002 cannot be enforced for opaque inputs.

    cwd_override: last -C <path> value from the global option walk, or None.
         Passed through to files_for_commit() for pathspec-from-file resolution.

    Falls back to ('staged-only', None) on git introspection failures (fail-open
    conservative).  Fails closed ('fail-closed', None) when the command form
    makes it structurally impossible to determine the file set.
    """
    # Recovery flags do not produce a commit; bypass entirely.
    if is_recovery(canonical_subcmd, remaining_toks):
        return ("bypass", None)
    if is_continuation(remaining_toks):
        return ("staged-only", None)
    if canonical_subcmd == "commit":
        return files_for_commit(remaining_toks, cwd_override=cwd_override, cwd_unknown=cwd_unknown)
    if canonical_subcmd == "am":
        # Out of scope — patch preview is hard. Documented limitation.
        # Falls back to --staged-only.
        return ("staged-only", None)
    positionals = extract_positionals(canonical_subcmd, remaining_toks)
    if canonical_subcmd in ("cherry-pick", "revert"):
        if not positionals:
            return ("staged-only", None)
        mainline = _extract_mainline_opt(remaining_toks)
        per_commit = files_for_show_per_commit(positionals, mainline=mainline)
        if per_commit is None:
            return ("staged-only", None)
        return ("files-multi", per_commit)
    if canonical_subcmd == "merge":
        if not positionals:
            implicit = _resolve_implicit_merge_head()
            if implicit is None:
                return ("staged-only", None)
            positionals = [implicit]
        # A FAST-FORWARD merge replays each incoming commit into history
        # unchanged (HEAD just advances to the target tip), exactly like
        # cherry-pick/rebase — so each commit must be checked independently
        # (files-multi). A union check would let an individual violating commit
        # land while a LATER incoming commit supplies the companion, satisfying
        # the union but committing the violation to history.
        #
        # A NON-fast-forward merge (--no-ff, octopus, or divergent histories)
        # instead records a single merge commit, for which the union of incoming
        # files is the correct unit.
        merge_value_takers = SUBCMD_VALUE_TAKING_OPTS.get("merge", set())
        merge_flags = set(_standalone_flags(remaining_toks, merge_value_takers))
        force_merge_commit = "--no-ff" in merge_flags
        is_octopus = len(positionals) > 1  # octopus always creates a merge commit
        if not force_merge_commit and not is_octopus:
            head = positionals[0]
            # Fast-forward happens iff HEAD is an ancestor of the merge target.
            if _is_ancestor("HEAD", head) is True:
                per_commit = files_for_rebase_per_commit("HEAD", head)
                if per_commit is None:
                    return ("staged-only", None)
                return ("files-multi", per_commit)
        # Non-FF / octopus / undeterminable: single merge commit → union.
        # If any ref lookup fails, fail open to staged-only.
        all_files: set = set()
        for head in positionals:
            files = files_for_diff_range(f"HEAD...{head}")
            if files is None:
                return ("staged-only", None)
            all_files.update(files)
        return ("files", sorted(all_files))
    if canonical_subcmd == "rebase":
        # Skip complex forms; fall back to staged-only conservatively.
        if "--onto" in remaining_toks or "-i" in remaining_toks or "--interactive" in remaining_toks:
            return ("staged-only", None)
        if not positionals:
            return ("staged-only", None)
        upstream = positionals[0]
        # `git rebase <upstream> <branch>` rebases <branch> onto <upstream>.
        # When a second positional is given, use it instead of HEAD so the
        # pre-flight covers the correct commit range.
        branch = positionals[1] if len(positionals) >= 2 else "HEAD"
        per_commit = files_for_rebase_per_commit(upstream, branch)
        if per_commit is None:
            return ("staged-only", None)
        return ("files-multi", per_commit)
    return ("staged-only", None)


# ---------------------------------------------------------------------------
# Pre-scan: path-qualified shell wrappers (raw-command scan)
# ---------------------------------------------------------------------------
# shlex with posix=True treats backslash as an escape character, so a Windows
# path like C:\Program Files\Git\bin\bash.exe is tokenized to "C:Program" and
# "FilesGitbinbash.exe" — the backslashes are silently consumed.  The per-segment
# is_shell_wrapper() check therefore never sees a backslash-containing first token
# for Windows-path forms.
#
# To catch Windows-path forms before shlex destroys the backslashes, we run a
# raw-string regex scan on the command BEFORE tokenization.  The scan looks for
# any known shell-wrapper name that is immediately preceded by a path separator
# (/ or \) — that pattern matches:
#   - POSIX absolute:  /bin/bash, /usr/bin/bash
#   - POSIX relative:  ./bash
#   - Windows:         C:\Program Files\Git\bin\bash.exe
#   - Windows UNC:     \\server\share\bash.exe
#
# When such a wrapper name is found AND a commit-producing verb appears in the
# tail of the raw command, we block with exit 2 immediately, before shlex
# tokenization has a chance to mangle the backslashes.
#
# Note: POSIX-path forms (/ separator) are also handled by the per-segment
# is_shell_wrapper() check after shlex (since POSIX shlex preserves forward
# slashes).  The raw scan here is the sole handler for backslash-path forms.
_SHELL_WRAPPER_NAMES = {
    "sh", "bash", "zsh", "dash", "ksh", "fish", "mksh", "ash",
    "busybox", "tcsh", "csh",
}


def is_shell_wrapper(token):
    """True if token names a shell wrapper (literal name or by path).

    Single source of truth: matches against _SHELL_WRAPPER_NAMES (the same set
    the raw-path pre-scan regex uses), so a new shell name added there applies
    everywhere. Used by the per-segment shell-wrapper fail-closed guard in the
    main loop.
    """
    if token in _SHELL_WRAPPER_NAMES:
        return True
    if "/" in token or "\\" in token:
        name = os.path.basename(token)
        if name.lower().endswith(".exe"):
            name = name[:-4]
        return name in _SHELL_WRAPPER_NAMES
    return False


_PATH_WRAPPER_NAMES_RE = re.compile(
    r'(?<=[/\\])(' + '|'.join(re.escape(w) for w in sorted(_SHELL_WRAPPER_NAMES)) + r')(?:\.exe)?\b',
    re.IGNORECASE,
)

# Regex that matches a path-qualified shell wrapper ONLY when it appears at
# command position — i.e. at the start of the string or immediately after a
# shell separator (; | & \n), with optional leading whitespace and optional
# env-var assignment prefixes (VAR=value) before the path.
#
# This prevents false positives where a path-qualified shell name appears as
# an ARGUMENT to another command (e.g. `echo /bin/bash I am here`).
#
# Structure:
#   (?:^|[;\n]|&&|\|\||\|)   — start-of-string OR shell separator
#   \s*                       — optional whitespace after separator
#   (?:[A-Za-z_]\w*=\S+\s+)* — zero or more VAR=value env-var prefixes
#   (?P<path>[^\s;|&]*[/\\])  — path portion ending in / or \
#   (?P<name>sh|bash|...)     — known shell wrapper name
#   (?:\.exe)?                — optional .exe suffix (Windows)
#   \b                        — word boundary
_CMD_POS_WRAPPER_RE = re.compile(
    r'(?:^|[;\n]|&&|\|\||\|)'
    r'\s*'
    r'(?:[A-Za-z_]\w*=\S+\s+)*'
    r'(?P<path>[^\s;|&]*[/\\])'
    r'(?P<name>' + '|'.join(re.escape(w) for w in sorted(_SHELL_WRAPPER_NAMES)) + r')'
    r'(?:\.exe)?\b',
    re.IGNORECASE | re.MULTILINE,
)


def _truncate_at_unquoted_separator(s):
    """Return the prefix of s up to (excluding) the first UNQUOTED shell command
    separator (; && || | & or newline). Separators inside single/double quotes
    are ignored. Used to bound a raw-string scan to a single simple command so
    a later, separate command is not misattributed to it.
    """
    in_single = False
    in_double = False
    escape = False
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if escape:
            escape = False
            i += 1
            continue
        if c == "\\" and not in_single:
            escape = True
            i += 1
            continue
        if c == "'" and not in_double:
            in_single = not in_single
            i += 1
            continue
        if c == '"' and not in_single:
            in_double = not in_double
            i += 1
            continue
        if not in_single and not in_double:
            if c == "\n" or c == ";" or c == "&" or c == "|":
                return s[:i]
        i += 1
    return s


def _check_raw_path_shell_wrappers(raw_cmd):
    """Scan raw_cmd for path-qualified shell wrapper invocations before shlex.

    Returns True and prints a FAIL message if a path-qualified shell wrapper is
    found at COMMAND POSITION alongside a git commit-producing verb in the tail.
    Returns False otherwise.

    This catches forms like:
      /bin/bash -c 'git commit'
      C:\\Program Files\\Git\\bin\\bash.exe -c 'git commit'
      .\\bash.exe -c 'git commit'
      FOO=1 C:\\path\\bash.exe -c 'git commit'
      ls; C:\\path\\bash.exe -c 'git commit'
    which shlex would mangle (backslash forms) or which need a raw pre-check.

    Command-position anchoring (F2 fix): only matches when the wrapper path
    is preceded by start-of-string, optional env-var assignments, or a shell
    separator.  This prevents false positives from commands like:
      echo /bin/bash I am here         ← /bin/bash is an arg, not executable
      echo C:\\path\\bash.exe commit   ← path is an arg, not executable

    Verb matching (F1 fix): uses _GIT_COMMIT_VERB_RE (requires "git verb"
    context) so bare words like "commit" or "am" in the tail do not trigger
    the guard.
    """
    for m in _CMD_POS_WRAPPER_RE.finditer(raw_cmd):
        wrapper_name = m.group("name")
        # Restrict the scan to the wrapper's OWN simple command: truncate at the
        # first UNQUOTED shell separator. Otherwise a separate later command,
        # e.g. `/bin/bash -c 'echo ok'; git commit -m x`, is misattributed to
        # the wrapper and false-blocked. Quote-aware so a separator INSIDE the
        # wrapper's own `-c '...; git commit'` arg is still scanned (real
        # in-argument commit → correctly fail-closed).
        tail = _truncate_at_unquoted_separator(raw_cmd[m.end():])
        if _GIT_COMMIT_VERB_RE.search(tail):
            display_token = (m.group("path") + wrapper_name).strip()
            print(
                "FAIL: cascade gate: command appears to invoke a shell wrapper "
                f"({display_token}) with a commit-producing git command in its "
                "argument. The gate cannot reliably parse nested shell strings. "
                "To commit, invoke `git` directly rather than via a shell wrapper.",
                file=sys.stderr
            )
            return True
    return False

if _check_raw_path_shell_wrappers(cmd):
    sys.exit(2)


# ---------------------------------------------------------------------------
# Main detection + dispatch loop
# ---------------------------------------------------------------------------
#
# Handle compound commands by splitting on shell separators (; && || |).
# Each segment is independently tokenized and checked.
# shlex tokenizes the full command first so separators inside quoted strings
# are never treated as split points (fixes the "a|b" class of false negatives).
#
# ALL segments are processed before exiting.  The most severe outcome across
# all segments determines the final exit code:
#   worst_exit == 0  → allow (no commit-producing segment, or all pass)
#   worst_exit == 2  → block (at least one segment fails cascade or fail-closed)
# Bypass segments (--abort / --quit / --skip) contribute nothing — they are
# neither pass nor fail, so they leave worst_exit unchanged.
worst_exit = 0

# ---------------------------------------------------------------------------
# F1: collect_pre_segment_staged_paths helper
# ---------------------------------------------------------------------------
# When a compound command like `git add <paths> && git commit -m x` is issued,
# PreToolUse fires once for the entire compound.  At the time the cascade check
# runs for the commit segment, the index is still empty — the git add has not
# executed yet.  This helper walks all segments BEFORE the commit segment and
# extracts pathspecs from staging subcommands (git add / git rm / git mv /
# git stage) so they can be unioned with the currently-staged files for the
# cascade check.
#
# Only commit segments that resolve to staged-only mode need this augmentation.
# Other modes (files, files-multi, bypass, fail-closed) use explicit file sets
# or are handled separately.
STAGING_SUBCOMMANDS = {"add", "rm", "mv", "stage"}


def _run_git_dry(git_args, cwd_override=None):
    """Run a git command in dry-run mode and return stdout as a string.

    cwd_override: when provided (from a -C <path> global option), prepend
        -C <cwd_override> to the git command so relative pathspecs in git_args
        are resolved against the correct working directory.

    Uses UTF-8 with errors='replace' to avoid codec failures on Windows when
    file paths contain non-ASCII bytes that cp1252 cannot decode.  Returns an
    empty string on any subprocess or encoding error (fail-open).
    """
    cmd = ["git"]
    if cwd_override:
        cmd.extend(["-C", cwd_override])
    cmd.extend(git_args[1:] if git_args and git_args[0] == "git" else git_args)
    try:
        r = subprocess.run(
            cmd,
            capture_output=True, timeout=5
        )
        # Decode stdout bytes directly with UTF-8, replacing any undecodable
        # bytes rather than raising.  This is safe: git outputs UTF-8 for paths
        # on all platforms; cp1252 fallback failures are avoided entirely.
        return (r.stdout or b"").decode("utf-8", errors="replace")
    except (subprocess.SubprocessError, OSError):
        return ""


def _expand_via_add_dry_run(args, cwd_override=None):
    """Run `git add --dry-run --ignore-missing <args>` and return paths it would stage.

    Handles forms like `git add .`, `git add -A`, `git add -u`, and explicit
    pathspecs.  The dry-run output reports what git would actually stage, so
    glob expansion, `-A`/`-u` semantics, and `.` expansion are all handled by
    git itself rather than by us.

    Captures both 'add' (modifications/additions) and 'remove' (deletions) lines
    because `git add -u` and `git add -A` stage deletions too, and git dry-run
    reports them as `remove 'path'`.

    cwd_override: when provided (from a -C <path> global option), passed through
        to _run_git_dry so relative pathspecs are resolved in the correct directory.

    Output format is `add 'path'` / `remove 'path'` lines (with single quotes)
    or unquoted on some platforms.  Returns empty set on any subprocess error.
    """
    stdout = _run_git_dry(["git", "add", "--dry-run", "--ignore-missing"] + args,
                          cwd_override=cwd_override)
    paths = set()
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("add "):
            prefix = "add "
        elif line.startswith("remove "):
            prefix = "remove "
        else:
            continue
        rest = line[len(prefix):].strip()
        # Strip surrounding single or double quotes if present.
        if len(rest) >= 2 and rest[0] == "'" and rest[-1] == "'":
            rest = rest[1:-1]
        elif len(rest) >= 2 and rest[0] == '"' and rest[-1] == '"':
            rest = rest[1:-1]
        if rest:
            paths.add(rest)
    return paths


def _expand_via_rm_dry_run(args, cwd_override=None):
    """Run `git rm --dry-run <args>` and return paths it would remove.

    cwd_override: when provided (from a -C <path> global option), passed through
        to _run_git_dry so relative pathspecs are resolved in the correct directory.

    Output format is `rm 'path'` lines.  Returns empty set on any subprocess
    error (fail-open; worst case: a cascade rule is not triggered for a removal
    — conservative and safe).
    """
    stdout = _run_git_dry(["git", "rm", "--dry-run"] + args,
                          cwd_override=cwd_override)
    paths = set()
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("rm "):
            continue
        rest = line[3:].strip()
        if len(rest) >= 2 and rest[0] == "'" and rest[-1] == "'":
            rest = rest[1:-1]
        elif len(rest) >= 2 and rest[0] == '"' and rest[-1] == '"':
            rest = rest[1:-1]
        if rest:
            paths.add(rest)
    return paths


def _has_no_commit_opt_out(canonical_subcmd, args):
    """True if the no-commit opt-out flags appear in args for this subcommand.

    For cherry-pick and revert, recognizes both --no-commit and the short form
    -n.  For merge, only --no-commit is recognized as an opt-out signal here
    (merge's combined --no-ff --no-commit semantics are handled by the caller
    via _merge_skips_history_change).

    Note: for `git merge`, -n means --no-stat (suppresses the diffstat) — it
    does NOT prevent the merge commit.  Only --no-commit is a valid merge
    opt-out and even then it only bypasses history when combined with --no-ff
    (handled by _merge_skips_history_change in is_commit_producing).  This
    helper is intentionally NOT called for merge; _merge_skips_history_change
    is used instead.

    Flag detection honours value-taking options via _standalone_flags(): a
    value-shaped token like `--no-commit` consumed by `-m`/`--mainline`/`-X`
    (e.g. `git cherry-pick -m --no-commit <ref>`) is NOT mistaken for the
    opt-out flag. (Same option-value class as is_commit_producing /
    _merge_skips_history_change.)
    """
    value_takers = SUBCMD_VALUE_TAKING_OPTS.get(canonical_subcmd, set())
    standalone = set(_standalone_flags(args, value_takers))
    if "--no-commit" in standalone:
        return True
    if canonical_subcmd in ("cherry-pick", "revert") and "-n" in standalone:
        return True
    return False


def _classify_cd(toks):
    """Classify an (env/wrapper-stripped) segment as a directory change.

    Returns:
      ("chdir", target)    — a `cd`/`pushd` to a literal, resolvable path.
      ("unresolvable", None) — a directory change we cannot resolve to a
                               literal path: bare `cd` (→ $HOME), `cd -`
                               (→ previous dir), `popd`, or a target requiring
                               shell expansion ($, backtick, ~, glob).
      (None, None)         — the segment is not a directory change.

    shlex(posix=True) tokenization (used upstream) does NOT expand variables,
    tilde, or globs, so a `$`/`` ` ``/`~`/`*`/`?`/`[` in the target token means
    the real shell would expand it to something we cannot predict.
    """
    if not toks:
        return (None, None)
    cmd0 = toks[0]
    if cmd0 == "popd":
        return ("unresolvable", None)
    if cmd0 not in ("cd", "pushd"):
        return (None, None)
    target = None
    i = 1
    while i < len(toks):
        t = toks[i]
        if t == "--":
            i += 1
            continue
        if t.startswith("-") and len(t) > 1:  # cd -P / -L / -e / -@
            i += 1
            continue
        target = t
        break
    if target is None or target == "-":
        return ("unresolvable", None)
    if any(ch in target for ch in ("$", "`", "~", "*", "?", "[")):
        return ("unresolvable", None)
    return ("chdir", target)


def _compose_cwd(base, override):
    """Compose a seg-local cwd override onto a running cwd.

    override None  → base unchanged.
    override abs   → override (an absolute path replaces the running cwd).
    base None      → override (running cwd is the hook's cwd / repo root).
    otherwise      → base/override.
    """
    if not override:
        return base
    if os.path.isabs(override):
        return override
    if not base:
        return override
    return os.path.join(base, override)


def _split_parens(toks):
    """Return (n_open, n_close, middle) where n_open is the count of leading `(`
    tokens, n_close the count of trailing `)` tokens, and middle the remaining
    inner tokens. Used to track subshell scope: a `cd` inside `( ... )` must not
    leak to commands after the subshell closes.
    """
    n = len(toks)
    n_open = 0
    while n_open < n and toks[n_open] == "(":
        n_open += 1
    n_close = 0
    while n_close < (n - n_open) and toks[n - 1 - n_close] == ")":
        n_close += 1
    middle = toks[n_open: n - n_close] if n_close else toks[n_open:]
    return n_open, n_close, middle


def _apply_cd_segment(stack, toks):
    """Update the cwd STACK for one prior segment's `cd`/subshell effects.

    stack is a list of (cwd, unknown) frames; stack[-1] is the current shell.
    Leading `(` push a child frame (subshell inherits cwd); trailing `)` pop it
    (cwd reverts — so a `cd` inside a closed subshell does not persist). A `cd`
    in the middle updates the current (top) frame only.
    """
    n_open, n_close, mid = _split_parens(list(toks))
    for _ in range(n_open):
        stack.append(stack[-1])  # enter subshell, inherit parent cwd
    # Strip env-var assignments and simple wrapping prefixes so `cd` reached via
    # `command cd` / `builtin cd` is still seen. `env` cannot exec the shell
    # builtin `cd`, so it is not handled here.
    while mid:
        t0 = mid[0]
        if ENV_VAR_ASSIGN.match(t0):
            mid = mid[1:]
            continue
        if t0 in ("command", "builtin", "exec"):
            mid = mid[1:]
            continue
        break
    cd_kind, cd_target = _classify_cd(mid)
    if cd_kind == "chdir":
        cwd, unknown = stack[-1]
        if os.path.isabs(cd_target):
            stack[-1] = (cd_target, False)
        elif not unknown:
            stack[-1] = (_compose_cwd(cwd, cd_target), False)
        # relative cd onto an already-unknown cwd → stays unknown
    elif cd_kind == "unresolvable":
        cwd, _unk = stack[-1]
        stack[-1] = (cwd, True)
    for _ in range(n_close):
        if len(stack) > 1:
            stack.pop()  # exit subshell, cwd reverts to the parent frame


def _running_cwd_before(all_segs, current_idx):
    """Return (running_cwd, cwd_unknown) — the shell cwd that applies AT segment
    current_idx, given bare `cd`/`pushd`/`popd` changes in the prior segments.

    Subshell-aware: a `cd` inside a `( ... )` that has already CLOSED before
    current_idx does not affect the result (Bash runs subshells in a child
    process; their cwd does not persist). A `cd` inside a subshell that is still
    open at current_idx (e.g. `(cd sub && git commit ...)`) does apply. Used to
    resolve the COMMIT segment's own pathspecs (e.g. `cd sub && git commit file`).

    running_cwd is None for the repo root; cwd_unknown is True when the
    applicable cwd was set by an unresolvable cd.
    """
    stack = [(None, False)]  # frame stack; [-1] is the current shell scope
    for prior in all_segs[:current_idx]:
        if not prior:
            continue
        _apply_cd_segment(stack, prior)
    return stack[-1]


def collect_pre_segment_staged_paths(all_segs, current_idx):
    """Walk segments before current_idx; return (pathspecs, cwd_unresolvable).

    `pathspecs` is the set of paths that prior staging commands will place into
    the index. `cwd_unresolvable` is True when a path-based staging command
    (`git add`/`rm`/`mv`/`stage`) runs in a working directory the gate cannot
    determine — i.e. a prior `cd`/`pushd`/`popd` that resolves to no literal
    path (bare cd, cd -, popd, or a shell-expanded target). The caller fails
    closed in that case, because it cannot preflight which paths will be staged.

    Handles:
      - git add / git stage    → git add --dry-run expansion
      - git rm                 → git rm --dry-run expansion
      - git mv                 → conservative positional collection
      - git cherry-pick -n / --no-commit <ref>
                               → files_for_show(refs) union
      - git revert -n / --no-commit <ref>
                               → files_for_show(refs) union
      - git merge --squash <branch>
        git merge --no-ff --no-commit <branch>
                               → files_for_diff_range("HEAD...<branch>") union

    Applies the same env-var-stripping and wrapping-prefix-stripping logic as
    the main loop so that forms like `env VAR=val git add foo` are handled.

    For `git add` and `git stage`, uses `git add --dry-run --ignore-missing`
    to expand the actual pathspecs git would stage, handling `.`, `-A`, `-u`,
    globs, and explicit paths uniformly.

    For `git rm`, uses `git rm --dry-run` for similar expansion.

    For `git mv`, falls back to collecting non-option positional args (both
    source and destination) as candidate paths; `git mv` is rarely used in
    staging-then-commit flows so the conservative approach is acceptable.

    For cherry-pick/revert no-commit forms, uses files_for_show() to collect
    the files the operation will stage without committing.

    For merge --squash and merge --no-ff --no-commit, uses
    files_for_diff_range() to collect the files in the diff between HEAD and
    the merge target branch.

    Returns (paths, cwd_unresolvable).
    """
    # Subcommands handled by the existing index-staging logic.
    _INDEX_STAGING_SUBCMDS = {"add", "rm", "mv", "stage"}
    # Subcommands that can stage without committing when no-commit opt-outs are
    # present.  These are handled by the new no-commit introspection path.
    _NO_COMMIT_SUBCMDS = {"cherry-pick", "revert", "merge"}

    paths = set()
    # staging_unresolvable records that a path-based staging command ran in a
    # working directory the gate cannot determine (a prior unresolvable `cd`).
    # The cwd that applies AT each staging segment is computed subshell-aware by
    # _running_cwd_before(all_segs, idx): a `cd` inside a CLOSED subshell does
    # not leak to later commands.
    staging_unresolvable = False
    for idx, prior in enumerate(all_segs[:current_idx]):
        if not prior:
            continue
        # Strip subshell grouping so `(git add x)` is detected as a staging
        # command; the cwd scoping of any `cd` inside the subshell is handled by
        # _running_cwd_before, not here.
        _open_parens, _close_parens, toks = _split_parens(list(prior))
        if not toks:
            continue
        # Strip env-var assignments and wrapping prefixes (mirrors main loop).
        _env_vt_short = {"-u", "-C", "-S", "-a"}
        _env_vt_long = {"--unset", "--chdir", "--split-string", "--argv0"}
        # Capture env -C / --chdir value for this prior segment.
        _seg_env_cwd = None
        while toks:
            t0 = toks[0]
            if ENV_VAR_ASSIGN.match(t0):
                toks = toks[1:]
                continue
            if t0 in WRAPPING_PREFIXES:
                toks = toks[1:]
                if t0 == "env":
                    while toks:
                        e = toks[0]
                        if e == "--":
                            toks = toks[1:]
                            break
                        if e.startswith("--") and "=" in e:
                            # Capture --chdir=<dir> (= form).
                            if e.startswith("--chdir="):
                                new_cwd = e[len("--chdir="):]
                                if new_cwd:
                                    if os.path.isabs(new_cwd) or _seg_env_cwd is None:
                                        _seg_env_cwd = new_cwd
                                    else:
                                        _seg_env_cwd = os.path.join(_seg_env_cwd, new_cwd)
                            toks = toks[1:]
                            continue
                        if e in _env_vt_long and len(toks) >= 2:
                            # Capture --chdir <dir> (space form).
                            if e == "--chdir":
                                new_cwd = toks[1]
                                if os.path.isabs(new_cwd) or _seg_env_cwd is None:
                                    _seg_env_cwd = new_cwd
                                else:
                                    _seg_env_cwd = os.path.join(_seg_env_cwd, new_cwd)
                            toks = toks[2:]
                            continue
                        if e.startswith("--"):
                            toks = toks[1:]
                            continue
                        if e in _env_vt_short and len(toks) >= 2:
                            # Capture -C <dir> (space form).
                            if e == "-C":
                                new_cwd = toks[1]
                                if os.path.isabs(new_cwd) or _seg_env_cwd is None:
                                    _seg_env_cwd = new_cwd
                                else:
                                    _seg_env_cwd = os.path.join(_seg_env_cwd, new_cwd)
                            toks = toks[2:]
                            continue
                        if e.startswith("-") and len(e) > 1:
                            toks = toks[1:]
                            continue
                        break
                continue
            break
        if not toks:
            continue
        # `cd`/`pushd`/`popd` segments change the shell cwd but stage nothing.
        # Their cwd effect is subshell-scoped and accounted for by
        # _running_cwd_before below, so skip them here.
        cd_kind, _cd_target = _classify_cd(toks)
        if cd_kind is not None:
            continue
        if not is_git_executable(toks[0]):
            continue
        # The shell cwd that applies AT this staging segment, honouring prior
        # `cd`s and subshell scope (a `cd` in a closed subshell does not leak).
        running_cwd, cwd_unknown = _running_cwd_before(all_segs, idx)
        # Walk past global git options to find the subcommand, capturing -C value.
        verb_idx, _seg_git_cwd = _skip_global_git_opts_with_capture(toks[1:])
        # Compose env's chdir with git's -C (same precedence as the main loop).
        if _seg_env_cwd and _seg_git_cwd:
            if os.path.isabs(_seg_git_cwd):
                seg_cwd_override = _seg_git_cwd
            else:
                seg_cwd_override = os.path.join(_seg_env_cwd, _seg_git_cwd)
        elif _seg_env_cwd:
            seg_cwd_override = _seg_env_cwd
        elif _seg_git_cwd:
            seg_cwd_override = _seg_git_cwd
        else:
            seg_cwd_override = None
        # Fold the running shell cwd (from prior `cd`) underneath the seg-local
        # override: an absolute -C/--chdir wins; otherwise it is relative to the
        # running cwd. For the common no-`cd` case running_cwd is None and this
        # is a no-op.
        seg_cwd_override = _compose_cwd(running_cwd, seg_cwd_override)
        subcmd_pos = verb_idx + 1
        if subcmd_pos >= len(toks):
            continue
        subcmd = toks[subcmd_pos]
        # All tokens after the subcommand (options + pathspecs together).
        args = toks[subcmd_pos + 1:]

        if subcmd in _INDEX_STAGING_SUBCMDS:
            # If a prior unresolvable `cd` left the shell cwd unknown and this
            # staging command has no absolute override of its own, we cannot
            # determine which paths it will stage — signal fail-closed.
            if cwd_unknown and not (seg_cwd_override and os.path.isabs(seg_cwd_override)):
                staging_unresolvable = True
                continue
            if subcmd in ("add", "stage"):
                # Use git's own dry-run to expand pathspecs (handles `.`, `-A`,
                # `-u`, globs, and explicit paths uniformly).  Thread seg_cwd_override
                # so that relative pathspecs in `-C <dir> add <path>` forms are
                # resolved against the correct working directory.
                expanded = _expand_via_add_dry_run(args, cwd_override=seg_cwd_override)
                paths.update(expanded)
            elif subcmd == "rm":
                expanded = _expand_via_rm_dry_run(args, cwd_override=seg_cwd_override)
                paths.update(expanded)
            elif subcmd == "mv":
                # `git mv -n` (dry-run) is supported but rarely used in
                # staging-then-commit flows.  Conservative fallback: collect all
                # non-option positional args (source + destination) as candidates.
                for a in args:
                    if not a.startswith("-"):
                        paths.add(a)
            continue

        if subcmd == "cherry-pick":
            # Only collect files for cherry-pick that stages without committing.
            if not _has_no_commit_opt_out("cherry-pick", args):
                continue
            refs = extract_positionals("cherry-pick", args)
            if not refs:
                continue
            mainline = _extract_mainline_opt(args)
            files = files_for_show(refs, mainline=mainline)
            if files:
                paths.update(files)
            continue

        if subcmd == "revert":
            # Only collect files for revert that stages without committing.
            if not _has_no_commit_opt_out("revert", args):
                continue
            refs = extract_positionals("revert", args)
            if not refs:
                continue
            mainline = _extract_mainline_opt(args)
            files = files_for_show(refs, mainline=mainline)
            if files:
                paths.update(files)
            continue

        if subcmd == "merge":
            # Only collect files for merge forms that stage without committing
            # (--squash or --no-ff --no-commit).  The _merge_skips_history_change
            # check is the canonical authority for these forms.
            if not _merge_skips_history_change(args):
                continue
            branches = extract_positionals("merge", args)
            if not branches:
                continue
            for branch in branches:
                files = files_for_diff_range(f"HEAD...{branch}")
                if files:
                    paths.update(files)
            continue

    return paths, staging_unresolvable


# Collect all segments up front so each segment knows its index (needed for
# collect_pre_segment_staged_paths and _running_cwd_before). Subshell grouping
# tokens are PRESERVED here so the cwd trackers can scope `cd` inside `( ... )`
# to the subshell; the main loop strips them locally (below) for git detection.
all_segments = list(shell_segments(cmd))

for seg_idx, toks in enumerate(all_segments):
    # Strip subshell grouping for THIS segment's git detection so `(git commit
    # -m x)` is recognised. This is a local rebind; all_segments keeps the
    # parens so the cwd trackers see subshell boundaries.
    toks = _strip_subshell_grouping(toks)
    if not toks:
        continue
    # Strip leading env-var assignments AND wrapping prefixes (command, builtin,
    # exec, env) in a single unified loop.  The loop merges both passes so that
    # interleaved forms like `env VAR=val command git commit` are handled correctly.
    #
    # When `env` is stripped, its own option flags are consumed inline.
    # Per `env --help` the full flag set is:
    #
    # Value-taking short flags (consume 2 tokens: flag + value):
    #   -u <VAR>   --unset <VAR>         : unset a variable
    #   -C <dir>   --chdir <dir>         : change directory
    #   -S <str>   --split-string <str>  : split string into args
    #   -a <name>  --argv0 <name>        : override argv[0]
    #
    # Value-less short flags (consume 1 token):
    #   -i   --ignore-environment   : clear the environment
    #   -0   --null                 : NUL-delimited output
    #   -v   --debug                : debug output
    #        --list-signal-handling : informational only
    #
    # Long flags with attached =value (single token, e.g. --block-signal=SIGTERM):
    #   --block-signal=<sig>, --default-signal=<sig>, --ignore-signal=<sig>, etc.
    #
    # End-of-options marker: -- terminates env flag processing; whatever follows
    # is the command to run.
    #
    # VAR=val tokens that follow env are handled by the ENV_VAR_ASSIGN branch
    # (they are syntactically identical to bare shell env-var prefixes).
    ENV_VALUE_TAKING_SHORT = {"-u", "-C", "-S", "-a"}
    ENV_VALUE_TAKING_LONG = {"--unset", "--chdir", "--split-string", "--argv0"}
    # env_cwd accumulates the working-directory change imposed by env -C / --chdir.
    # It is composed with git's own -C value (cwd_override) after env stripping.
    env_cwd = None
    while toks:
        t = toks[0]
        if ENV_VAR_ASSIGN.match(t):
            toks = toks[1:]
            continue
        if t in WRAPPING_PREFIXES:
            toks = toks[1:]
            if t == "env":
                # Consume env-specific option flags before continuing.
                while toks:
                    e = toks[0]
                    # End-of-options marker: consume and stop env-flag processing.
                    if e == "--":
                        toks = toks[1:]
                        break
                    # --opt=value forms (single token; covers --block-signal=SIG etc.)
                    if e.startswith("--") and "=" in e:
                        # F2: --split-string=<script> — check the embedded string
                        # for a git commit-producing verb before skipping.
                        if e.startswith("--split-string="):
                            script_arg = e[len("--split-string="):]
                            if _GIT_COMMIT_VERB_RE.search(script_arg):
                                print(
                                    "FAIL: cascade gate: env --split-string='<script>' "
                                    "contains a commit-producing git invocation. "
                                    "The gate cannot reliably parse nested shell strings. "
                                    "Invoke git directly rather than via env --split-string.",
                                    file=sys.stderr
                                )
                                worst_exit = max(worst_exit, 2)
                                toks = toks[1:]
                                break
                        # Capture --chdir=<dir> (= form): compose with any prior env_cwd.
                        if e.startswith("--chdir="):
                            new_cwd = e[len("--chdir="):]
                            if new_cwd:
                                if os.path.isabs(new_cwd) or env_cwd is None:
                                    env_cwd = new_cwd
                                else:
                                    env_cwd = os.path.join(env_cwd, new_cwd)
                        toks = toks[1:]
                        continue
                    # Value-taking long flags in space form.
                    if e in ENV_VALUE_TAKING_LONG and len(toks) >= 2:
                        # F2: --split-string <script> (space-separated form) — check
                        # the next token for a git commit-producing verb.
                        if e == "--split-string":
                            script_arg = toks[1]
                            if _GIT_COMMIT_VERB_RE.search(script_arg):
                                print(
                                    "FAIL: cascade gate: env --split-string '<script>' "
                                    "contains a commit-producing git invocation. "
                                    "The gate cannot reliably parse nested shell strings. "
                                    "Invoke git directly rather than via env --split-string.",
                                    file=sys.stderr
                                )
                                worst_exit = max(worst_exit, 2)
                                toks = toks[2:]
                                break
                        # Capture --chdir <dir> (space form): compose with any prior env_cwd.
                        if e == "--chdir":
                            new_cwd = toks[1]
                            if os.path.isabs(new_cwd) or env_cwd is None:
                                env_cwd = new_cwd
                            else:
                                env_cwd = os.path.join(env_cwd, new_cwd)
                        toks = toks[2:]
                        continue
                    # Value-less long flags (--ignore-environment, --null, --debug, etc.)
                    if e.startswith("--"):
                        toks = toks[1:]
                        continue
                    # Value-taking short flags in space form.
                    if e in ENV_VALUE_TAKING_SHORT and len(toks) >= 2:
                        # F2: -S <script> — check the next token for a git commit verb.
                        if e == "-S":
                            script_arg = toks[1]
                            if _GIT_COMMIT_VERB_RE.search(script_arg):
                                print(
                                    "FAIL: cascade gate: env -S '<script>' contains a "
                                    "commit-producing git invocation. The gate cannot "
                                    "reliably parse nested shell strings. Invoke git "
                                    "directly rather than via env -S.",
                                    file=sys.stderr
                                )
                                worst_exit = max(worst_exit, 2)
                                toks = toks[2:]
                                break
                        # Capture -C <dir>: compose with any prior env_cwd.
                        if e == "-C":
                            new_cwd = toks[1]
                            if os.path.isabs(new_cwd) or env_cwd is None:
                                env_cwd = new_cwd
                            else:
                                env_cwd = os.path.join(env_cwd, new_cwd)
                        toks = toks[2:]
                        continue
                    # Other short flags (value-less): -i, -0, -v and any unknown.
                    if e.startswith("-") and len(e) > 1:
                        toks = toks[1:]
                        continue
                    # Non-option token: actual command to run — stop env-flag processing.
                    break
            continue
        break
    if not toks:
        continue

    # F1: substitution-as-executable detection (fail-closed, per-segment).
    # Only block when the first token signals a shell substitution used AS the
    # executable (not as an argument to a real command).
    #
    # shlex with punctuation_chars=True tokenizes $(which git) into the tokens
    # ['$', '(', 'which', 'git', ')'], so a '$( substitution-as-executable is
    # detected by toks[0]=='$' and toks[1]=='('.  Backtick forms like
    # `which git` produce toks[0] starting with a backtick.
    #
    # By contrast, argument-position substitutions in non-git commands look like:
    #   echo "$(date) commit"   → toks[0]='echo'  (first token is 'echo')
    #   cat "$(script)" ...     → toks[0]='cat'   (first token is 'cat')
    #   echo $(date) ok         → toks[0]='echo'  (first token is 'echo', then '$')
    # Those are not affected because their first token is the real command name.
    #
    # We detect substitution-as-executable and, when a commit-producing verb
    # also appears anywhere in the segment, block with exit 2 (fail-closed).
    # We do NOT exit immediately; instead we record worst_exit=2 and continue
    # processing remaining segments so the full compound command is evaluated.
    first_token = toks[0]
    _is_substitution_executable = (
        # $(...) form: shlex splits to ['$', '(', ...]
        (first_token == "$" and len(toks) > 1 and toks[1] == "(")
        # backtick form: first token starts with backtick (e.g. '`which')
        or first_token.startswith("`")
    )
    if _is_substitution_executable:
        # The executable is a substitution result — check if a commit verb
        # appears anywhere in this segment's remaining tokens.
        segment_tail = " ".join(toks[1:])
        if _COMMIT_VERB_RE.search(segment_tail):
            print(
                "FAIL: cascade gate: command appears to invoke git via "
                "shell substitution combined with a commit-producing verb. "
                "The gate cannot reliably determine what executable will "
                "run. To commit, use a literal `git` invocation.",
                file=sys.stderr
            )
            worst_exit = 2
        # Substitution-as-executable but no commit verb in remainder: not our concern.
        continue

    # F1: shell-wrapper fail-closed.
    # If the first token is a known shell interpreter (sh, bash, zsh, etc.) AND
    # any later token contains a commit-producing verb keyword, the gate cannot
    # safely parse the nested shell string.  Block with exit 2 rather than risk
    # silently allowing a commit that bypasses cascade enforcement.
    #
    # Shell wrappers WITHOUT a commit verb in their arguments (e.g. `bash -c
    # "echo hello"`) pass through — they are clearly not commit-producing.
    #
    # This check is placed AFTER the substitution-as-executable guard so that
    # substitution forms are caught first, and BEFORE is_git_executable() so
    # we never fall through to the git detection path for shell-wrapped invocations.
    # is_shell_wrapper() / _SHELL_WRAPPER_NAMES are defined at module level
    # (single source of truth, shared with the raw-path pre-scan).
    if is_shell_wrapper(first_token):
        # Join the remaining tokens so that a split "git" + "commit" pair —
        # which shlex produces from e.g. `bash -c 'git commit'` — is seen as
        # the phrase "git commit" and matched by _GIT_COMMIT_VERB_RE.  Using
        # the contextual pattern (requires "git verb") avoids false positives
        # from bare words like "am" or "commit" in non-git arguments.
        joined_tail = " ".join(toks[1:])
        if _GIT_COMMIT_VERB_RE.search(joined_tail):
            print(
                "FAIL: cascade gate: command appears to invoke a shell wrapper "
                f"({first_token}) with a commit-producing git command in its "
                "argument. The gate cannot reliably parse nested shell strings. "
                "To commit, invoke `git` directly rather than via a shell wrapper.",
                file=sys.stderr
            )
            worst_exit = max(worst_exit, 2)
        continue

    # F1: recognize git by basename so absolute or relative paths like
    # /usr/bin/git or ./bin/git are detected, not just the literal "git".
    if not is_git_executable(toks[0]):
        continue
    # Walk past global options until we find the subcommand, capturing -C value.
    # toks[0] is the git executable itself; pass toks[1:] to the walker and
    # adjust the returned index back by adding 1 (for toks[0]).
    _verb_idx, git_cwd_override = _skip_global_git_opts_with_capture(toks[1:])
    # Compose env's chdir (env_cwd) with git's -C (git_cwd_override).
    # Precedence rules:
    #   - env's chdir happens FIRST (changes the process working directory
    #     before git is invoked).
    #   - git's -C is then applied relative to the already-changed directory,
    #     UNLESS git's -C is an absolute path, which replaces env's chdir.
    if env_cwd and git_cwd_override:
        if os.path.isabs(git_cwd_override):
            # git -C with absolute path replaces env's chdir entirely.
            cwd_override = git_cwd_override
        else:
            # git -C is relative to env's chdir.
            cwd_override = os.path.join(env_cwd, git_cwd_override)
    elif env_cwd:
        cwd_override = env_cwd
    elif git_cwd_override:
        cwd_override = git_cwd_override
    else:
        cwd_override = None
    i = _verb_idx + 1  # adjust to index into original toks list
    while i < len(toks):
        t = toks[i]
        # Non-option token: this is the subcommand position.
        # Check whether it (or an alias it resolves to) produces a commit.
        resolve_result = _resolve_subcmd(t)
        if resolve_result is None:
            break  # Not commit-producing — stop
        canonical, expansion_args, is_shell = resolve_result
        remaining_toks = toks[i + 1:]
        # Prepend alias-injected flags so that -a, --pathspec-from-file, etc.
        # embedded in the alias definition are visible to files_for_commit()
        # and determine_check_target().  User-supplied args follow the alias args.
        effective_args = expansion_args + remaining_toks
        # Check opt-out flags before deciding on check mode
        if not is_commit_producing(t, effective_args):
            break  # Opted out with --no-commit/-n — stop

        # Fold any prior bare `cd`/`pushd` directory change into this commit
        # segment's cwd so that pathspec commits (e.g. `cd sub && git commit
        # file -m x`) resolve their paths against the right directory. The
        # commit segment's own env --chdir / git -C (cwd_override) applies on
        # top; an absolute override wins. cwd_unknown_before signals a prior
        # unresolvable cd so files_for_commit can fail closed on pathspecs.
        running_before, cwd_unknown_before = _running_cwd_before(all_segments, seg_idx)
        commit_cwd_override = _compose_cwd(running_before, cwd_override)

        # Determine the check mode and target file list for this subcommand
        if is_shell:
            # Shell alias — opaque, cannot pre-flight; use staged-only
            mode, files = "staged-only", None
        else:
            mode, files = determine_check_target(
                canonical, effective_args,
                cwd_override=commit_cwd_override, cwd_unknown=cwd_unknown_before,
            )

        # Recovery flags (--abort / --quit / --skip) bypass the gate entirely.
        # These paths never write commits, so blocking them would deadlock the
        # developer's workflow when a cascade-violating file is staged.
        # Do NOT set worst_exit — bypass segments are neutral.
        if mode == "bypass":
            break

        # Fail-closed: the gate cannot determine what will be committed
        # (e.g. stdin pathspec, unreadable pathspec file, shell substitution).
        # The diagnostic was already printed by the function that returned this
        # mode.  Record the failure and continue to the next segment.
        if mode == "fail-closed":
            worst_exit = 2
            break

        # Invoke check-cascade.sh — Python is the single invocation point.
        # Use the bash and check-cascade.sh paths exported by the outer bash
        # wrapper (_GATE_BASH, _CHECK_CASCADE_SCRIPT) so that path-style
        # differences between MSYS bash and any other bash in PATH are avoided.
        check_script = os.environ.get("_CHECK_CASCADE_SCRIPT")
        gate_bash = os.environ.get("_GATE_BASH", "bash")
        if not check_script:
            # Env vars not set — bail conservatively (fail-open); do not block
            break
        if mode == "files-multi":
            # Per-commit cascade check: each commit's file set is checked
            # independently.  Block on the FIRST violating commit so that the
            # violation is attributed to the correct commit in the sequence.
            # An empty inner list means the commit touched no tracked files;
            # skip it (nothing to cascade-check).
            total = len(files)
            seg_rc = 0
            for idx, file_set in enumerate(files):
                if not file_set:
                    continue
                result = subprocess.run(
                    [gate_bash, check_script, "--files"] + file_set
                )
                if result.returncode != 0:
                    print(
                        f"(cascade violation in commit #{idx + 1} of {total})",
                        file=sys.stderr
                    )
                    seg_rc = result.returncode
                    break
            if seg_rc > worst_exit:
                worst_exit = seg_rc
        elif mode == "files":
            if not files:
                # Empty file list = nothing to check; treat as pass
                pass
            else:
                result = subprocess.run([gate_bash, check_script, "--files"] + files)
                if result.returncode > worst_exit:
                    worst_exit = result.returncode
        else:  # staged-only
            # F1: augment the staged-only check with paths that EARLIER segments
            # in the same compound command will stage (e.g. `git add foo && git
            # commit -m x`).  At PreToolUse time those files are not yet in the
            # index, so a plain --staged-only check would miss them.  We union
            # the currently-staged set with any paths collected from prior
            # git add/rm/mv/stage segments and pass the combined list via
            # --files mode so check-cascade.sh evaluates the full set.
            #
            # This augmentation only applies to staged-only mode (the default
            # `git commit` case).  Other modes (files, files-multi, bypass,
            # fail-closed) have their own file sets or are handled separately.
            extra_paths, cwd_unresolvable = collect_pre_segment_staged_paths(all_segments, seg_idx)
            if cwd_unresolvable:
                # A prior `cd`/`pushd`/`popd` to a directory we cannot resolve
                # (bare cd, cd -, popd, or a shell-expanded target) precedes a
                # path-based staging command, so we cannot determine which paths
                # the commit will land. Fail closed rather than risk a bypass.
                print(
                    "FAIL: cascade gate: a `cd`/`pushd`/`popd` to an unresolvable "
                    "directory precedes a staging command in this compound, so the "
                    "gate cannot determine which paths will be committed. Run the "
                    "staging and commit as separate commands, or use `git -C <dir>` "
                    "instead of `cd`.",
                    file=sys.stderr,
                )
                worst_exit = 2
                break
            if extra_paths:
                # Get currently staged files.
                try:
                    _staged_r = subprocess.run(
                        ["git", "diff", "--cached", "--name-only", "--no-renames"],
                        capture_output=True, text=True, timeout=5
                    )
                    current_staged = set(
                        line.strip()
                        for line in _staged_r.stdout.splitlines()
                        if line.strip()
                    ) if _staged_r.returncode == 0 else set()
                except (subprocess.SubprocessError, OSError):
                    current_staged = set()
                combined = current_staged | extra_paths
                if combined:
                    result = subprocess.run(
                        [gate_bash, check_script, "--files"] + sorted(combined)
                    )
                else:
                    result = subprocess.run([gate_bash, check_script, "--staged-only"])
            else:
                result = subprocess.run([gate_bash, check_script, "--staged-only"])
            if result.returncode > worst_exit:
                worst_exit = result.returncode
        break  # finished processing this segment's subcommand

# Not a commit-producing command (or all segments processed) — use accumulated result
sys.exit(worst_exit)
PYEOF
exit $?
