#!/usr/bin/env bash
# Armature PreToolUse hook — tier0-preflight
# Event:  PreToolUse(Edit, Write)
# Stdin:  JSON object with a tool_input.file_path field (Claude Code hook payload)
# Invariant: TIER0-001
# Cycle-2 fix: phase file is read via Python to reject NUL bytes and other
# control characters (HIGH finding from m3-cp3 red-team review).
# m3-cp4 polish (LOW-2): stdin payload is read via Python stdin.buffer.read()
#   instead of bash "$(cat)", preserving NUL bytes so the control-char check
#   fires correctly even when file_path contains a NUL byte.
#
# Purpose:
#   Block any Edit/Write to source files when DOMAIN.md and/or PROJECT.md do not
#   exist at the repository root.  Those two tier-0 documents must be created
#   before any substantive source editing begins so that the orchestrator has
#   the required project context for every delegation.
#
# Exempt categories (always allowed, even when tier-0 files are missing):
#   - The tier-0 files themselves  (DOMAIN.md, PROJECT.md)
#   - Governance scaffold paths    (.armature/*, .claude/*, docs/adr/*)
#
# Fail-open conditions (exit 0 without blocking):
#   - Not in a git repo            (cannot determine REPO_ROOT)
#   - Python unavailable           (cannot parse JSON payload)
#   - JSON payload is invalid
#   - tool_input.file_path is absent or empty
#
# Hotfix bypass:
#   If .armature/session/phase contains exactly "Hotfix", the hook emits an
#   advisory and exits 0.  This matches D4 from m3-plan.md.
#
# Exit codes:
#   0  = allow (fail-open, exempt, hotfix-bypass, both tier-0 files present)
#   2  = block (BLOCK [TIER0-001] emitted on stderr)
#
# Cross-platform: works on Git Bash (Windows), bash on Linux, bash on macOS.
# Performance: no external processes beyond python3/python for JSON parse.

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
        sys.stderr.write("BLOCK [TIER0-001]: stdin payload contains NUL byte.\n")
        sys.exit(2)
    data = json.loads(raw)
    fp = data.get("tool_input", {}).get("file_path")
    if fp is None or fp == "":
        print("")
    elif any(ord(c) < 32 for c in fp):
        sys.stderr.write("BLOCK [TIER0-001]: file_path contains control characters.\n")
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
# Compute relative path from REPO_ROOT for exempt-path matching
# Strip trailing separator from REPO_ROOT first for clean prefix removal
# ---------------------------------------------------------------------------
REPO_ROOT_NORM="${REPO_ROOT%/}"
REL_PATH="${FILE_PATH#$REPO_ROOT_NORM/}"

# On Windows under Git Bash, REPO_ROOT uses forward slashes; FILE_PATH after
# normpath may use forward slashes too.  The strip above should work in both
# cases.  If FILE_PATH didn't start with REPO_ROOT (e.g., different drive),
# REL_PATH equals FILE_PATH — the exempt checks below will simply not match
# and the tier-0 gate will run, which is the safe default.

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
        echo "ADVISORY: Hotfix phase active — tier0-preflight bypassed per §7.9." >&2
        exit 0
    fi
fi

# ---------------------------------------------------------------------------
# Exempt-path check — governance scaffold and the tier-0 files themselves
# ---------------------------------------------------------------------------
case "$REL_PATH" in
    DOMAIN.md|PROJECT.md)   exit 0 ;;
    .armature/*)            exit 0 ;;
    .claude/*)              exit 0 ;;
    docs/adr/*)             exit 0 ;;
esac

# ---------------------------------------------------------------------------
# Tier-0 existence check
# ---------------------------------------------------------------------------
MISSING=""
[ ! -f "$REPO_ROOT/DOMAIN.md"  ] && MISSING="DOMAIN.md"
[ ! -f "$REPO_ROOT/PROJECT.md" ] && MISSING="${MISSING:+$MISSING and }PROJECT.md"

if [ -n "$MISSING" ]; then
    cat >&2 <<EOF
BLOCK [TIER0-001]: $MISSING not found at repo root ($REPO_ROOT).
These files must exist before source edits are permitted.
Create: $REPO_ROOT/DOMAIN.md  and  $REPO_ROOT/PROJECT.md
See .armature/ARMATURE.md §5.7 (GATE-TIER0-001).
EOF
    exit 2
fi

exit 0
