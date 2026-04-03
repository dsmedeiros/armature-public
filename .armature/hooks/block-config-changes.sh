#!/usr/bin/env bash
# Armature ConfigChange hook — prevents agents from modifying Claude Code
# configuration that could alter their own governance constraints.
# Wire to Claude Code's ConfigChange lifecycle event.
#
# Stdin: JSON object with a top-level "source" field identifying which
#        configuration store is being modified.
# Exit 2  = block the configuration change
# Exit 0  = allow the configuration change
#
# Blocked sources : user_settings, project_settings, local_settings, skills
# Allowed sources : policy_settings

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# ---------------------------------------------------------------------------
# Parse the source field from stdin JSON.
# Try python first; fall back to sed/grep.
# ---------------------------------------------------------------------------
STDIN_CONTENT="$(cat)"

SOURCE=""
if command -v python3 &>/dev/null; then
  SOURCE="$(printf '%s' "$STDIN_CONTENT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('source', ''))
except Exception:
    pass
")"
elif command -v python &>/dev/null; then
  SOURCE="$(printf '%s' "$STDIN_CONTENT" | python -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('source', ''))
except Exception:
    pass
")"
else
  # Fallback: extract value of "source" key with sed
  SOURCE="$(printf '%s' "$STDIN_CONTENT" | sed -n 's/.*"source"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
fi

# ---------------------------------------------------------------------------
# Helper: emit block message and exit 2
# ---------------------------------------------------------------------------
block() {
  local source_value="$1"
  echo "BLOCK: Agents cannot modify governance configuration via ${source_value}" >&2
  exit 2
}

# ---------------------------------------------------------------------------
# Evaluate the source value (normalise to lowercase for case-insensitive match)
# ---------------------------------------------------------------------------
SOURCE_LOWER="${SOURCE,,}"
case "$SOURCE_LOWER" in
  user_settings|project_settings|local_settings|skills)
    block "$SOURCE"
    ;;
  policy_settings)
    # Explicitly allowed — fall through to exit 0
    ;;
  "")
    # Could not parse source; fail open to avoid false positives
    echo "WARN: block-config-changes.sh could not parse 'source' from stdin; allowing" >&2
    ;;
  *)
    # Unknown source — allow but warn so novel sources are visible in logs
    echo "WARN: block-config-changes.sh encountered unknown source '${SOURCE}'; allowing" >&2
    ;;
esac

exit 0
