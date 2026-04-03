#!/usr/bin/env bash
# Armature inject-context hook
# Runs at SubagentStart. Outputs governance context to stdout so the
# Claude Code runtime injects it into the subagent's context window.
# Always exits 0 — this is an informational hook, not a gate.
#
# Sections emitted:
#   ## Active Invariants  — parsed from registry.yaml (status: active entries)
#   ## Session State      — extracted sections from session/state.md
#   ## Scope Context      — frontmatter of nearest agents.md for the scope

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ARMATURE_DIR="${REPO_ROOT}/.armature"
REGISTRY="${ARMATURE_DIR}/invariants/registry.yaml"
STATE="${ARMATURE_DIR}/session/state.md"

# Resolve python command (python3 preferred, fall back to python)
PYTHON=""
if command -v python3 &>/dev/null; then
  PYTHON="python3"
elif command -v python &>/dev/null; then
  PYTHON="python"
fi

# ---------------------------------------------------------------------------
# Section 1: Active Invariants
# ---------------------------------------------------------------------------
echo "## Active Invariants"
echo ""

if [ ! -f "$REGISTRY" ]; then
  echo "<!-- ${REGISTRY} not found, skipping -->"
elif [ -z "$PYTHON" ]; then
  echo "<!-- python not available; cannot parse registry.yaml -->"
else
  export _INJECT_REGISTRY="$REGISTRY"
  $PYTHON - <<'PYEOF'
import sys, os
try:
    import yaml
except ImportError:
    print("<!-- pyyaml not available; cannot parse registry.yaml -->")
    sys.exit(0)

registry = os.environ["_INJECT_REGISTRY"]
try:
    with open(registry) as f:
        data = yaml.safe_load(f)
except Exception as e:
    print(f"<!-- failed to parse registry.yaml: {e} -->")
    sys.exit(0)

invariants = data.get("invariants", {})
active = {k: v for k, v in invariants.items() if v.get("status") == "active"}

if not active:
    print("_No active invariants found._")
else:
    for inv_id, inv in sorted(active.items()):
        severity = inv.get("severity", "unknown")
        rule = inv.get("rule", inv.get("description", ""))
        print(f"- **{inv_id}** ({severity}): {rule}")
PYEOF
fi

echo ""

# ---------------------------------------------------------------------------
# Section 2: Session State
# ---------------------------------------------------------------------------
echo "## Session State"
echo ""

if [ ! -f "$STATE" ]; then
  echo "<!-- ${STATE} not found, skipping -->"
else
  if [ -z "$PYTHON" ]; then
    # Fallback: emit full file if no python to parse sections
    cat "$STATE"
  else
    export _INJECT_STATE="$STATE"
    $PYTHON - <<'PYEOF'
import re, sys, os

target_sections = [
    "Current Objective",
    "Active Delegation",
    "Invariants Touched",
]

state = os.environ["_INJECT_STATE"]
try:
    with open(state) as f:
        content = f.read()
except Exception as e:
    print(f"<!-- could not read state.md: {e} -->")
    sys.exit(0)

# Split on ## headings
blocks = re.split(r'(?=^## )', content, flags=re.MULTILINE)

found = []
for block in blocks:
    for section in target_sections:
        if block.startswith(f"## {section}"):
            found.append(block.rstrip())
            break

if found:
    print("\n\n".join(found))
else:
    print("_No relevant session state sections found._")
PYEOF
  fi
fi

echo ""

# ---------------------------------------------------------------------------
# Section 3: Scope Context
# ---------------------------------------------------------------------------
echo "## Scope Context"
echo ""

# Read scope hint from stdin JSON (best-effort; non-fatal if absent or malformed)
STDIN_JSON=""
if [ ! -t 0 ]; then
  STDIN_JSON="$(cat)"
fi

if [ -z "$PYTHON" ]; then
  echo "<!-- python not available; cannot determine scope context -->"
else
  # Pass values via environment to keep heredoc quoted (suppresses backtick expansion)
  export _INJECT_REPO_ROOT="$REPO_ROOT"
  export _INJECT_STDIN_JSON="$STDIN_JSON"
  $PYTHON - <<'PYEOF'
import json, os, sys

repo_root = os.environ.get("_INJECT_REPO_ROOT", "")
stdin_json = os.environ.get("_INJECT_STDIN_JSON", "")

# Try to extract a file path or scope hint from the stdin JSON
candidate_path = None
if stdin_json.strip():
    try:
        data = json.loads(stdin_json)
        # Common fields that may carry a file or directory hint
        for key in ("file", "path", "scope", "cwd", "workingDirectory"):
            val = data.get(key)
            if val and isinstance(val, str):
                candidate_path = val
                break
    except Exception:
        pass

# Walk up from candidate_path (or repo_root) to find nearest agents.md
search_dir = candidate_path if candidate_path else repo_root
if not os.path.isdir(search_dir):
    search_dir = os.path.dirname(search_dir)

agents_file = None
current = os.path.abspath(search_dir)
while True:
    probe = os.path.join(current, "agents.md")
    if os.path.isfile(probe):
        agents_file = probe
        break
    parent = os.path.dirname(current)
    if parent == current:
        break
    current = parent

if not agents_file:
    print("<!-- no agents.md found in scope path hierarchy, skipping -->")
    sys.exit(0)

try:
    with open(agents_file) as f:
        content = f.read()
except Exception as e:
    print(f"<!-- could not read {agents_file}: {e} -->")
    sys.exit(0)

# Extract YAML frontmatter only
if not content.startswith("---"):
    print(f"<!-- {agents_file} has no frontmatter, skipping -->")
    sys.exit(0)

end = content.find("---", 3)
if end < 0:
    print(f"<!-- {agents_file} frontmatter not closed, skipping -->")
    sys.exit(0)

frontmatter_raw = content[3:end].strip()

# Parse and re-emit only governance-relevant fields
try:
    import yaml
    fm = yaml.safe_load(frontmatter_raw)
except Exception:
    fm = None

rel_path = os.path.relpath(agents_file, repo_root)
print(f"_Source: {rel_path}_")
print("")

if fm and isinstance(fm, dict):
    for field in ("scope", "governs", "adrs", "invariants", "restricted"):
        val = fm.get(field)
        if val is not None:
            print(f"**{field}:** {val}")
else:
    # Emit raw frontmatter if YAML parse failed
    print("```yaml")
    print(frontmatter_raw)
    print("```")
PYEOF
fi

echo ""

exit 0
