#!/usr/bin/env bash
# Armature PreToolUse hook — phase-gate
# Event:  PreToolUse(Edit)
# Stdin:  JSON object with a tool_input.file_path field (Claude Code hook payload)
# Invariant: PHASE-001
# Cycle-2 fix: phase file is read via Python to reject NUL bytes and other
# control characters (HIGH finding from m3-cp3 red-team review).
# m3-cp4 polish (LOW-1): CLAUDE.md/CODEX.md/agents.md/AGENTS.md now classified
#   as governance before the spec-doc check fires, so they are correctly blocked
#   in Review/Release as governance (not spec-doc).
# m3-cp4 polish (LOW-2): stdin payload is read via Python stdin.buffer.read()
#   instead of bash "$(cat)", preserving NUL bytes so the control-char check
#   fires correctly even when file_path contains a NUL byte.
#
# Purpose:
#   Block any Edit to a file when the active SDLC phase does not permit edits
#   to that class of file.  Enforces the phase gate model described in §5.6 and
#   the gate registry entry GATE-PHASE-001 (§5.7).
#
# Check ordering (top → bottom):
#   1. Extract file_path + reject control characters (Python inline)
#   2. Empty file_path → exit 0 (fail-open)
#   3. Get REPO_ROOT via git rev-parse; fail-open if not in repo
#   4. Compute REL_PATH (relative posix-style from REPO_ROOT)
#   5. Read phase from .armature/session/phase; WARN + default Implementation if
#      missing, empty, or unknown
#   6. If phase = Hotfix → exit 0 with ADVISORY (bypass — before classification)
#   7. Classify file into one of 8 classes (Python inline, first-match wins)
#   8. Look up (phase, class) in PERMITTED table
#   9. Allow → exit 0; Block → exit 2 with formatted BLOCK message
#
# Phase permission table:
#   Discovery     : tier0-doc, spec-doc, governance, other
#   Design        : spec-doc, governance, config-file, other
#   Implementation: implementation-code, test-file, hook-script, governance,
#                   config-file, tier0-doc, spec-doc, other
#   Review        : governance, other
#   Release       : governance, config-file, other
#   Hotfix        : BYPASS_ALL (checked in step 6, before classification)
#
# Fail-open conditions (exit 0 without blocking):
#   - Not in a git repo              (cannot determine REPO_ROOT)
#   - Python unavailable             (cannot parse JSON payload)
#   - JSON payload is invalid
#   - tool_input.file_path is absent or empty
#   - Phase file missing or unknown  (WARN emitted; defaults to Implementation)
#
# Hotfix bypass:
#   If .armature/session/phase contains exactly "Hotfix" (case-sensitive), the
#   hook emits an ADVISORY and exits 0.  Checked FIRST, before classification,
#   so no file class can prevent bypass.
#
# Exit codes:
#   0  = allow (fail-open, Hotfix-bypass, or phase permits the file class)
#   2  = block (BLOCK [PHASE-001] emitted on stderr)
#
# Cross-platform: works on Git Bash (Windows), bash on Linux, bash on macOS.
# Performance: no external processes beyond python3/python for JSON parse.

set -euo pipefail

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
        sys.stderr.write("BLOCK [PHASE-001]: stdin payload contains NUL byte.\n")
        sys.exit(2)
    data = json.loads(raw)
    fp = data.get("tool_input", {}).get("file_path")
    if fp is None or fp == "":
        print("")
    elif any(ord(c) < 32 for c in fp):
        sys.stderr.write("BLOCK [PHASE-001]: file_path contains control characters.\n")
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
# Get REPO_ROOT — fail-open if not in a git repo
# ---------------------------------------------------------------------------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
[ -z "$REPO_ROOT" ] && exit 0

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
# Compute REL_PATH (relative posix-style from REPO_ROOT)
# Strip trailing separator from REPO_ROOT first for clean prefix removal.
# On Windows under Git Bash, REPO_ROOT uses forward slashes; normpath may
# use backslashes.  Normalise both to forward slashes for consistent matching.
# ---------------------------------------------------------------------------
REPO_ROOT_NORM="${REPO_ROOT%/}"
REL_PATH="${FILE_PATH#$REPO_ROOT_NORM/}"

# Normalise backslashes to forward slashes (Windows Git Bash safety)
REL_PATH="${REL_PATH//\\//}"

# ---------------------------------------------------------------------------
# Resolve Python interpreter (python3 preferred, python fallback)
# Used for the phase-file reader and classifier below.
# ---------------------------------------------------------------------------
PY=""
if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
fi

# ---------------------------------------------------------------------------
# Read phase from .armature/session/phase
# Missing / empty / unknown → WARN + default Implementation (fail-open).
# Valid values: Discovery, Design, Implementation, Review, Release, Hotfix.
# Comparison is case-sensitive: "Hotfix" triggers bypass; "hotfix" does not.
# ---------------------------------------------------------------------------
PHASE_FILE="$REPO_ROOT/.armature/session/phase"
PHASE="Implementation"  # default

_VALID_PHASES="Discovery Design Implementation Review Release Hotfix"

if [ ! -f "$PHASE_FILE" ]; then
    echo "WARN [PHASE-001]: .armature/session/phase not found — defaulting to Implementation (fail-open)." >&2
elif [ ! -s "$PHASE_FILE" ]; then
    echo "WARN [PHASE-001]: .armature/session/phase is empty — defaulting to Implementation (fail-open)." >&2
else
    # Read phase via Python to reject NUL bytes and other control characters.
    # bash command-substitution silently strips NUL bytes, which allows a file
    # containing "Hot\x00fix" to alias to "Hotfix" and bypass the gate.
    # Python reads raw bytes and rejects any control byte (except tab/LF/CR).
    if [ -n "$PY" ]; then
        _RAW_PHASE="$(
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
    else
        _RAW_PHASE=""
    fi
    # Validate against known phases (case-sensitive)
    _MATCHED=0
    for _VP in $_VALID_PHASES; do
        if [ "$_RAW_PHASE" = "$_VP" ]; then
            PHASE="$_RAW_PHASE"
            _MATCHED=1
            break
        fi
    done
    if [ "$_MATCHED" -eq 0 ]; then
        echo "WARN [PHASE-001]: Unknown phase '${_RAW_PHASE}' — defaulting to Implementation (fail-open)." >&2
    fi
fi

# ---------------------------------------------------------------------------
# Hotfix bypass — FIRST check after phase is known (before file classification)
# ---------------------------------------------------------------------------
if [ "$PHASE" = "Hotfix" ]; then
    echo "ADVISORY: Hotfix phase active — phase-gate bypassed per §7.9." >&2
    exit 0
fi

# ---------------------------------------------------------------------------
# Classify the file into one of 8 classes using Python inline.
# First-match wins. REL_PATH is posix-style relative to REPO_ROOT.
# ---------------------------------------------------------------------------
_PYTHON_CLASSIFY='
import sys

def classify(rel_path):
    # rel_path is relative to repo root, posix-style.
    # lower is used for case-insensitive extension/prefix matching so that
    # paths like src/foo.PY or .armature/HOOKS/foo.sh are classified correctly
    # on case-sensitive filesystems (MEDIUM-1 fix, cycle-2).
    lower = rel_path.lower()
    # Tier-0: exact names or .taskmaster/docs/ prefix (case-sensitive names)
    if rel_path in ("DOMAIN.md", "PROJECT.md") or lower.startswith(".taskmaster/docs/"):
        return "tier0-doc"
    # Governance (top-level adapter files): CLAUDE.md, CODEX.md, agents.md,
    # AGENTS.md are governance files despite being repo-root .md files.  This
    # check runs BEFORE the spec-doc check so these specific files are never
    # mis-classified as spec-doc (LOW-1 fix, m3-cp4 polish pass).
    if rel_path in ("CLAUDE.md", "CODEX.md", "agents.md", "AGENTS.md"):
        return "governance"
    # Spec-doc: docs/adr/ prefix or repo-root .md files (other than tier-0 and
    # the known governance adapter files matched above).
    if lower.startswith("docs/adr/") or (lower.endswith(".md") and "/" not in rel_path):
        return "spec-doc"
    # Hook-script: ANY file under .armature/hooks/ regardless of extension.
    # Backup/temp files (.sh.bak, .sh.tmp, etc.) and subdirectory paths
    # (e.g. .armature/hooks/__tests__/foo.sh) are treated identically to
    # canonical hooks to prevent staging vectors and composition gaps.
    # IMPORTANT: this check is placed BEFORE the test-file check so that
    # __tests__/ inside .armature/hooks/ is classified as hook-script, not
    # test-file (cycle-3 MEDIUM-2 fix).
    if lower.startswith(".armature/hooks/"):
        return "hook-script"
    # Test-file: test dirs or test-named files.
    # "__tests__/" (no leading slash) covers both repo-root and nested paths
    # (MEDIUM-3 fix, cycle-2).
    if (lower.startswith(".armature/tests/") or lower.startswith("tests/")
            or "/test_" in lower or rel_path.startswith("test_")
            or ".test." in lower or "__tests__/" in lower):
        return "test-file"
    # Governance: other .armature/ or .claude/ paths (not already caught by the
    # more-specific hook-script or test-file checks above).
    if lower.startswith(".armature/") or lower.startswith(".claude/"):
        return "governance"
    # Implementation-code: source file extensions (case-insensitive, MEDIUM-1)
    if any(lower.endswith(ext) for ext in (
            ".py", ".js", ".ts", ".tsx", ".jsx", ".mts", ".cts", ".mjs", ".cjs",
            ".go", ".rs", ".java", ".rb", ".c", ".cpp", ".h", ".hpp")):
        return "implementation-code"
    # Config-file: configuration file extensions (case-insensitive, MEDIUM-1)
    if any(lower.endswith(ext) for ext in (
            ".yaml", ".yml", ".toml", ".json", ".ini", ".cfg", ".env")):
        return "config-file"
    return "other"

print(classify(sys.argv[1]))
'

FILE_CLASS=""
if command -v python3 >/dev/null 2>&1; then
    FILE_CLASS="$(python3 -c "$_PYTHON_CLASSIFY" "$REL_PATH" 2>/dev/null || echo "")"
elif command -v python >/dev/null 2>&1; then
    FILE_CLASS="$(python -c "$_PYTHON_CLASSIFY" "$REL_PATH" 2>/dev/null || echo "")"
fi

# If classification failed (python unavailable), fail-open
[ -z "$FILE_CLASS" ] && exit 0

# ---------------------------------------------------------------------------
# Phase permission lookup
# PERMITTED maps phase → set of allowed file classes.
# "other" is allowed in all non-Hotfix phases (Hotfix is already bypassed above).
# ---------------------------------------------------------------------------
_PYTHON_PERMIT='
import sys

PERMITTED = {
    "Discovery":      {"tier0-doc", "spec-doc", "governance", "other"},
    "Design":         {"spec-doc", "governance", "config-file", "other"},
    "Implementation": {"implementation-code", "test-file", "hook-script",
                       "governance", "config-file", "tier0-doc", "spec-doc", "other"},
    "Review":         {"governance", "other"},
    "Release":        {"governance", "config-file", "other"},
}

# Which phases permit a given class
def permitted_phases_for(cls):
    return [ph for ph, allowed in PERMITTED.items() if cls in allowed]

phase     = sys.argv[1]
file_cls  = sys.argv[2]
rel_path  = sys.argv[3]

allowed = PERMITTED.get(phase, set())
if file_cls in allowed:
    sys.exit(0)

# Build permitted-phases list for BLOCK message
pp = permitted_phases_for(file_cls)
pp_str = ", ".join(pp) if pp else "(none)"

sys.stderr.write(
    f"BLOCK [PHASE-001]: Edit to '"'"'{rel_path}'"'"' (class: {file_cls}) is not permitted in phase '"'"'{phase}'"'"'.\n"
    f"Permitted phases for class '"'"'{file_cls}'"'"': {pp_str}.\n"
    f"The orchestrator updates .armature/session/phase and records transitions in .armature/journal.md.\n"
    f"See .armature/ARMATURE.md §5.6.\n"
)
sys.exit(2)
'

_PERMIT_RC=0
if command -v python3 >/dev/null 2>&1; then
    python3 -c "$_PYTHON_PERMIT" "$PHASE" "$FILE_CLASS" "$REL_PATH" || _PERMIT_RC=$?
elif command -v python >/dev/null 2>&1; then
    python -c "$_PYTHON_PERMIT" "$PHASE" "$FILE_CLASS" "$REL_PATH" || _PERMIT_RC=$?
fi

exit "$_PERMIT_RC"
