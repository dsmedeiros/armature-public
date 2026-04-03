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
# Try python first; fall back to a grep/sed approach.
#
# N-3 pre-processing: literal LF (0x0A) characters inside a JSON string
# value are not valid JSON, but they can appear when a multi-line command
# is piped directly into the hook.  Replace literal LFs with spaces in the
# raw JSON text before parsing so that the JSON parser can still extract the
# full command value across lines.
# ---------------------------------------------------------------------------
STDIN_CONTENT="$(cat | tr '\012' ' ')"

COMMAND=""
if command -v python3 &>/dev/null; then
  COMMAND="$(printf '%s' "$STDIN_CONTENT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('command', ''))
except Exception:
    pass
")"
elif command -v python &>/dev/null; then
  COMMAND="$(printf '%s' "$STDIN_CONTENT" | python -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('command', ''))
except Exception:
    pass
")"
else
  # Fallback: extract value of "command" key with sed
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
  # Reject absolute paths with sub-directories (e.g. /home/user/node_modules)
  if [[ "$raw_target" == /* ]] && [[ "$raw_target" != "/${b}" ]]; then return 1; fi

  for safe in "${SAFE_RM_TARGETS[@]}"; do
    if [[ "$b" == "$safe" ]] || [[ "$t" == "$safe" ]]; then return 0; fi
  done
  return 1
}

# Returns 0 (safe) only when every non-flag argument to an rm command is a
# recognised safe target; returns 1 (unsafe) as soon as any argument is not.
all_rm_targets_safe() {
  local cmd="$1"
  # Extract the portion of the command starting at the first "rm " token.
  # This handles prefixes like "sudo rm", "env rm", "xargs rm", etc.
  local rm_onwards="${cmd#*rm }"
  # Split into an array
  read -ra tokens <<< "$rm_onwards"
  local found_target=0
  for token in "${tokens[@]}"; do
    # Skip flag tokens (start with -)
    if [[ "$token" == -* ]]; then continue; fi
    found_target=1
    if ! is_safe_rm_target "$token"; then return 1; fi
  done
  # If no non-flag arguments were found, treat as unsafe (e.g. bare "rm -rf")
  if [[ $found_target -eq 0 ]]; then return 1; fi
  return 0
}

# ---------------------------------------------------------------------------
# Rule: rm -rf / rm -r -f on broad targets
#
# B-2 fix: only trigger when BOTH -r and -f are present.
#
# B-3 fix: skip when the rm token appears only inside a quoted string
#   argument to another command (e.g. echo "rm -rf is dangerous").
#   We detect this by checking whether the outermost context before "rm"
#   contains an unmatched opening quote.
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

# B-3 string-literal filter: check whether the text before the first
# occurrence of "rm " is inside an unmatched double-quote context.
_rm_in_string_literal=false
if [[ "$COMMAND" =~ rm[[:space:]] ]]; then
  # Extract everything before the first "rm " occurrence
  _prefix="${COMMAND%%rm *}"
  # Count unescaped double-quotes in the prefix
  _quote_count=$(printf '%s' "$_prefix" | tr -cd '"' | wc -c)
  # Odd count means we are inside a double-quoted string
  if (( _quote_count % 2 != 0 )); then
    _rm_in_string_literal=true
  fi
fi

if ! $_rm_in_string_literal; then
  # Substring scan: does the command contain "rm" with both -r and -f?
  _has_r=false
  _has_f=false
  if [[ "$COMMAND" =~ rm[[:space:]]([^;|&]*[[:space:]])?-[a-zA-Z]*[rR][a-zA-Z]* ]] || \
     [[ "$COMMAND" =~ rm[[:space:]]([^;|&]*[[:space:]])?-[rR]([[:space:]]|$) ]]; then
    _has_r=true
  fi
  if [[ "$COMMAND" =~ rm[[:space:]]([^;|&]*[[:space:]])?-[a-zA-Z]*[fF][a-zA-Z]* ]] || \
     [[ "$COMMAND" =~ rm[[:space:]]([^;|&]*[[:space:]])?-[fF]([[:space:]]|$) ]]; then
    _has_f=true
  fi
  if $_has_r && $_has_f; then
    if ! all_rm_targets_safe "$COMMAND"; then
      block "rm -rf" "recursive force-delete on broad targets can destroy repository state; use targeted deletion on specific safe directories only"
    fi
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
if [[ "$COMMAND" =~ git[[:space:]].*add.*([[:space:]]+-A[[:space:]]|[[:space:]]+-A$) ]] || \
   [[ "$COMMAND" =~ git[[:space:]].*add.*--all ]] || \
   [[ "$COMMAND" =~ git[[:space:]].*add.*([[:space:]]+-u[[:space:]]|[[:space:]]+-u$) ]] || \
   [[ "$COMMAND" =~ git[[:space:]].*add.*--update ]] || \
   [[ "$COMMAND" =~ git[[:space:]].*add[[:space:]]+\.[[:space:]]*$ ]]; then
  block "git add -A / --all / -u / --update / git add ." "staging all changes risks committing unintended files (secrets, binaries); stage files explicitly by name"
fi

# ---------------------------------------------------------------------------
# Rule: git checkout -- . (discard all unstaged changes in working tree)
# Allow: git checkout -- specific-file  and  git checkout branch-name
# The dangerous form is exactly "git checkout -- ." (dot as sole path arg).
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ git[[:space:]].*checkout[[:space:]].*--[[:space:]]+\.[[:space:]]*$ ]]; then
  block "git checkout -- ." "discards all unstaged working-tree changes and cannot be undone; specify individual files instead"
fi

# ---------------------------------------------------------------------------
# Rule: git restore . / git restore --staged .
# Allow: git restore <specific-file>
# Block only when the sole path argument is a bare dot.
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ git[[:space:]].*restore([[:space:]]+(--staged|--worktree|--source=[^[:space:]]*))*[[:space:]]+\.[[:space:]]*$ ]]; then
  block "git restore ." "discards all changes (staged or unstaged) and cannot be undone; specify individual files instead"
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
if [[ "$COMMAND" =~ mkfs([.[:space:]]|$) ]]; then
  block "mkfs" "formats a filesystem, permanently destroying all existing data on the target device"
fi

# ---------------------------------------------------------------------------
# Rule: fork bomb patterns  :(){ :|:& };:
# Match the two core signatures: :|: (self-pipe recursion) and (){ (function
# definition with an open brace that enables the pattern).
# ---------------------------------------------------------------------------
if [[ "$COMMAND" =~ :\|: ]] || [[ "$COMMAND" =~ \(\)\{[[:space:]] ]] || [[ "$COMMAND" =~ \(\)\{[[:space:]]*: ]]; then
  block "fork bomb" "fork bomb pattern detected — this would exhaust system process limits"
fi

# ---------------------------------------------------------------------------
# All checks passed — allow the command
# ---------------------------------------------------------------------------
exit 0
