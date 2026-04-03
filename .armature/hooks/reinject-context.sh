#!/usr/bin/env bash
# Armature reinject-context hook
# Runs at SessionStart after context compaction. Outputs recovery context
# to stdout so the Claude Code runtime re-injects it into the session.
# Always exits 0 — this is an informational hook, not a gate.
#
# Sections emitted:
#   ## Session State           — full contents of session/state.md
#   ## Recent Journal Entries  — last 10 ### sections from journal.md
#   ## Recent Commits          — git log --oneline -5
#   ## Warnings                — dirty-code marker if .code-dirty exists

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ARMATURE_DIR="${REPO_ROOT}/.armature"
STATE="${ARMATURE_DIR}/session/state.md"
JOURNAL="${ARMATURE_DIR}/journal.md"
DIRTY_MARKER="${ARMATURE_DIR}/.code-dirty"

# Resolve python command (python3 preferred, fall back to python)
PYTHON=""
if command -v python3 &>/dev/null; then
  PYTHON="python3"
elif command -v python &>/dev/null; then
  PYTHON="python"
fi

# ---------------------------------------------------------------------------
# Section 1: Session State
# ---------------------------------------------------------------------------
echo "## Session State"
echo ""

if [ ! -f "$STATE" ]; then
  echo "<!-- ${STATE} not found, skipping -->"
else
  cat "$STATE"
fi

echo ""

# ---------------------------------------------------------------------------
# Section 2: Recent Journal Entries (last 10 ### sections)
# ---------------------------------------------------------------------------
echo "## Recent Journal Entries"
echo ""

if [ ! -f "$JOURNAL" ]; then
  echo "<!-- ${JOURNAL} not found, skipping -->"
elif [ -z "$PYTHON" ]; then
  # Fallback without python: grab last ~50 lines which will cover recent entries
  tail -50 "$JOURNAL"
else
  export _REINJECT_JOURNAL="$JOURNAL"
  $PYTHON - <<'PYEOF'
import sys, os

journal = os.environ["_REINJECT_JOURNAL"]
try:
    with open(journal) as f:
        content = f.read()
except Exception as e:
    print(f"<!-- could not read journal.md: {e} -->")
    sys.exit(0)

# Split on ### headers (journal entry delimiters), keep delimiter with its block
import re
parts = re.split(r'(?=^### )', content, flags=re.MULTILINE)

# Filter to non-empty blocks that start with ###
entries = [p for p in parts if p.startswith("###")]

# Take last 10
recent = entries[-10:] if len(entries) > 10 else entries

if not recent:
    print("_No journal entries found._")
else:
    print("".join(recent).rstrip())
PYEOF
fi

echo ""

# ---------------------------------------------------------------------------
# Section 3: Recent Commits
# ---------------------------------------------------------------------------
echo "## Recent Commits"
echo ""

if git rev-parse --git-dir &>/dev/null; then
  git log --oneline -5 2>/dev/null || echo "<!-- git log failed -->"
else
  echo "<!-- not a git repository, skipping -->"
fi

echo ""

# ---------------------------------------------------------------------------
# Section 4: Warnings
# ---------------------------------------------------------------------------
echo "## Warnings"
echo ""

WARNINGS=0

if [ -f "$DIRTY_MARKER" ]; then
  echo "WARNING: Application code has been modified since last test pass. Run tests before completing work."
  WARNINGS=$((WARNINGS + 1))
fi

if [ "$WARNINGS" -eq 0 ]; then
  echo "_No warnings._"
fi

echo ""

exit 0
