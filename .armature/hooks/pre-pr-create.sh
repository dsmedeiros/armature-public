#!/usr/bin/env bash
# Armature PreToolUse(Bash) hook — pre-pr-create red-team enforcement.
#
# Event: PreToolUse with matcher "Bash" — fires before every Bash tool
# invocation. Inspects the command; no-ops unless the command is a
# `gh pr create` invocation. When it is, runs the red-team trigger check
# (shared module .armature/hooks/lib/red_team_check.py — same logic as
# auto-reviewer.sh) and either:
#   - exits 0 (allow) when not triggered OR marker is valid
#   - exits 2 (BLOCK) when triggered AND marker missing/stale AND
#     ARMATURE_RED_TEAM_ENFORCE truthy (1/true/yes/on, case-insensitive)
#   - exits 0 (ADVISORY only, stderr warning) when triggered AND marker
#     missing/stale AND ARMATURE_RED_TEAM_ENFORCE is unset (soft-deploy)
#
# Default mode is ADVISORY. Operators opt into blocking by setting
# ARMATURE_RED_TEAM_ENFORCE=true in their shell profile or per-invocation
# environment.
#
# Cross-platform: bash + Git Bash (Windows) compatible.
#
# Stdin: JSON object with top-level "tool_input.command" string.
# Exit codes:
#   0 = allow the tool call (or advisory-only when soft-deploy)
#   2 = BLOCK the tool call (Claude Code semantic for PreToolUse blocks)
#
# Security:
#   - L001 NUL-byte rejection: bash command substitution silently strips
#     NUL bytes, masking pattern-match bypass. Reject any payload with NUL.
#     Fail-CLOSED (exit 2 — BLOCK) on NUL since we cannot reliably extract
#     the command. Matches block-dangerous-commands.sh L001 contract.
#   - Module-unavailable fail-CLOSED under enforce (red-team bypass fix):
#     if a detected gh pr create cannot be evaluated (red_team_check.py
#     import fails OR evaluate_red_team raises) AND ARMATURE_RED_TEAM_ENFORCE
#     is set, the hook exits 2 (BLOCK) with a structured BLOCK message.
#     In advisory mode (enforce unset) the hook stays fail-open so operators
#     are not blocked by infrastructure breakage when they have not opted in.
#     Only post-detection evaluation failures fail closed; stdin-read-failure
#     and JSON-parse-failure happen before detection so they stay fail-open
#     (blocking arbitrary/unknown bash commands is disproportionate).
#   - No Python interpreter: hook emits a stderr advisory and exits 0
#     (fail-open). Without Python the hook cannot even detect the command;
#     blocking all bash is disproportionate. Residual: under ENFORCE with no
#     Python, a gh pr create bypass is possible. Mitigation: ensure Python is
#     present in enforced environments (the hook will not evaluate otherwise).
#
# Observability:
#   Every triggered-without-marker block emits a structured stderr block:
#       BLOCK [GATE-RED-TEAM-001]: <reasons>
#       Missing/stale: <marker_status>
#       To bypass: ...
#   Soft-deploy (advisory) emits the same shape with ADVISORY instead of
#   BLOCK so operators can tail their hook logs and see what would have
#   blocked under enforcement.
#   Evaluation failure under enforce emits:
#       BLOCK [GATE-RED-TEAM-001]: cannot evaluate red-team gate (<reason>);
#         failing closed under ARMATURE_RED_TEAM_ENFORCE
#
# Fail-open on unresolvable base ref (carry-forward from CP1 red team):
#   evaluate_red_team's git-derived triggers (LOC + component count) require
#   a resolvable base ref (main / origin/main / master / origin/master).
#   When the base ref is unresolvable (shallow clone, unusual branching),
#   _detect_base_ref returns '' and the LOC + component heuristics silently
#   skip — evaluate_red_team returns triggered=False for those dimensions.
#   This is FAIL-OPEN for those two triggers only: a large multi-component
#   PR on an unusual base would not be caught by LOC/component heuristics.
#   HOWEVER: keyword/severity/FORCE_RED_TEAM/pending-advisory triggers still
#   fire regardless of base ref; only the git-diff-derived heuristics are
#   affected. In advisory-default mode (ARMATURE_RED_TEAM_ENFORCE unset),
#   this is acceptable — process discipline, not a security gate. In enforce
#   mode, operators should ensure main/master is locally tracked.
#   TODO: CP5 may add a registry note for HOOK-007 on this limitation.

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve REPO_ROOT cwd-INDEPENDENTLY (codex P1 enforcement-bypass fix).
#
# WHY cwd-derivation is unsafe: when the hook fires for a command like
#   env -C /other/path gh pr create
# or
#   cd /other/path && gh pr create
# the Claude Code harness may invoke this hook while the bash cwd is NOT
# inside this project. `git rev-parse --show-toplevel` then runs in the
# wrong directory, returns an unrelated repo root (or falls back to the
# external pwd), and `sys.path.insert(REPO_ROOT/.armature/hooks/lib)`
# resolves to a non-existent path. The subsequent ImportError is caught by
# the evaluation-failure fail-closed branch → under ARMATURE_RED_TEAM_ENFORCE
# the hook exits 2 (BLOCK) for detected gh-pr-create commands.
#
# Resolution precedence (pick first candidate where lib sanity check passes):
#   1. CLAUDE_PROJECT_DIR if set, non-empty, and the lib exists there.
#      Claude Code sets this to the project root; it is the preferred
#      cwd-independent source. However, CLAUDE_PROJECT_DIR can be wrong or
#      stale (e.g. a different project was open previously). The lib sanity
#      check (.armature/hooks/lib/red_team_check.py must exist) ensures we
#      only accept it when it points at a real Armature root, and fall through
#      to Candidate 2 when it does not.
#   2. Canonicalized path two directories up from the hook's own install
#      location (BASH_SOURCE). The hook lives at
#      <root>/.armature/hooks/pre-pr-create.sh, so
#      dirname(dirname(dirname(hook))) == <root>. BASH_SOURCE[0] is the
#      symlink path (not the target) when the hook is symlinked; canonicalize
#      via `readlink -f` (GNU) with a raw-path fallback (macOS/BSD where
#      readlink -f is unavailable) before deriving the root. A lib sanity
#      check guards against false positives when BASH_SOURCE resolves
#      unexpectedly (e.g. the hook is not installed at the expected depth).
#   3. Last-resort: git rev-parse --show-toplevel || pwd (original behaviour,
#      retained only when both preferred methods fail). Cwd-dependent; used
#      only as a last resort.
#
# When resolution fails (no candidate passes the lib sanity check), the Python
# core tries the last-resort path anyway. If the lib is still not found and the
# command IS a detected gh-pr-create under ARMATURE_RED_TEAM_ENFORCE, the hook
# exits 2 (fail-closed). In advisory mode it exits 0 (fail-open preserved).
#
# Documented limitation: a command that cd's into a DIFFERENT Armature repo
# is governed by THAT repo's own hook, not this one. The fix only ensures
# REPO_ROOT is THIS hook's project regardless of the operator's shell cwd.
# ---------------------------------------------------------------------------
_REPO_ROOT_RESOLVED=""

# Candidate 1: CLAUDE_PROJECT_DIR — only accept if lib sanity check passes.
# CLAUDE_PROJECT_DIR can be wrong/stale (a different project root). The lib
# check ensures we fall through to Candidate 2 when it does not point at a
# real Armature root, avoiding over-blocking when Candidate 2 can resolve.
if [ -n "${CLAUDE_PROJECT_DIR:-}" ] && [ -d "${CLAUDE_PROJECT_DIR}" ] \
   && [ -f "${CLAUDE_PROJECT_DIR}/.armature/hooks/lib/red_team_check.py" ]; then
    _REPO_ROOT_RESOLVED="${CLAUDE_PROJECT_DIR}"
fi

# Candidate 2: hook's own install location (BASH_SOURCE two levels up).
# Canonicalize BASH_SOURCE[0] via readlink -f (GNU/Linux) to resolve symlinks
# before deriving the root. Fall back to the raw path if readlink -f is
# unavailable (macOS/BSD readlink does not support -f without GNU coreutils).
if [ -z "$_REPO_ROOT_RESOLVED" ]; then
    _hook_self="${BASH_SOURCE[0]:-$0}"
    # Try readlink -f first; fall back to the raw symlink path on platforms
    # where readlink does not support -f (BSD/macOS without GNU coreutils).
    _hook_canonical="$(readlink -f "$_hook_self" 2>/dev/null)" || _hook_canonical="$_hook_self"
    _hook_dir="$(cd "$(dirname "$_hook_canonical")" 2>/dev/null && pwd)" || true
    if [ -n "$_hook_dir" ]; then
        _hook_root="$(cd "$_hook_dir/../.." 2>/dev/null && pwd)" || true
        if [ -n "$_hook_root" ] && [ -f "$_hook_root/.armature/hooks/lib/red_team_check.py" ]; then
            _REPO_ROOT_RESOLVED="$_hook_root"
        fi
    fi
fi

# Candidate 3: last-resort git-based derivation (cwd-dependent, kept as fallback).
if [ -z "$_REPO_ROOT_RESOLVED" ]; then
    _REPO_ROOT_RESOLVED="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi

REPO_ROOT="$_REPO_ROOT_RESOLVED"

# ---------------------------------------------------------------------------
# Resolve Python interpreter.
# If neither python3 nor python is available, fail-open: emit advisory,
# exit 0. The PreToolUse(Bash) gate is not a security barrier; the
# discipline is process-level. Missing Python is an environment problem,
# not a security failure mode.
# ---------------------------------------------------------------------------
PY=""
if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
fi

if [ -z "$PY" ]; then
    echo "ADVISORY [GATE-RED-TEAM-001]: no python3/python interpreter; skipping red-team enforcement" >&2
    exit 0
fi

# ---------------------------------------------------------------------------
# Parse stdin JSON, extract tool_input.command, run red-team check.
#
# All logic lives in Python (heredoc) to avoid bash-vs-python quoting hell.
# The Python is single-quoted into _PY so embedded apostrophes are
# forbidden (same convention as auto-reviewer.sh and task-readiness.sh).
# ---------------------------------------------------------------------------
_PY='
import io, json, os, sys

REPO_ROOT = os.environ.get("_PPC_REPO_ROOT", "")
ENFORCE = os.environ.get("ARMATURE_RED_TEAM_ENFORCE", "")

# Truthy set for ARMATURE_RED_TEAM_ENFORCE (and inline override).
# Normalise: strip whitespace, lowercase, then match.
# Strictly additive vs {"1","true"} -- never accidentally disables enforce.
# No apostrophes in this block (bash single-quoted heredoc constraint).
_TRUTHY = frozenset({"1", "true", "yes", "on"})

def _is_enforce_truthy(val):
    return val.strip().lower() in _TRUTHY

ENFORCING = _is_enforce_truthy(ENFORCE)

# L001: reject NUL bytes before any decode.
try:
    raw = sys.stdin.buffer.read()
except Exception:
    # Stdin read failure on a Bash hook is unexpected; fail-open (allow) so
    # the operator is not blocked by harness pathology. The block-dangerous-
    # commands.sh sibling fails-closed on stdin-read; for the marker
    # discipline (process, not security), open is the right default.
    sys.stderr.write("ADVISORY [GATE-RED-TEAM-001]: stdin read failed; skipping enforcement\n")
    sys.exit(0)

if b"\x00" in raw:
    sys.stderr.write(
        "BLOCK [GATE-RED-TEAM-001]: NUL bytes in command payload (potential bypass attempt per L001)\n"
    )
    sys.exit(2)

try:
    payload_str = raw.decode("utf-8", errors="replace")
    # Mirror block-dangerous-commands.sh: normalise literal LFs inside JSON
    # string values to spaces so JSON parses across multi-line commands.
    payload_str = payload_str.replace("\n", " ").replace("\r", " ")
    data = json.loads(payload_str)
except Exception:
    # Unparseable payload — allow (advisory). The downstream block-dangerous-
    # commands.sh hook also runs and will catch genuinely-malformed bash.
    sys.exit(0)

command = ""
ti = data.get("tool_input")
if isinstance(ti, dict):
    cmd = ti.get("command")
    if isinstance(cmd, str):
        command = cmd

if not command:
    # No command to inspect — allow.
    sys.exit(0)

# Shell-aware tokenization to detect `gh pr create` as a real command, not
# a literal substring inside a quoted argument or comment. Round-1 used a
# regex on the raw command text; two real gaps were identified:
#
#   (a) Backslash-newline line continuation (`gh \<LF> pr create`) was a
#       BYPASS — bash collapses backslash-newline before executing, but
#       the regex saw the backslash and failed to match. Under ENFORCE
#       this gave any multi-line gh pr create invocation a clean bypass.
#
#   (b) FALSE POSITIVES on echo / variable assignment / comment lines:
#       `echo "gh pr create"`, `CMD="gh pr create"`, `# gh pr create`
#       all matched the regex even though they do not invoke gh.
#
# shlex.split handles both: line continuations are consumed by the
# tokenizer; quoted strings become single opaque tokens; comments do not
# appear in the token list. We split, then scan the token stream for a
# command-segment that starts with [gh, pr, create, ...]. A command-segment
# starts at index 0 or immediately after a shell command separator
# token (one of: ;, &&, ||, |, &, ( ).
#
# Tokenizer audit checklist:
#   - BOM-prefixed: JSON parse handles before this point.
#   - CRLF: JSON parse layer normalises (replace \r with space) before parse.
#   - NBSP / zero-width whitespace: shlex tokenizes on shell-significant
#     whitespace, not Unicode \s, so NBSP would land inside a token — safe
#     against accidental token-split bypass (NBSP-padded "gh pr create"
#     would NOT match, which is correct — it is not an executable command).
#   - Empty command: handled before this point (early exit).
#   - Trailing whitespace: shlex handles.
#   - Comments: shlex with posix=True drops trailing #-comments; we set
#     posix=True (default) so `cmd # gh pr create` does not match. Comments
#     at the START of the command (`# gh pr create`) collapse to no tokens.
#   - Heredocs / variable-expansion of "gh pr create": shlex tokenises the
#     command but cannot resolve variables, so $CMD where CMD="gh pr create"
#     would not match. This is the intended safer direction — a hook can
#     not predict runtime variable expansion; gating on textual presence
#     of gh pr create tokens is the achievable contract.
#   - Malformed quoting: shlex raises ValueError on unmatched quotes; we
#     catch it and fall through to allow (advisory mode) since unparseable
#     commands are not the discipline concern and downstream
#     block-dangerous-commands.sh has its own coverage. (No apostrophes in
#     this heredoc block - bash single-quoted heredoc terminates at the
#     first apostrophe, same trap I caught myself in here at round 2.)

def _is_gh_pr_create(cmd_text):
    """Detect an executable `gh pr create` (or alias `gh pr new`) segment
    + extract inline overrides.

    `gh pr new` is the official gh-documented alias for `gh pr create`
    (listed under ALIASES in `gh pr create --help`). Both subcommands
    invoke the same PR-creation path and are matched via the
    _GH_PR_CREATE_SUBCMDS constant.

    Returns a dict:
        {
            "detected": bool,
            "overrides": {
                "ARMATURE_RED_TEAM_ENFORCE": str,  # if inline-prefixed
                "FORCE_RED_TEAM": str,             # if inline-prefixed
            }
        }

    The overrides dict captures bash inline env-prefix assignments that
    apply ONLY to the gh-pr-create command (e.g.
    `ARMATURE_RED_TEAM_ENFORCE=true gh pr create`). Bash treats these as
    temporary env for the following command; they live in the command
    STRING, not in this hook process environment. Without this extraction,
    the operator-explicit `ARMATURE_RED_TEAM_ENFORCE=true gh pr create`
    invocation would advisory-allow even though the operator clearly
    requested blocking.

    Inline overrides are extracted ONLY from the env-prefix of the
    specific segment that contains gh pr create (including env-wrapper
    internal assignments) - not from arbitrary other segments.

    Returns detected=False when the tokens appear only inside quoted
    strings, after #-comments, or as positional arguments of another
    command. overrides dict is empty in that case.

    Detection algorithm (round 2):
      1. Collapse bash line continuations (`\\<CR>?<LF>` -> empty).
         Round-1 fix handled `\\<LF>` only; CRLF was a self-audit gap.
      2. Tokenise via shlex.shlex(punctuation_chars=True) so shell
         control operators (`;`, `&&`, `||`, `|`, `&`, etc.) tokenise
         as standalone tokens even when adjacent to other text. Round-1
         used shlex.split which produced `[`git`, `push;`, `gh`, ...]`
         for `git push; gh pr create`, missing the segment boundary
         (codex P1 #1 round 2).
      3. At each command-segment start, skip leading env-assignment
         words (`VAR=val`). Bash treats these as temporary env for the
         following command, NOT as the command itself. Round-1 left
         these in the token stream and cleared at_segment_start, so
         `GH_TOKEN=... gh pr create` slipped through (codex P1 #2
         round 2).
      4. Match [gh, pr, create] when found at a (possibly env-stripped)
         segment start.
    """
    import re
    import shlex

    # Step 1: collapse line continuations. Both LF and CRLF.
    cmd_text = re.sub(r"\\\r?\n", "", cmd_text)

    # Step 1b: convert unquoted newlines to command separators AND
    # strip bash word-start comments. Combined walk for two reasons:
    # both passes need the same quote/escape/word-boundary state, and
    # comment stripping must happen BEFORE shlex sees the input
    # (round-7 cleared lex.commenters so shlex treats # as literal in
    # ALL positions; this walk is what restores correct bash comment
    # semantics).
    #
    # Bash semantics implemented here:
    #   - Unquoted newline (LF/CR) -> `;` (round-8: command separator
    #     same as `;`; shlex by default treats LF as whitespace)
    #   - Word-start `#` outside quotes -> strip from `#` to next
    #     unquoted LF (round-13 codex P2: round-7 cleared commenters
    #     to fix mid-word `#` like `echo issue#123`, but that broke
    #     trailing-comment cases like `echo ok # comment; gh pr create`
    #     where the `; gh pr create` is part of the comment and bash
    #     never invokes gh pr create)
    #   - Mid-word `#` outside quotes -> preserved literally
    #     (round-7: `echo issue#123` echoes the literal string
    #     `issue#123`; mid-word `#` is not a comment introducer)
    #   - Quoted content (single or double) -> preserved verbatim
    #     including `#` and newlines (bash does not treat either as
    #     special inside quotes)
    #   - Backslash escape -> next char appended literally
    #
    # `word_start` tracks whether the current cursor is at a word
    # boundary (preceded by whitespace, separator, or start-of-input)
    # where `#` would introduce a comment. Reset to True after every
    # whitespace or shell separator. Set to False after any non-
    # whitespace non-separator emit.
    #
    # CRLF (Windows-pasted) becomes `;;` after the walk. `;;` is in
    # the SEPS set (originally for bash case-statement terminators)
    # so segment boundary is still detected correctly.
    def _lf_to_separator(s):
        out = []
        in_single = False
        in_double = False
        escape = False
        in_comment = False
        word_start = True
        for c in s:
            if in_comment:
                if c in ("\n", "\r"):
                    in_comment = False
                    out.append(";")
                    word_start = True
                continue
            if escape:
                out.append(c)
                escape = False
                word_start = False
                continue
            if c == "\\" and not in_single:
                escape = True
                out.append(c)
                continue
            if c == "\x27" and not in_double:  # \x27 is a single-quote
                in_single = not in_single
                out.append(c)
                word_start = False
                continue
            if c == "\"" and not in_single:
                in_double = not in_double
                out.append(c)
                word_start = False
                continue
            if c == "#" and word_start and not in_single and not in_double:
                in_comment = True
                continue
            if c in ("\n", "\r") and not in_single and not in_double:
                out.append(";")
                word_start = True
                continue
            if c in (" ", "\t"):
                out.append(c)
                word_start = True
                continue
            if c in (";", "&", "|", "(", ")", "{", "}"):
                out.append(c)
                word_start = True
                continue
            out.append(c)
            word_start = False
        return "".join(out)

    cmd_text = _lf_to_separator(cmd_text)

    # Step 2: tokenise with punctuation-aware shell lexer.
    #
    # shlex.shlex defaults `commenters="#"`, which drops everything from `#`
    # to EOL. Bash, however, treats `#` as a comment introducer ONLY when
    # it starts a word (GNU bash manual section "Comments"). Mid-word `#`
    # is just a literal character: `echo issue#123` echoes the literal
    # string `issue#123`. The gap: `echo issue#123; gh pr create` had
    # `#123; gh pr create` dropped by shlex, so the chained `gh pr create`
    # was invisible to detection and bypassed enforcement.
    #
    # Fix: clear `lex.commenters` so `#` is treated as a literal character
    # in all positions. Leading-comment cases like `# gh pr create` still
    # do NOT trigger because `#` (now its own token) is not in SEPS, so
    # the subsequent `gh` is not at_segment_start. Trailing-comment cases
    # like `ls # then gh pr create maybe` similarly do not trigger because
    # `ls`/`#`/`then`/etc. are not separators. Quoted `#` (e.g.
    # `"comment # in string"`) was already correctly preserved by shlex
    # quote handling; the commenters change does not regress that. (No
    # apostrophes in this heredoc block - bash single-quoted heredoc
    # terminates at the first apostrophe; same trap caught multiple times,
    # banking the pattern to memory at next consolidation.)
    try:
        lex = shlex.shlex(cmd_text, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        tokens = list(lex)
    except ValueError:
        # Unparseable (unmatched quote, etc.). Allow - the dangerous-commands
        # gate handles security; we only care about well-formed gh pr create.
        return {"detected": False, "overrides": {}}

    # punctuation_chars=True tokenises ();<>|& as standalone tokens, including
    # multi-character sequences like && and ||. ;; (case statement terminator)
    # is also recognised.
    SEPS = {";", "&&", "||", "|", "&", "(", ")", "{", "}", ";;"}

    # gh pr subcommands that create a pull request.
    # `gh pr new` is the official gh-documented alias for `gh pr create`
    # (listed under ALIASES in `gh pr create --help`). Both subcommand
    # spellings invoke the same PR-creation path and must be gated.
    # ONLY these two forms create PRs; other `gh pr` subcommands
    # (view, edit, list, checkout, close, merge, review, etc.) must NOT match.
    _GH_PR_CREATE_SUBCMDS = ("create", "new")

    # Bash env-assignment word: `NAME=value` where NAME is a valid shell
    # identifier (alpha/underscore start). shlex tokenises the whole
    # assignment as one token; we match it with a regex.
    ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

    # Inline env-prefix variables whose values are extracted and returned
    # so the caller can override the hook env-derived ENFORCING / force_env
    # decisions. The operator-explicit form
    # `ARMATURE_RED_TEAM_ENFORCE=true gh pr create` is bash inline prefix;
    # the assignment lives in the command string but NOT in the hook
    # process environment, so os.environ does not see it.
    INLINE_OVERRIDE_VARS = {"ARMATURE_RED_TEAM_ENFORCE", "FORCE_RED_TEAM"}

    def _record_override(token, overrides):
        # token shape: NAME=value (regex already matched). Extract NAME
        # and value; record only the vars we care about.
        if "=" in token:
            name, _, value = token.partition("=")
            if name in INLINE_OVERRIDE_VARS:
                overrides[name] = value

    # GNU env (coreutils) flags that take a SEPARATE operand token.
    # Verified against `env --help`:
    #   -u, --unset=NAME      (short or long-with-space takes operand)
    #   -C, --chdir=DIR       (short or long-with-space takes operand)
    #   -S, --split-string=S  (short or long-with-space takes operand)
    # Long forms with `=` (`--unset=NAME`) embed the operand in one shlex
    # token and need no special handling. This set covers the separate-
    # operand cases.
    ENV_OPERAND_FLAGS = {"-u", "-C", "-S", "--unset", "--chdir", "--split-string"}

    # gh CLI parent-level flags that can appear BETWEEN `gh` and `pr`.
    # `gh -R owner/repo pr create` and `gh --repo owner/repo pr create`
    # are valid invocations where the parent-level flag interposes between
    # `gh` and the `pr` subcommand. Without this handling, those would
    # slip past detection. After matching `gh` at segment start, skip
    # parent flags (with operand consumption for the allow-list below)
    # before checking for [pr, create].
    #
    # The gh manual documents these as inherited subcommand flags:
    #   -R, --repo OWNER/REPO   (operand)
    #   --hostname HOST         (operand)
    # Other parent flags like --help / --version short-circuit gh execution
    # so they would not actually create a PR, but shlex cannot know that
    # semantically; treating them as standard flags (skip the token,
    # do not consume operand) is conservative and acceptable.
    GH_PARENT_OPERAND_FLAGS = {"-R", "--repo", "--hostname"}

    at_segment_start = True
    i = 0
    # Inline overrides extracted from the env-prefix of the segment that
    # contains gh pr create. Reset on every new segment start; populated
    # by the env-wrapper consume loop and the bash env-prefix skip loop.
    seg_overrides = {}
    while i < len(tokens):
        if at_segment_start:
            seg_overrides = {}
            # Handle `env` command wrapper at segment start:
            #   env [VAR=val ...] [-flags [operand] ...] command args...
            # Bash treats `env` as a real command that sets/clears
            # environment then execs the next argument as the command.
            #
            # Short-form env flags `-u/-C/-S` take a SEPARATE operand
            # token; long-form `--unset NAME`/`--chdir DIR` similarly.
            # Maintain an allow-list of operand-taking env flags; after
            # consuming such a flag, also consume the next token as its
            # operand.
            #
            # Long-form `--unset=NAME` and `--chdir=DIR` embed the operand
            # inside the same shlex token, so they need no special handling
            # (the flag-skip pass consumes the whole `--unset=NAME` token).
            # Combined short flags `-iu VAR` (where `-iu` means `-i -u`)
            # are an edge case not handled — shlex tokenises `-iu` as one
            # token, so we cannot distinguish "i and u flags combined"
            # from "single non-operand flag named iu". Documented as a
            # corner-case limitation; the common forms are all handled.
            # Same for `env -S "..."` (split-string) — shlex cannot see
            # inside the quoted operand, so a `gh pr create` inside is
            # not visible to detection. Acceptable for a process gate.
            if i < len(tokens) and tokens[i] == "env":
                i += 1
                while i < len(tokens):
                    t = tokens[i]
                    if ENV_ASSIGN_RE.match(t):
                        _record_override(t, seg_overrides)
                        i += 1
                    elif t.startswith("-"):
                        i += 1
                        # If this flag takes a SEPARATE operand, consume
                        # the next token too. Exact-match on the flag spelling
                        # to avoid false-skipping (e.g. an unknown `-x` should
                        # NOT also consume the next token).
                        if t in ENV_OPERAND_FLAGS and i < len(tokens):
                            i += 1
                    else:
                        break
                if i >= len(tokens):
                    break
            # Bash env-prefix syntax: VAR=val ... cmd. Skip any number
            # of leading env-assignments at this segment start. This loop
            # runs AFTER env-wrapper handling so `env GH_HOST=ghe GH_TOKEN=x
            # gh pr create` collapses correctly: env consumes
            # assignments+flags, then this loop is a no-op (already past them).
            while i < len(tokens) and ENV_ASSIGN_RE.match(tokens[i]):
                _record_override(tokens[i], seg_overrides)
                i += 1
            if i >= len(tokens):
                break
            tok = tokens[i]
            # Match gh by BASENAME so that absolute/relative-path invocations
            # are caught: `/usr/bin/gh pr create`, `./gh pr create`,
            # `/opt/homebrew/bin/gh pr create`, and Windows `gh.exe`.
            # Split on both `/` and `\` (os.path.basename is platform-
            # dependent and does not split `\` on POSIX or `/` on Windows;
            # command strings can contain either separator style).
            # Only the exact basename `gh` (POSIX) or case-insensitive
            # `gh.exe` (Windows) are matched — `mygh`, `gh-wrapper`, `ghx`
            # have different basenames and are NOT matched.
            _cmd_base = tok.replace("\\", "/").rsplit("/", 1)[-1]
            if _cmd_base == "gh" or _cmd_base.lower() == "gh.exe":
                # Skip parent-level gh flags that may appear between
                # `gh` and `pr`. Operand-take rules mirror the
                # env-wrapper handling above.
                j = i + 1
                while j < len(tokens):
                    t = tokens[j]
                    if t.startswith("-"):
                        j += 1
                        if t in GH_PARENT_OPERAND_FLAGS and j < len(tokens):
                            j += 1
                    else:
                        break
                if j < len(tokens) and tokens[j] == "pr":
                    # Skip pr-level flags that may appear between
                    # `pr` and `create`. gh CLI accepts -R/--repo at
                    # the `gh pr` parent in addition to the `gh` root,
                    # so a valid PR creation form like
                    # `gh pr -R owner/repo create` would otherwise
                    # bypass detection.
                    k = j + 1
                    while k < len(tokens):
                        t = tokens[k]
                        if t.startswith("-"):
                            k += 1
                            if t in GH_PARENT_OPERAND_FLAGS and k < len(tokens):
                                k += 1
                        else:
                            break
                    if k < len(tokens) and tokens[k] in _GH_PR_CREATE_SUBCMDS:
                        # Dry-run exemption: `gh pr create --dry-run` (or the
                        # alias `gh pr new --dry-run`) only PRINTS the PR
                        # without creating it (gh manual: "Print details
                        # instead of creating the PR"). Blocking the gate
                        # for this non-creating validation path is a false
                        # positive. Exempt it — but ONLY when `--dry-run` is a
                        # genuine standalone boolean flag, NOT when it is the
                        # VALUE of a preceding value-taking option.
                        #
                        # Bypass prevented: `gh pr create --title "--dry-run"`
                        # tokenizes (after shlex strips quotes) to
                        # [..., "create", "--title", "--dry-run"] and gh DOES
                        # create that PR (the title is literally "--dry-run").
                        # A naive "is --dry-run among post-create tokens" check
                        # would wrongly exempt that invocation. This scan
                        # maintains a value-flag-aware state machine: when a
                        # value-taking option without `=` is seen, the
                        # immediately following token is its value and is
                        # SKIPPED (not treated as a flag).
                        #
                        # Last --dry-run value wins (matches gh pflag behavior):
                        # a later --dry-run=false re-enables creation and must
                        # still block. e.g. `--dry-run --dry-run=false` has
                        # final value false → gh CREATES the PR → gate blocks.
                        # Conversely, `--dry-run=false --dry-run` has final
                        # value true → real dry-run → gate exempts.
                        # The scan does NOT break early on the first match;
                        # it walks ALL post-create tokens and tracks the LAST
                        # --dry-run occurrence.
                        #
                        # End-of-options (`--`): gh uses pflag, which treats
                        # a bare `--` token as end-of-options. All tokens
                        # AFTER `--` are positional arguments, and `gh pr
                        # create` rejects positionals (it errors out — it does
                        # NOT create and does NOT dry-run). Therefore a
                        # `--dry-run` that appears AFTER `--` is not a real
                        # dry-run flag and must NOT exempt the gate. When the
                        # scan encounters a bare `--` token, it stops scanning
                        # (break), leaving _dry_run_state at whatever a
                        # pre-`--` `--dry-run` set it to. This is correct: a
                        # pre-`--` `--dry-run` IS honored by gh; a post-`--`
                        # `--dry-run` is a positional and causes an error.
                        # Note: bare `--` is distinct from SEPS tokens (it is
                        # not a shell operator); the SEPS break above handles
                        # shell command separators, this break handles the
                        # gh/pflag end-of-options sentinel.
                        #
                        # gh pr create value-taking options (long + short).
                        # When these appear WITHOUT `=`, the next token is
                        # consumed as their value and must be skipped.
                        # IMPORTANT: this set is hand-maintained and must
                        # mirror gh pr create value-taking flags exactly.
                        # Drift risk: new gh releases may add value-taking
                        # options. Review on gh upgrades.
                        GH_CREATE_VALUE_FLAGS = {
                            "--title", "-t",
                            "--body", "-b",
                            "--base", "-B",
                            "--head", "-H",
                            "--reviewer", "-r",
                            "--assignee", "-a",
                            "--label", "-l",
                            "--milestone", "-m",
                            "--project", "-p",
                            "--template", "-T",
                            "--body-file", "-F",
                            "--recover",  # gh: "Recover input from a failed run of create" (no short alias)
                        }
                        # pflag truth table for --dry-run=<v>:
                        #   True  values: 1, t, T, true, TRUE, True
                        #   False values: 0, f, F, false, FALSE, False
                        #   Any OTHER value: treat as False (pflag would
                        #   reject the flag; gh would not create — but
                        #   blocking is the safe default; do NOT exempt
                        #   on an unparseable value).
                        _PFLAG_TRUE = {"1", "t", "T", "true", "TRUE", "True"}
                        # _dry_run_state tracks the LAST --dry-run value seen:
                        #   None  = no --dry-run flag encountered yet
                        #   True  = last --dry-run evaluates to true (dry-run on)
                        #   False = last --dry-run evaluates to false (creates PR)
                        _dry_run_state = None
                        _skip_next = False
                        _m = k + 1
                        while _m < len(tokens):
                            _t = tokens[_m]
                            if _t in SEPS:
                                break
                            # gh/pflag end-of-options: bare `--` stops flag
                            # parsing. Tokens after `--` are positionals;
                            # `gh pr create` rejects positionals and errors.
                            # A post-`--` `--dry-run` is NOT a real dry-run.
                            # Stop scanning here, honoring any pre-`--`
                            # --dry-run value already recorded in
                            # _dry_run_state.
                            if _t == "--":
                                break
                            if _skip_next:
                                # This token is the value of the preceding
                                # value-taking flag — not a standalone flag.
                                _skip_next = False
                                _m += 1
                                continue
                            # Exact match: bare --dry-run (standalone boolean → True).
                            if _t == "--dry-run":
                                _dry_run_state = True
                                # Do NOT break — last value wins; keep scanning.
                            # --dry-run=<value>: parse the value with pflag semantics.
                            elif _t.startswith("--dry-run="):
                                _val = _t[len("--dry-run="):]
                                _dry_run_state = _val in _PFLAG_TRUE
                                # Do NOT break — last value wins; keep scanning.
                            # Check for value-taking flags WITHOUT `=`.
                            # When such a flag appears as `--flag=value`
                            # (single token), the value is embedded and the
                            # next token is NOT consumed.
                            elif _t in GH_CREATE_VALUE_FLAGS:
                                # No `=` in this token: next token is its value.
                                _skip_next = True
                            # (If it starts with one of the long-form names
                            # followed by `=`, the value is embedded — no skip.)
                            _m += 1
                        if _dry_run_state is True:
                            return {"detected": False, "overrides": {}}
                        return {"detected": True, "overrides": seg_overrides}
        else:
            tok = tokens[i]
        # Advance and update segment state for next token.
        at_segment_start = tok in SEPS
        i += 1
    return {"detected": False, "overrides": {}}

# Known scope limitations (documented for the next reviewer):
#
# The shlex-based tokenizer cannot disambiguate bash reserved words from
# ordinary arguments in context. Specifically, `then`, `elif`, `else`,
# `do`, and `!` are command-segment introducers inside bash control flow
# (if/elif/then/else/fi, for/while/until/do/done, ! cmd) but ARE valid
# command arguments outside that context. shlex has no concept of bash
# grammar, so adding them to SEPS would create symmetric false positives
# (e.g. `echo then gh pr create` would trigger). The hook is a process-
# discipline gate, not a security boundary; an operator deliberately
# wrapping `gh pr create` in `if cond; then ...; fi` to bypass the
# discipline is making a deliberate choice, equivalent to unsetting
# ARMATURE_RED_TEAM_ENFORCE. Same rationale for backtick command
# substitution `\`gh pr create\`` (deprecated syntax; backticks attach
# to tokens) and for negation `! gh pr create` (uncommon usage for a
# side-effect-only command).
#
# Wrapper commands beyond `env` (`time`, `nohup`, `exec`, `sudo`,
# `command`, `builtin`) are not handled. `env` is the only one flagged
# in practice because GH_TOKEN/GH_HOST passthrough via `env` is the
# documented pattern in gh CLI docs. If a future PR encounters a
# `time gh pr create` or `nohup gh pr create` bypass, the wrapper-skip
# block above can be extended with additional command names; the shape
# is the same (consume wrapper, allow flags/assigns, re-check segment
# command).
#
# NOTE: absolute/relative-path invocations (`/usr/bin/gh pr create`,
# `./gh pr create`, `/opt/homebrew/bin/gh pr create`, `gh.exe pr create`,
# etc.) ARE now detected via basename matching (codex P2 fix). The
# remaining undetected forms are shell builtins/wrappers that interpose
# before the command name without being `env`: `command gh pr create`,
# `sudo gh pr create`, `xargs ... gh pr create`, backtick substitution
# `\`gh pr create\``, and `if/then` control-flow wrapping.
#
# - Escaped shell separators as literal arguments (codex P3, accepted
#   conservative limitation): a command like `echo \; gh pr create` or
#   `printf %s \| gh pr create` is a SINGLE bash command -- the escaped
#   `;`/`|`/`&` are literal arguments to echo/printf and gh is never
#   invoked. The _lf_to_separator char-walker processes the backslash-
#   escape path (setting escape=True, emitting the next char literally),
#   so the `\;` sequence emits a literal `;` character into the rebuilt
#   string rather than a separator. However, after that emission the
#   escape state clears and the subsequent ` gh pr create` tail is still
#   present as unquoted tokens, which shlex surfaces as a new segment
#   starting with `gh`. Under ARMATURE_RED_TEAM_ENFORCE on a triggered
#   branch the gate will BLOCK such a command -- a false positive in the
#   FAIL-SAFE direction (over-block, never a bypass). Fixing this would
#   require the char-walker to retain `\` in output only when it precedes
#   a shell-significant char, which risks subtly altering the separator-
#   detection semantics that are security-load-bearing. This limitation
#   is therefore accepted: the affected input patterns are contrived and
#   harmless in normal use. Operators who encounter a block can rephrase
#   (e.g. quote the separator argument with double-quotes, or split the
#   commands across separate Bash tool calls).

_detect_result = _is_gh_pr_create(command)
if not _detect_result["detected"]:
    # Not a gh pr create — no-op.
    sys.exit(0)

# Inline overrides from bash env-prefix on the gh-pr-create command itself.
# These run in addition to (logical OR with) the environment-derived values:
# an operator typing `ARMATURE_RED_TEAM_ENFORCE=true gh pr create` clearly
# intends enforcement; honor it even though the assignment lives in the
# command string, not in this hook process env.
_inline_overrides = _detect_result["overrides"]
_inline_enforce = _inline_overrides.get("ARMATURE_RED_TEAM_ENFORCE", "")
_inline_force = _inline_overrides.get("FORCE_RED_TEAM", "")
if _is_enforce_truthy(_inline_enforce):
    ENFORCING = True

# Hotfix bypass — same semantic as auto-reviewer.sh: emit ADVISORY but
# do not block. The phase file is a tracked governance signal allowing
# the operator to explicitly bypass discipline during incident response.
PHASE_FILE = os.path.join(REPO_ROOT, ".armature", "session", "phase")
if os.path.isfile(PHASE_FILE):
    try:
        with open(PHASE_FILE, "rb") as _pf:
            _phase_raw = _pf.read()
        if not any(b < 32 and b not in (9, 10, 13) for b in _phase_raw):
            _phase_val = _phase_raw.decode("utf-8", errors="replace").strip(" \t\n\r")
            if _phase_val == "Hotfix":
                sys.stderr.write(
                    "ADVISORY [GATE-RED-TEAM-001]: Hotfix phase active — bypassing red-team enforcement\n"
                )
                sys.exit(0)
    except Exception:
        # If the phase file is unreadable, fall through to standard checks.
        pass

# Load the shared module.
# Fail-closed under enforce: we now know the command IS a gh pr create
# (detection succeeded above). If the lib cannot be imported OR evaluation
# raises, failing open would allow the PR creation to proceed without any
# red-team check — the bypass the red team identified. Under
# ARMATURE_RED_TEAM_ENFORCE we therefore exit 2 (BLOCK). In advisory mode
# (enforce unset) we stay fail-open so operators are not blocked by
# infrastructure breakage when they have not opted in to enforcement.
sys.path.insert(0, os.path.join(REPO_ROOT, ".armature", "hooks", "lib"))
try:
    from red_team_check import evaluate_red_team
except Exception as exc:
    _reason = "red_team_check.py unavailable (" + repr(exc) + ")"
    if ENFORCING:
        sys.stderr.write(
            "BLOCK [GATE-RED-TEAM-001]: cannot evaluate red-team gate ("
            + _reason + "); failing closed under ARMATURE_RED_TEAM_ENFORCE\n"
        )
        sys.exit(2)
    else:
        sys.stderr.write(
            "ADVISORY [GATE-RED-TEAM-001]: " + _reason + " - skipping enforcement\n"
        )
        sys.exit(0)

try:
    # force_env: prefer inline override if present, else fall back to hook
    # process env. Inline values come from bash env-prefix on the
    # gh-pr-create command itself.
    _force_env_val = _inline_force or os.environ.get("FORCE_RED_TEAM", "")
    result = evaluate_red_team(
        REPO_ROOT,
        deliverable_text="",
        severity="",
        force_env=_force_env_val,
    )
except Exception as exc:
    _reason = "evaluate_red_team raised (" + repr(exc) + ")"
    if ENFORCING:
        sys.stderr.write(
            "BLOCK [GATE-RED-TEAM-001]: cannot evaluate red-team gate ("
            + _reason + "); failing closed under ARMATURE_RED_TEAM_ENFORCE\n"
        )
        sys.exit(2)
    else:
        sys.stderr.write(
            "ADVISORY [GATE-RED-TEAM-001]: " + _reason + " - skipping enforcement\n"
        )
        sys.exit(0)

triggered = result["triggered"]
marker_status = result["marker_status"]
marker_verdict = result["marker_verdict"]
reasons = "; ".join(result["reasons"]) if result["reasons"] else "(none)"

if not triggered:
    # No red-team triggers fired — PR is not a discipline candidate. Allow.
    sys.exit(0)

# Triggered case. evaluate_red_team already incorporated marker validation
# into the "triggered" decision: if marker was valid, it flipped triggered
# back to False and we would not be here. So at this point: triggered=True
# means no valid suppressing marker. (No apostrophes in this heredoc block:
# bash single-quoted heredoc terminates at the first apostrophe — same trap
# avoided across multiple review rounds.)
#
# The verdict to emit:
#   - missing marker → "no marker file"
#   - stale → "marker stale (fingerprint mismatch or missing field)"
#   - unmatched_verdict → "marker verdict was X, not PASS/APPROVED"
#   - malformed → "marker file unparseable"
#   - no_branch → "could not determine branch"

status_msg = {
    "missing": "no marker file at .armature/session/red-team-<branch>.json",
    "stale": "marker is stale (content_fingerprint mismatch or missing field)",
    "unmatched_verdict": (
        "marker verdict is " + (marker_verdict or "(empty)") + ", not PASS/APPROVED"
    ),
    "malformed": "marker JSON is unparseable",
    "no_branch": "could not determine current branch",
}.get(marker_status, "marker status: " + marker_status)

label = "BLOCK" if ENFORCING else "ADVISORY"
sys.stderr.write(
    label + " [GATE-RED-TEAM-001]: red-team trigger fired but marker is not valid\n"
)
sys.stderr.write("  Reasons: " + reasons + "\n")
sys.stderr.write("  Marker status: " + status_msg + "\n")
sys.stderr.write("\n")
sys.stderr.write("  To remediate:\n")
sys.stderr.write("    1. Dispatch the red-team reviewer for this PR\n")
sys.stderr.write(
    "    2. After PASS verdict, write a marker file with content_fingerprint\n"
)
sys.stderr.write(
    "       (see .armature/personas/orchestrator.md - Computing content_fingerprint)\n"
)
sys.stderr.write("    3. Retry `gh pr create`\n")
sys.stderr.write("\n")
if not ENFORCING:
    sys.stderr.write(
        "  Soft-deploy mode (ARMATURE_RED_TEAM_ENFORCE unset): allowing PR creation anyway.\n"
    )
    sys.stderr.write(
        "  Set ARMATURE_RED_TEAM_ENFORCE=true to block on this condition.\n"
    )
    sys.exit(0)
else:
    sys.stderr.write(
        "  Enforcement mode (ARMATURE_RED_TEAM_ENFORCE=true): blocking PR creation.\n"
    )
    sys.stderr.write("  To bypass once: unset ARMATURE_RED_TEAM_ENFORCE in this shell.\n")
    sys.exit(2)
'

export _PPC_REPO_ROOT="$REPO_ROOT"
# Write _PY to a temp file and execute it. Using `python -c "$_PY"` hits
# the Windows ARG_MAX limit (~32 KB) when _PY grows large; a temp-file
# exec is length-agnostic and avoids that constraint.
_PY_TMP="$(mktemp /tmp/pre_pr_create_XXXXXX.py 2>/dev/null || mktemp)"
trap 'rm -f "$_PY_TMP"' EXIT INT TERM HUP
printf '%s' "$_PY" > "$_PY_TMP"
"$PY" "$_PY_TMP"
