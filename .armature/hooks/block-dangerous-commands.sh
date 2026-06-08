#!/usr/bin/env bash
# Armature PreToolUse(Bash) hook — blocks dangerous shell commands.
# Wire to Claude Code's PreToolUse event filtered to the Bash tool.
#
# Stdin: JSON object with a top-level "tool_input" key whose "command"
#        field contains the bash command string about to be executed.
# Exit 2  = block the tool call
# Exit 0  = allow the tool call

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# ---------------------------------------------------------------------------
# Parse the command string from stdin JSON.
#
# Security: NUL bytes (0x00) MUST be rejected before any decode. Bash command
# substitution (`$(cat)`) silently strips NUL bytes, allowing an attacker to
# pad command tokens with embedded nulls that disappear before pattern
# matching. This is lesson L001 in .armature/lessons.yaml. Newer framework
# hooks (tdd-gate.sh, tier0-preflight.sh, task-readiness.sh) all read stdin
# via Python's sys.stdin.buffer.read() and check for b"\x00" before decoding.
# This is a fail-closed security gate, so NUL byte detection triggers BLOCK.
#
# N-3 pre-processing: literal LF (0x0A) characters inside a JSON string
# value are not valid JSON, but they can appear when a multi-line command
# is piped directly into the hook.  Replace literal LFs with spaces in the
# raw JSON text before parsing so that the JSON parser can still extract the
# full command value across lines.
# ---------------------------------------------------------------------------
PYTHON=""
if command -v python3 &>/dev/null; then PYTHON="python3"; elif command -v python &>/dev/null; then PYTHON="python"; fi

if [ -n "$PYTHON" ]; then
  # Python path: full L001 NUL-byte guard + JSON parse via sys.stdin.buffer.
  # Python exits 2 on NUL detection; set -e propagates that as the script's
  # exit code, which BLOCKs the tool call (no separate py_rc capture needed —
  # bash exits at the failing command substitution under errexit).
  COMMAND="$("$PYTHON" -c "$(cat <<'PYEOF'
import json, sys
raw = sys.stdin.buffer.read()
# L001: reject NUL bytes before any decode — bash strips them, masking bypass.
# This is a fail-closed security gate, so NUL-byte payloads BLOCK.
if b'\x00' in raw:
    sys.stderr.write('BLOCK: NUL bytes in command payload (potential bypass attempt per L001)\n')
    sys.exit(2)
text = raw.decode('utf-8', errors='replace')
# N-3: normalise literal LFs inside JSON string values to spaces so JSON parses.
text = text.replace('\n', ' ').replace('\r', ' ')
try:
    data = json.loads(text)
    print(data.get('tool_input', {}).get('command', ''))
except Exception:
    pass
PYEOF
)")"
else
  # Python unavailable — fail-OPEN for parse, fail-CLOSED via pattern checks.
  # Without Python the L001 NUL-byte guard is inactive (bash command
  # substitution silently strips NUL), but the bash pattern checks below
  # still catch naked `rm -rf /` / `git reset --hard` / etc. This is
  # strictly better than the alternative of allowing every command, and
  # matches canonical's pre-PR-23 behaviour. Documented trade-off: a
  # determined attacker on a no-Python host could pad command tokens with
  # NUL bytes to bypass pattern matching; install python3 to close that
  # gap. Sed fallback parses the JSON command value with a single regex.
  echo "ADVISORY: block-dangerous-commands.sh has no python3/python — L001 NUL-byte guard inactive; pattern checks still apply" >&2
  STDIN_CONTENT="$(cat | tr '\012' ' ')"
  COMMAND="$(printf '%s' "$STDIN_CONTENT" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\(.*\)".*/\1/p' | head -1)"
fi

# Nothing to check if we couldn't extract a command
if [ -z "$COMMAND" ]; then
  exit 0
fi

# ---------------------------------------------------------------------------
# N-3 fix: normalize newlines so every logical line is visible to pattern
# matching.  Two forms can appear in JSON command strings:
#   • literal two-character sequence \n (JSON-escaped newline)
#   • actual 0x0A byte (multi-line here-strings piped in during tests)
# Replace both with " && " so each line is treated as a separate command
# segment without breaking any existing pattern that anchors on &&.
# ---------------------------------------------------------------------------
COMMAND="${COMMAND//\\n/ && }"
COMMAND="$(printf '%s' "$COMMAND" | tr '\012' ' ')"

# ---------------------------------------------------------------------------
# N-1 fix (backslash-command bypass): normalize \cmd → cmd.
# The shell allows \rm to bypass aliases/functions, but it still runs rm.
# Two encoding forms arise depending on how the JSON client handles \rm:
#   • Proper encoding: backslash (0x5C) + rm — strip the 0x5C.
#   • CR-escape encoding: JSON \r (0x0D) + m — replace CR with 'r'.
#     This occurs in environments where '\r' before a letter is processed
#     as the JSON \r escape sequence, consuming the 'r'.  Replacing 0x0D
#     with 'r' reconstructs the intended command token (e.g. \rm → rm).
# Unix paths never contain backslashes or bare CRs, so both transforms
# are safe on the target platform.
# ---------------------------------------------------------------------------
COMMAND="$(printf '%s' "$COMMAND" | tr -d '\134')"
COMMAND="$(printf '%s' "$COMMAND" | tr '\015' 'r')"

# ---------------------------------------------------------------------------
# Cycle-17 fix (shell-expanded-whitespace bypass): normalize all IFS
# parameter-expansion forms to a space. Bash expands $IFS (and any
# parameter-expansion subset of it) to space-tab-newline by default, so a
# command like `rm${IFS}-rf /` runs as `rm -rf /` but appears to the
# validator with the literal `${IFS}` between `rm` and `-rf`. The outer
# rm-rf substring detection and the per-rm operand walker both anchor on
# whitespace, so this substitution restores their visibility into
# variable-whitespace bypass patterns. Performed AFTER backslash/CR
# normalization so escape forms are decoded first.
#
# Covers:
#   ${IFS}                exact braced form
#   ${IFS:0:1}            substring expansion (first char)
#   ${IFS%??}             pattern-removal expansion
#   ${IFS#...}            prefix removal
#   ${IFS/x/y}            substitution
#   ${IFS^^}, ${IFS,,}    case modification
#   $IFS                  bare form (when followed by non-identifier char)
#
# Use sed because bash parameter-expansion ${var//pat/repl} only supports
# pathname-style globs, not regex; bash globs cannot express "${IFS} or
# ${IFS followed by any param-expansion operator}". PR #297 cycle-17 +
# PR dsmedeiros/armature#23 cycle-4 review.
# ---------------------------------------------------------------------------
# Pattern 1: ${IFS}, ${IFS<op><chars>} — any braced IFS expansion. The
# regex matches `${IFS` immediately followed by either `}` (exact form)
# or a non-identifier character (so ${IFSx} is left alone — that's a
# different variable) plus zero-or-more non-`}` chars plus `}`.
COMMAND="$(printf '%s' "$COMMAND" | sed -E 's/\$\{IFS\}/ /g; s/\$\{IFS[^A-Za-z0-9_}][^}]*\}/ /g')"
# Pattern 2: bare $IFS followed by non-identifier char or end of string.
# `\b` in BRE/ERE is GNU-specific; use a character class plus a trailing
# capture-and-restore so we replace only `$IFS` without consuming the
# following character.
COMMAND="$(printf '%s' "$COMMAND" | sed -E 's/\$IFS([^A-Za-z0-9_]|$)/ \1/g')"

# ---------------------------------------------------------------------------
# Helper: emit block message and exit 2
# ---------------------------------------------------------------------------
block() {
  local pattern="$1"
  local reason="$2"
  echo "BLOCK: ${pattern} is prohibited — ${reason}" >&2
  exit 2
}

# ---------------------------------------------------------------------------
# Safe targets for rm -rf (broad removal allowed for these directories)
# ---------------------------------------------------------------------------
SAFE_RM_TARGETS=(
  "node_modules"
  "__pycache__"
  "dist"
  "build"
  ".pytest_cache"
  ".tdd-dirty"
  ".code-dirty"
  ".venv"
  ".mypy_cache"
  ".ruff_cache"
  "__pypackages__"
)

is_safe_rm_target() {
  local raw_target="$1"
  # Strip surrounding quotes if any
  raw_target="${raw_target//\"/}"
  # Strip trailing slash
  local t="${raw_target%/}"
  # Take basename (strip any leading path components)
  local b="${t##*/}"

  # Reject path traversal
  if [[ "$raw_target" == *".."* ]]; then return 1; fi
  # Cycle-20 fix: reject ALL absolute paths. The safe-name allowlist is
  # for repo-local cache/build directories (node_modules, dist, .venv,
  # __pycache__, etc.); absolute paths whose basename happens to collide
  # with a safe name (e.g. `/build`, `/dist`, `/node_modules`) point at
  # filesystem-root directories outside the repo and must never be
  # rm-rf'd by a governed agent. Previously this check accepted any
  # absolute path of the form `/<basename>` because the inequality
  # `$raw_target != /${b}` failed for single-segment absolute targets.
  # If a user genuinely needs to wipe a repo-local cache, the relative
  # form (`rm -rf node_modules` or `rm -rf ./node_modules`) works.
  if [[ "$raw_target" == /* ]]; then return 1; fi

  for safe in "${SAFE_RM_TARGETS[@]}"; do
    if [[ "$b" == "$safe" ]] || [[ "$t" == "$safe" ]]; then return 0; fi
  done
  return 1
}

# Returns 0 (safe) only when EVERY rm invocation in the command has
# operands that are recognised safe targets. Returns 1 (unsafe) on the
# first unsafe operand or bare rm-rf.
#
# Handles chained commands by iterating over each ` rm ` occurrence and
# validating its operands separately. Shell separators (&&, ||, ;, |, &)
# bound each rm invocation; tokens after a separator belong to a
# different command and are not rm operands.
#
# Examples:
#   rm -rf node_modules && npm ci       → PASS (only one rm, safe target)
#   rm -rf node_modules && rm -rf /     → BLOCK (second rm has unsafe target)
#   rm -rf node_modules&&npm ci         → PASS (no-space variant)
all_rm_targets_safe() {
  # Normalize whitespace: convert TAB characters to spaces so that the
  # " rm " boundary detection works on tab-separated invocations like
  # `rm\t-rf /` or `sudo\trm\t-rf /`. Shells treat tabs as whitespace,
  # so the outer rm-rf regex (which uses [[:space:]]) matches both
  # forms; the operand validator must too. Without this step a real
  # rm-rf invocation with tab separators would silently pass the
  # safe-target check. (L001-class bypass.)
  # Whitespace-variable expansion (`${IFS}` / `$IFS`) is normalized at
  # the top-level COMMAND processing step BEFORE this function is called,
  # so by the time we get here those substrings have already been replaced
  # with literal spaces. See COMMAND normalization in the parent script.
  local cmd_norm="${1//	/ }"   # literal TAB → space (the char between // and / is a TAB)
  # Strip quote characters — they are token-delimiters in the shell but
  # our parser uses whitespace boundaries. Without this step an `rm`
  # token immediately after a quote (e.g. `echo "rm -rf /"`) wouldn't be
  # flagged by the " rm " pattern. Replacing quotes with spaces preserves
  # rm-token visibility for pipe-into-shell attacks like
  # `echo "rm -rf /" | ksh`.
  local cmd_unquoted="${cmd_norm//\"/ }"
  cmd_unquoted="${cmd_unquoted//\'/ }"
  # Normalize shell separators by padding with spaces. This ensures that
  # an rm immediately following a separator without whitespace (e.g.
  # `rm -rf safe&&rm -rf /` or `rm -rf safe;rm -rf /`) is still seen
  # by the " rm " (space-rm-space) boundary detection. Multi-char
  # separators must be padded BEFORE single-char ones so we don't break
  # `&&` apart prematurely; the subsequent single-char pass adds extra
  # spaces inside already-padded multi-char separators (harmless — bash
  # word-splitting absorbs multiple consecutive spaces).
  #
  # Also normalize command-substitution delimiters (`$(`, backtick, `)`)
  # to spaces. Without this, `$(rm -rf /)` or `` `rm -rf /` `` would
  # have rm preceded by `$(` / backtick (not space), and the validator
  # would miss the rm entirely. PR #297 cycle-12 finding #26.
  local cmd_sep="${cmd_unquoted//&&/ && }"
  cmd_sep="${cmd_sep//||/ || }"
  cmd_sep="${cmd_sep//;/ ; }"
  cmd_sep="${cmd_sep//&/ & }"
  cmd_sep="${cmd_sep//|/ | }"
  cmd_sep="${cmd_sep//\$(/ \$( }"     # `$(` (command substitution start) → space-padded
  cmd_sep="${cmd_sep//)/ ) }"          # `)` (command substitution end) → space-padded
  cmd_sep="${cmd_sep//\`/ }"           # backtick → space (legacy command substitution)
  # Prepend a space so " rm " (space-rm-space) matches an rm at the very
  # start of the command as well as in the middle (e.g. after "sudo " or
  # after a separator).
  local remaining=" $cmd_sep"

  while [[ "$remaining" == *" rm "* ]]; do
    # Advance past the next " rm " to the operand region.
    remaining="${remaining#* rm }"

    # Slice operand region at the first shell separator. Each %% is a
    # no-op if its pattern is absent, so the chain safely peels the
    # longest non-separator prefix.
    local chunk="$remaining"
    chunk="${chunk%%&&*}"
    chunk="${chunk%%||*}"
    chunk="${chunk%%;*}"
    chunk="${chunk%%|*}"
    chunk="${chunk%%&*}"

    # Only validate when THIS rm has both -r and -f. Individual rms in a
    # chain may not all be rm-rf (the outer caller only confirms the
    # whole command contains rm-rf somewhere).
    local has_r=0
    local has_f=0
    if [[ "$chunk" =~ (^|[[:space:]])-[a-zA-Z]*[rR][a-zA-Z]*([[:space:]]|$) ]] || \
       [[ "$chunk" =~ (^|[[:space:]])--recursive([[:space:]]|$) ]]; then
      has_r=1
    fi
    if [[ "$chunk" =~ (^|[[:space:]])-[a-zA-Z]*[fF][a-zA-Z]*([[:space:]]|$) ]] || \
       [[ "$chunk" =~ (^|[[:space:]])--force([[:space:]]|$) ]]; then
      has_f=1
    fi
    if [[ $has_r -eq 0 || $has_f -eq 0 ]]; then
      continue   # this rm isn't rm-rf; skip it
    fi

    # Validate operands of this rm chunk.
    read -ra tokens <<< "$chunk"
    local found_target=0
    for token in "${tokens[@]}"; do
      # Skip flag tokens (start with -)
      if [[ "$token" == -* ]]; then continue; fi
      # Handle no-space separator embedded in a token (e.g. "foo&&bar"):
      # slice the prefix before the separator, evaluate it, then stop —
      # the outer while loop will pick up any remaining rm invocations.
      case "$token" in
        *"&&"*|*"||"*|*";"*|*"|"*|*"&"*)
          local prefix="$token"
          prefix="${prefix%%&&*}"
          prefix="${prefix%%||*}"
          prefix="${prefix%%;*}"
          prefix="${prefix%%|*}"
          prefix="${prefix%%&*}"
          if [[ -n "$prefix" && "$prefix" != -* ]]; then
            found_target=1
            if ! is_safe_rm_target "$prefix"; then return 1; fi
          fi
          break
          ;;
      esac
      found_target=1
      if ! is_safe_rm_target "$token"; then return 1; fi
    done
    # Bare `rm -rf` with no operands is unsafe.
    if [[ $found_target -eq 0 ]]; then return 1; fi
  done

  return 0
}

# ---------------------------------------------------------------------------
# Rule: rm -rf / rm -r -f on broad targets
#
# B-2 fix: only trigger when BOTH -r and -f are present.
#
# B-3 note (cycle-3 removal): The B-3 string-literal filter was removed
#   in cycle-3 after two successive cycles produced exploitable bypasses.
#   The filter's purpose was to allow `echo "rm -rf is dangerous"` — a rare
#   documentation use case.  Every implementation attempt introduced new
#   HIGH-severity bypass vectors (quote parity in cycle-1; 2-element pipe
#   denylist in cycle-2).  The filter has been removed entirely.  The
#   usability cost is accepted: ANY command containing the rm-rf pattern now
#   blocks, including:
#     echo "rm -rf ..."          grep "rm -rf" file.txt
#     git log --grep "rm -rf"    rg "rm -rf"
#     git commit -m "removed rm -rf usage"
#     alias safe='echo rm -rf'
#   Workarounds for legitimate documentation strings:
#     - Use split tokens:   echo "rm" "-rf" "..."
#     - Obfuscate letter:   echo "r-m -rf is dangerous"
#     - Use prose:          echo "the recursive force-remove command is dangerous"
#
# Known false positives (pre-existing, not introduced by M2):
#   The substring scan fires on any token containing "rm" followed by -r/-f
#   flags anywhere, so commands like `xterm -rf` or `term -rf` are blocked
#   even though they have no relation to the rm command.  Future work should
#   anchor "rm" at command-position rather than using a substring match.
#
# N-1/N-2/N-3 fix: rather than anchoring rm at command position (which
#   fails for sudo/env/command/\rm prefixes, subshell expressions, and
#   newline-embedded commands), we do a simple substring scan for "rm"
#   followed by both -r and -f flags ANYWHERE in the (now newline-
#   normalised) command string.  This catches:
#     sudo rm -rf /        env rm -rf /     command rm -rf /
#     \rm -rf /            $(rm -rf /)      `rm -rf /`
#     xargs rm -rf         newline-embedded rm -rf /
# ---------------------------------------------------------------------------

# Substring scan: does the command contain "rm" with both -r and -f?
# Handles short flags (-r, -R, -f, -rf, etc.) and long-form synonyms
# (--recursive, --force) and any mixed combination thereof.
_has_r=false
_has_f=false
if [[ "$COMMAND" =~ rm[[:space:]]([^;|&]*[[:space:]])?-[a-zA-Z]*[rR][a-zA-Z]* ]] || \
   [[ "$COMMAND" =~ rm[[:space:]]([^;|&]*[[:space:]])?-[rR]([[:space:]]|$) ]] || \
   [[ "$COMMAND" =~ rm[[:space:]]([^;|&]*[[:space:]])?--recursive([[:space:]]|$) ]]; then
  _has_r=true
fi
if [[ "$COMMAND" =~ rm[[:space:]]([^;|&]*[[:space:]])?-[a-zA-Z]*[fF][a-zA-Z]* ]] || \
   [[ "$COMMAND" =~ rm[[:space:]]([^;|&]*[[:space:]])?-[fF]([[:space:]]|$) ]] || \
   [[ "$COMMAND" =~ rm[[:space:]]([^;|&]*[[:space:]])?--force([[:space:]]|$) ]]; then
  _has_f=true
fi
if $_has_r && $_has_f; then
  if ! all_rm_targets_safe "$COMMAND"; then
    block "rm -rf" "recursive force-delete on broad targets can destroy repository state; use targeted deletion on specific safe directories only"
  fi
fi

# ---------------------------------------------------------------------------
# Rule: git push --force / git push -f
# --force-with-lease is intentionally excluded: it is a safe push mode that
# only succeeds when the remote tip matches what the pusher last fetched.
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ git[[:space:]].*push.*--force([[:space:]]|$) ]] || \
   [[ "$COMMAND" =~ git[[:space:]].*push.*[[:space:]]-f([[:space:]]|$) ]]; then
  block "git push --force" "force-pushing rewrites remote history and can destroy work for all collaborators"
fi

# ---------------------------------------------------------------------------
# Rule: git reset --hard
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ git[[:space:]].*reset.*--hard ]]; then
  block "git reset --hard" "discards all local changes and cannot be undone"
fi

# ---------------------------------------------------------------------------
# Rule: git clean -f / -fd / -fx
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ git[[:space:]].*clean.*[[:space:]]-[fdxX]*f[fdxX]* ]]; then
  block "git clean -f" "permanently deletes untracked files and cannot be undone"
fi

# ---------------------------------------------------------------------------
# Rule: DROP TABLE / TRUNCATE (SQL destructive statements)
# ---------------------------------------------------------------------------
if echo "$COMMAND" | grep -qiE 'DROP[[:space:]]+TABLE|TRUNCATE[[:space:]]'; then
  block "DROP TABLE / TRUNCATE" "destructive SQL statements can cause irreversible data loss"
fi

# ---------------------------------------------------------------------------
# Rule: chmod -R 777
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ chmod.*-R.*777 ]] || [[ "$COMMAND" =~ chmod.*777.*-R ]]; then
  block "chmod -R 777" "world-writable recursive permission change is a security vulnerability"
fi

# ---------------------------------------------------------------------------
# Rule: --no-verify / --skip-hooks flags
# Match --no-verify only as a complete flag (followed by space, end-of-string,
# or another flag character) to avoid false-positives on --no-verify-ssl,
# --no-verify-signatures, etc.
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ (^|[[:space:]])--no-verify([[:space:]]|$) ]] || \
   [[ "$COMMAND" =~ (^|[[:space:]])--skip-hooks([[:space:]]|$) ]]; then
  block "--no-verify / --skip-hooks" "bypassing commit hooks defeats governance enforcement"
fi

# ---------------------------------------------------------------------------
# Rule: git add -A / --all / -u / --update / bare dot (but NOT git add ./specific-file)
# -u / --update stages all modifications and deletions to already-tracked
# files without requiring explicit file names, posing the same broad-staging
# risk as -A / --all.
# ---------------------------------------------------------------------------
# Note on terminators: each pattern ends with (.[[:space:]]*($|[;&|]))
# instead of `\.[[:space:]]*$` so chained commands like
# `git add . && git commit -m ...` are caught — the dot can be followed
# by end-of-string OR a shell separator (;, &, |). Without this, an
# end-anchored guard silently allows the broad-staging form when the
# user chains a follow-up command.
#
# Cycle-19: also block `git add -- .` — git treats `--` as the option
# terminator and the following `.` is the same broad pathspec as a bare
# `.`. Without the optional `(--[[:space:]]+)?` group, an attacker could
# bypass the bare-dot guard by inserting the option terminator. Same
# treatment for any whitespace before the dot. See `git add -h`:
#   usage: git add [<options>] [--] <pathspec>...
if [[ "$COMMAND" =~ git[[:space:]].*add.*([[:space:]]+-A[[:space:]]|[[:space:]]+-A$) ]] || \
   [[ "$COMMAND" =~ git[[:space:]].*add.*--all ]] || \
   [[ "$COMMAND" =~ git[[:space:]].*add.*([[:space:]]+-u[[:space:]]|[[:space:]]+-u$) ]] || \
   [[ "$COMMAND" =~ git[[:space:]].*add.*--update ]] || \
   [[ "$COMMAND" =~ git[[:space:]].*add[[:space:]]+(--[[:space:]]+)?\.[[:space:]]*($|[;&|]) ]]; then
  block "git add -A / --all / -u / --update / git add [--] ." "staging all changes risks committing unintended files (secrets, binaries); stage files explicitly by name"
fi

# ---------------------------------------------------------------------------
# Rule: git checkout -- . (discard all unstaged changes in working tree)
# Allow: git checkout -- specific-file  and  git checkout branch-name
# The dangerous form is exactly "git checkout -- ." (dot as sole path arg).
# Terminator handles chained commands per the note above.
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ git[[:space:]].*checkout[[:space:]].*--[[:space:]]+\.[[:space:]]*($|[;&|]) ]]; then
  block "git checkout -- ." "discards all unstaged working-tree changes and cannot be undone; specify individual files instead"
fi

# ---------------------------------------------------------------------------
# Rule: git restore . / git restore --staged .
# Allow: git restore <specific-file>
# Block only when the sole path argument is a bare dot.
# Terminator handles chained commands per the note above.
# ---------------------------------------------------------------------------
# Cycle-19 sibling extension: also accept an explicit `--` option terminator
# before the bare dot (e.g. `git restore -- .`, `git restore --staged -- .`).
# Per `git restore -h`, usage is `git restore [<options>] [--] <pathspec>...`
# so omitting the `--` cover-all-with-option-terminator form would replicate
# the cycle-19 `git add -- .` bypass class on this command too.
if [[ "$COMMAND" =~ git[[:space:]].*restore([[:space:]]+(--staged|--worktree|--source=[^[:space:]]*))*[[:space:]]+(--[[:space:]]+)?\.[[:space:]]*($|[;&|]) ]]; then
  block "git restore [--] ." "discards all changes (staged or unstaged) and cannot be undone; specify individual files instead"
fi

# ---------------------------------------------------------------------------
# Rule: git branch -D (force-delete branch)
# Allow: git branch -d (safe delete) and git branch (listing)
# Match only the uppercase -D flag (alone or combined) to avoid collateral.
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ git[[:space:]].*branch[[:space:]].*[[:space:]]-[a-zA-Z]*D[a-zA-Z]*([[:space:]]|$) ]] || \
   [[ "$COMMAND" =~ git[[:space:]].*branch[[:space:]]+-[a-zA-Z]*D[a-zA-Z]*([[:space:]]|$) ]]; then
  block "git branch -D" "force-deletes a branch regardless of merge status and cannot be undone; use git branch -d for a safe delete"
fi

# ---------------------------------------------------------------------------
# Rule: git stash drop (permanently discards a stash entry)
# Allow: git stash, git stash pop, git stash list, git stash show, etc.
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ git[[:space:]].*stash[[:space:]]+(drop|clear)([[:space:]]|$) ]]; then
  block "git stash drop/clear" "permanently discards stash entries and cannot be undone"
fi

# ---------------------------------------------------------------------------
# Rule: dd if= (raw disk operations)
#
# N-1/N-2/N-3 fix: use simple substring match anywhere in the (newline-
# normalised) command string so that "sudo dd if=...", "$(dd if=...)", and
# newline-embedded variants are all caught.
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ dd[[:space:]].*if= ]]; then
  block "dd if=" "raw disk read/write can corrupt filesystems and is irreversible"
fi

# ---------------------------------------------------------------------------
# Rule: mkfs (filesystem format — destroys all data on a device)
#
# N-1/N-2/N-3 fix: same approach — substring match anywhere.
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ (^|[;&|[:space:]])mkfs([.[:space:]]|$) ]]; then
  block "mkfs" "formats a filesystem, permanently destroying all existing data on the target device"
fi

# ---------------------------------------------------------------------------
# Rule: fork bomb patterns  :(){ :|:& };:
# :|:       — self-pipe recursion: a function calls itself twice, piped,
#             causing exponential process spawning.
# ()[[:space:]]*{ — shell function definition preamble; `(){` (no space) and
#             `() {` (with space) are both matched.  Any function definition
#             followed immediately by a recursive pipe call is the fork-bomb
#             template, so we block on the definition alone as a conservative
#             proxy — legitimate scripts rarely define anonymous functions
#             named single punctuation characters in a one-liner.
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ :\|: ]] || [[ "$COMMAND" =~ \(\)[[:space:]]*\{ ]]; then
  block "fork bomb" "fork bomb pattern detected — this would exhaust system process limits"
fi

# ---------------------------------------------------------------------------
# All checks passed — allow the command
# ---------------------------------------------------------------------------
exit 0
