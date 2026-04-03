#!/usr/bin/env bash
# Armature mark-dirty hook
# Runs on PostToolUse(Edit|Write) events.
# Reads JSON from stdin with a tool_input.file_path field.
#
# If the modified file is NOT under a governance directory (.armature/, .claude/, docs/),
# touch ${ARMATURE_DIR}/.code-dirty so the post-stop hook knows to run application tests.
#
# Always exits 0 — this is a pure observer that never blocks the tool use.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ARMATURE_DIR="${REPO_ROOT}/.armature"

# Read JSON payload from stdin. Tolerate missing input gracefully.
INPUT="$(cat 2>/dev/null || true)"

# Extract tool_input.file_path from the JSON payload.
# Try python3/python first; fall back to sed when neither is available.
# Falls back to empty string on failure.
FILE_PATH=""
if command -v python3 &>/dev/null; then
  FILE_PATH="$(printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''))
except Exception:
    pass
" 2>/dev/null || true)"
elif command -v python &>/dev/null; then
  FILE_PATH="$(printf '%s' "$INPUT" | python -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''))
except Exception:
    pass
" 2>/dev/null || true)"
fi

# Fallback: extract "file_path" value with sed when Python is unavailable.
if [ -z "$FILE_PATH" ] && [ -n "$INPUT" ]; then
  FILE_PATH=$(printf '%s' "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
fi

# If we could not extract a path, nothing to do.
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Normalise to a path relative to REPO_ROOT so prefix checks are stable.
# Strip leading REPO_ROOT prefix if present, then strip any leading slash.
REL_PATH="${FILE_PATH#"${REPO_ROOT}"}"
REL_PATH="${REL_PATH#/}"

# Governance directory prefixes — changes here do not trigger test runs.
case "$REL_PATH" in
  .armature/*|.claude/*|docs/*)
    # Governance file — do nothing.
    exit 0
    ;;
esac

# Non-governance file was modified. Mark application code as dirty.
touch "${ARMATURE_DIR}/.code-dirty"

exit 0
