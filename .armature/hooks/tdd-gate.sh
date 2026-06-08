#!/usr/bin/env bash
# Armature PreToolUse hook — tdd-gate
# Event:  PreToolUse(Edit)
# Stdin:  JSON object with a tool_input.file_path field (Claude Code hook payload)
# Invariant: TDD-001
# Cycle-2 fix: phase file is read via Python to reject NUL bytes and other
# control characters (HIGH finding from m3-cp3 red-team review).
# m3-cp4 polish (LOW-2): stdin payload is read via Python stdin.buffer.read()
#   instead of bash "$(cat)", preserving NUL bytes so the control-char check
#   fires correctly even when file_path contains a NUL byte.
#
# Purpose:
#   Block any Edit to a source file when no matching test file exists for that
#   source.  Enforces the TDD discipline: write the failing test before editing
#   the implementation.
#
# Matching conventions (first match wins):
#   1. Hook script convention (checked FIRST so that .armature/hooks/test_foo.sh
#      is still gated even though its basename starts with test_):
#        .armature/hooks/<name>.sh → .armature/tests/test_<name_dashes_to_underscores>.py
#        Match is case-insensitive (REL_PATH_LOWER used for prefix comparison
#        only; original REL_PATH used for stem extraction and file lookups).
#        Top-level .sh files under .armature/hooks/ are covered by the TDD
#        convention.  Paths with subdirs (e.g. .armature/hooks/__tests__/foo.sh)
#        are BLOCKED outright — subdirectories in hooks/ are non-canonical and
#        would otherwise evade both the TDD convention and the test-file exemption
#        (cycle-3 MEDIUM-2 fix).
#   2. File is itself a test (basename starts with test_, or path contains
#      /tests/ or /__tests__/) → allow (no test-for-tests requirement).
#      Note: this check fires AFTER Check 1 so that hook scripts whose names
#      start with test_ (e.g. .armature/hooks/test_foo.sh) are still gated.
#   3. Exempt extensions: .md .txt .rst .yaml .yml .toml .json .ini .cfg .env
#      No extension at all (Makefile, Dockerfile, etc.) → allow.
#   4. Exempt path prefixes: .armature/ (except .armature/hooks/*.sh, already
#      handled above), .claude/, docs/, adr/ → allow.
#   5. Python source:
#        <dir>/<stem>.py → tests/test_<stem>.py  OR  tests/<dir>/test_<stem>.py
#   6. JS/TS source:
#        <dir>/<stem>.{ts,js,tsx,jsx,mts,cts,mjs,cjs} →
#          <dir>/<stem>.test.<ext>
#          <dir>/<stem>.spec.<ext>
#          __tests__/<stem>.test.<ext>
#   7. Unknown extension → exit 0 (fail-open).
#
# Case-sensitivity note:
#   All bash glob patterns are case-sensitive.  Check 1 explicitly converts
#   REL_PATH to lowercase (REL_PATH_LOWER) for the prefix comparison so that
#   paths like .armature/HOOKS/foo.sh match on case-insensitive filesystems
#   (Windows NTFS, macOS APFS default).  All other checks remain case-sensitive
#   because they match source-file extensions, which are conventionally
#   lowercase.
#
# Fail-open conditions (exit 0 without blocking):
#   - Not in a git repo            (cannot determine REPO_ROOT)
#   - Python unavailable           (cannot parse JSON payload)
#   - JSON payload is invalid
#   - tool_input.file_path is absent or empty
#   - file_path contains only whitespace
#   - Unrecognized/unknown extension
#
# Hotfix bypass:
#   If .armature/session/phase contains exactly "Hotfix", the hook emits an
#   advisory and exits 0.  This matches D4 from m3-plan.md.
#
# Exit codes:
#   0  = allow (fail-open, exempt, hotfix-bypass, matching test found)
#   2  = block (BLOCK [TDD-001] emitted on stderr)
#
# Cross-platform: works on Git Bash (Windows), bash on Linux, bash on macOS.
# Performance: no external processes beyond python3/python for JSON parse.
# Requires: bash 4+ (for ${VAR,,} lowercase expansion used in Check 1).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
[ -z "$REPO_ROOT" ] && exit 0  # fail-open: not in a git repo

# ---------------------------------------------------------------------------
# Extract tool_input.file_path using Python reading raw stdin bytes.
#
# Defense-in-depth (LOW-2 fix, m3-cp4 polish pass):
#   The previous pattern was PAYLOAD="$(cat || true)" followed by piping
#   $PAYLOAD to Python.  bash command substitution silently strips NUL bytes
#   (0x00), so a JSON payload containing "foo\x00bar" in file_path would have
#   the NUL stripped before Python saw it — defeating Python's control-character
#   check.  By having Python read stdin.buffer directly, NUL bytes are preserved
#   and the check fires correctly.
#
# Control characters (including NUL) in file_path → exit 2 immediately.
# ---------------------------------------------------------------------------
_PYTHON_EXTRACT='
import json, sys
try:
    raw = sys.stdin.buffer.read()
    if any(b == 0 for b in raw):
        sys.stderr.write("BLOCK [TDD-001]: stdin payload contains NUL byte.\n")
        sys.exit(2)
    data = json.loads(raw)
    fp = data.get("tool_input", {}).get("file_path")
    if fp is None or fp == "":
        print("")
    elif any(ord(c) < 32 for c in fp):
        sys.stderr.write("BLOCK [TDD-001]: file_path contains control characters.\n")
        sys.exit(2)
    else:
        print(fp)
except json.JSONDecodeError:
    pass  # fail-open
except Exception:
    pass  # fail-open
'

FILE_PATH=""
_EXTRACT_RC=0
if command -v python3 >/dev/null 2>&1; then
    FILE_PATH="$(python3 -c "$_PYTHON_EXTRACT")" || _EXTRACT_RC=$?
elif command -v python >/dev/null 2>&1; then
    FILE_PATH="$(python -c "$_PYTHON_EXTRACT")" || _EXTRACT_RC=$?
fi
# Exit code 2 from the extractor means NUL-byte or control-character rejection
[ "$_EXTRACT_RC" -eq 2 ] && exit 2

[ -z "$FILE_PATH" ] && exit 0  # fail-open: no file_path or python unavailable

# ---------------------------------------------------------------------------
# Normalize file_path to absolute (agents may supply relative paths)
# ---------------------------------------------------------------------------
case "$FILE_PATH" in
    /*) : ;;  # already absolute (POSIX)
    [A-Za-z]:*) : ;;  # already absolute (Windows drive letter)
    *)  FILE_PATH="$REPO_ROOT/$FILE_PATH" ;;
esac

# Resolve any symlinks / .. components where available
if command -v realpath >/dev/null 2>&1; then
    FILE_PATH="$(realpath -m "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")"
elif command -v python3 >/dev/null 2>&1; then
    FILE_PATH="$(python3 -c "
import os, sys
print(os.path.normpath(sys.argv[1]))
" "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")"
elif command -v python >/dev/null 2>&1; then
    FILE_PATH="$(python -c "
import os, sys
print(os.path.normpath(sys.argv[1]))
" "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")"
fi

# ---------------------------------------------------------------------------
# Resolve Python interpreter (python3 preferred, python fallback)
# ---------------------------------------------------------------------------
PY=""
if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
fi

# ---------------------------------------------------------------------------
# Hotfix bypass — check .armature/session/phase
# Phase is read via Python to reject NUL bytes and other control characters.
# bash command-substitution silently strips NUL bytes, which allows a file
# containing "Hot\x00fix" to alias to "Hotfix" and bypass the gate.
# ---------------------------------------------------------------------------
PHASE_FILE="$REPO_ROOT/.armature/session/phase"
if [ -f "$PHASE_FILE" ] && [ -s "$PHASE_FILE" ] && [ -n "$PY" ]; then
    PHASE="$(
        "$PY" -c "
import sys
VALID = {'Discovery', 'Design', 'Implementation', 'Review', 'Release', 'Hotfix'}
try:
    with open('$PHASE_FILE', 'rb') as f:
        raw = f.read()
    if any(b < 32 and b not in (9, 10, 13) for b in raw):
        sys.exit(0)  # control bytes present -> treat as unknown phase
    decoded = raw.decode('utf-8', errors='replace').strip(' \t\n\r')
    if decoded in VALID:
        print(decoded)
except Exception:
    pass
" 2>/dev/null || echo ""
    )"
    if [ "$PHASE" = "Hotfix" ]; then
        echo "ADVISORY: Hotfix phase active — tdd-gate bypassed per §7.9." >&2
        exit 0
    fi
fi

# ---------------------------------------------------------------------------
# Compute relative path from REPO_ROOT for matching
# ---------------------------------------------------------------------------
REPO_ROOT_NORM="${REPO_ROOT%/}"
REL_PATH="${FILE_PATH#$REPO_ROOT_NORM/}"

# ---------------------------------------------------------------------------
# Check 1: Hook script convention (MUST be first — precedes test-file exemption
#   so that .armature/hooks/test_foo.sh is not silently exempted).
#   .armature/hooks/<name>.sh → .armature/tests/test_<stem_dashes_to_underscores>.py
#
#   Case-insensitive prefix match: convert REL_PATH to lowercase for the
#   case comparison only; use original REL_PATH for stem extraction and
#   file existence checks.
#
#   Top-level .sh files are gated by the TDD convention.
#   Subdirectory paths (e.g. .armature/hooks/__tests__/foo.sh) are BLOCKED
#   outright: subdirectories inside .armature/hooks/ are non-canonical and
#   would otherwise slip past both the TDD convention (no subdir match) and
#   the test-file exemption (cycle-3 MEDIUM-2 fix).
# ---------------------------------------------------------------------------
BASENAME="$(basename "$FILE_PATH")"
REL_PATH_LOWER="${REL_PATH,,}"

case "$REL_PATH_LOWER" in
    .armature/hooks/*.sh)
        # Extract the tail after the prefix to detect subdirectory components.
        _TAIL="${REL_PATH_LOWER#.armature/hooks/}"
        if [[ "$_TAIL" == */* ]]; then
            # Subdir in hooks/ — non-canonical; block with explanatory message.
            cat >&2 <<EOF
BLOCK [TDD-001]: '$REL_PATH' is under .armature/hooks/ but in a subdirectory.
Hook scripts must be top-level in .armature/hooks/ (no subdirectories).
See .armature/ARMATURE.md §5.7.
EOF
            exit 2
        fi
        # Top-level hook script — apply TDD convention using original REL_PATH
        STEM="${BASENAME%.*}"
        STEM_UNDERSCORED="${STEM//-/_}"
        EXPECTED=".armature/tests/test_${STEM_UNDERSCORED}.py"
        if [ -f "$REPO_ROOT/$EXPECTED" ]; then
            exit 0
        fi
        cat >&2 <<EOF
BLOCK [TDD-001]: No test file found for '$REL_PATH'.
Expected one of: $EXPECTED
Write the failing test first, then edit the source.
See .armature/ARMATURE.md §5.7 (GATE-TDD-001).
EOF
        exit 2
        ;;
esac

# ---------------------------------------------------------------------------
# Check 2: Is the file itself a test? → allow
# (Placed AFTER Check 1 so .armature/hooks/test_foo.sh is still gated above.)
# ---------------------------------------------------------------------------
case "$BASENAME" in
    test_*) exit 0 ;;
esac
case "$REL_PATH" in
    */tests/*|*/__tests__/*) exit 0 ;;
    tests/*|__tests__/*) exit 0 ;;
esac

# ---------------------------------------------------------------------------
# Check 3: Exempt extensions → allow
# ---------------------------------------------------------------------------
case "$BASENAME" in
    *.md|*.txt|*.rst|*.yaml|*.yml|*.toml|*.json|*.ini|*.cfg|*.env) exit 0 ;;
esac
# No extension at all (Makefile, Dockerfile, .gitignore, etc.)
case "$BASENAME" in
    *.*) : ;;  # has extension — continue
    *)   exit 0 ;;  # no extension — exempt
esac

# ---------------------------------------------------------------------------
# Convention-based test file lookup
# Extract STEM (filename without extension) and PARENT DIR
# (Done before exempt-path check so that hook-script convention takes
#  precedence over the general .armature/ exemption.)
# ---------------------------------------------------------------------------
STEM="${BASENAME%.*}"
EXT="${BASENAME##*.}"
PARENT_DIR="$(dirname "$REL_PATH")"

# Normalise PARENT_DIR: if it collapses to "." treat as empty
[ "$PARENT_DIR" = "." ] && PARENT_DIR=""

# ---------------------------------------------------------------------------
# Check 4: Exempt path prefixes (all .armature/ except .armature/hooks/*.sh
# which was already handled above) → allow
# ---------------------------------------------------------------------------
case "$REL_PATH" in
    .armature/*) exit 0 ;;
    .claude/*)   exit 0 ;;
    docs/*)      exit 0 ;;
    adr/*)       exit 0 ;;
esac

# ---------------------------------------------------------------------------
# Check 5: Python source convention
#   <dir>/<stem>.py → tests/test_<stem>.py  OR  tests/<dir>/test_<stem>.py
# ---------------------------------------------------------------------------
case "$EXT" in
    py)
        EXPECTED1="tests/test_${STEM}.py"
        if [ -n "$PARENT_DIR" ]; then
            EXPECTED2="tests/${PARENT_DIR}/test_${STEM}.py"
        else
            EXPECTED2="tests/test_${STEM}.py"
        fi
        if [ -f "$REPO_ROOT/$EXPECTED1" ] || [ -f "$REPO_ROOT/$EXPECTED2" ]; then
            exit 0
        fi
        if [ "$EXPECTED1" = "$EXPECTED2" ]; then
            EXPECTED_LIST="$EXPECTED1"
        else
            EXPECTED_LIST="$EXPECTED1 or $EXPECTED2"
        fi
        cat >&2 <<EOF
BLOCK [TDD-001]: No test file found for '$REL_PATH'.
Expected one of: $EXPECTED_LIST
Write the failing test first, then edit the source.
See .armature/ARMATURE.md §5.7 (GATE-TDD-001).
EOF
        exit 2
        ;;
esac

# ---------------------------------------------------------------------------
# Check 6: JS/TS source convention
#   <dir>/<stem>.{ts,js,tsx,jsx,mts,cts,mjs,cjs} →
#     sibling .test.<ext>, .spec.<ext>, or __tests__/<stem>.test.<ext>
#
#   Extensions mts/cts/mjs/cjs are ESM/CJS TypeScript and JavaScript module
#   variants that follow the same test-file naming conventions.
# ---------------------------------------------------------------------------
case "$EXT" in
    ts|js|tsx|jsx|mts|cts|mjs|cjs)
        if [ -n "$PARENT_DIR" ]; then
            EXPECTED1="${PARENT_DIR}/${STEM}.test.${EXT}"
            EXPECTED2="${PARENT_DIR}/${STEM}.spec.${EXT}"
            EXPECTED3="__tests__/${STEM}.test.${EXT}"
        else
            EXPECTED1="${STEM}.test.${EXT}"
            EXPECTED2="${STEM}.spec.${EXT}"
            EXPECTED3="__tests__/${STEM}.test.${EXT}"
        fi
        if [ -f "$REPO_ROOT/$EXPECTED1" ] || \
           [ -f "$REPO_ROOT/$EXPECTED2" ] || \
           [ -f "$REPO_ROOT/$EXPECTED3" ]; then
            exit 0
        fi
        cat >&2 <<EOF
BLOCK [TDD-001]: No test file found for '$REL_PATH'.
Expected one of: $EXPECTED1 or $EXPECTED2 or $EXPECTED3
Write the failing test first, then edit the source.
See .armature/ARMATURE.md §5.7 (GATE-TDD-001).
EOF
        exit 2
        ;;
esac

# ---------------------------------------------------------------------------
# Unknown extension → fail-open
# ---------------------------------------------------------------------------
exit 0
