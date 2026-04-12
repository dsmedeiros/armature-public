#!/usr/bin/env bash
# Armature post-stop hook
# Runs deterministic checks after a Claude Code session or subagent completes.
# Wire to Claude Code's Stop and SubagentStop lifecycle events, or run manually
# from other runtimes such as Codex before handoff.
#
# These are mechanical checks — no LLM judgment. They validate structural
# integrity of the governance scaffold and basic code hygiene.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ARMATURE_DIR="${REPO_ROOT}/.armature"
REGISTRY="${ARMATURE_DIR}/invariants/registry.yaml"
EXIT_CODE=0

# Resolve python command (python3 preferred, fall back to python)
PYTHON=""
if command -v python3 &>/dev/null; then
  PYTHON="python3"
elif command -v python &>/dev/null; then
  PYTHON="python"
fi

echo "=== Armature Post-Stop Validation ==="

check_adapter_routes() {
  local adapter_name="$1"
  local adapter_path="$2"
  local found_refs=0
  local route_fail=0

  if [ ! -f "$adapter_path" ]; then
    return
  fi

  while IFS= read -r ref; do
    [ -z "$ref" ] && continue
    found_refs=1
    agents_path="${REPO_ROOT}/${ref}"
    if [ ! -f "$agents_path" ]; then
      echo "FAIL: ${adapter_name} references ${ref} but file does not exist"
      EXIT_CODE=1
      route_fail=1
    fi
  done < <(grep -oE '`[^`]*agents\.md`' "$adapter_path" | tr -d '`' | sort -u)

  if [ "$found_refs" -eq 1 ] && [ "$route_fail" -eq 0 ]; then
    echo "PASS: ${adapter_name} routing references resolve"
  else
    if [ "$found_refs" -eq 0 ]; then
      echo "SKIP: ${adapter_name} has no routed agents.md references"
    fi
  fi
}

# 1. Check that all agents.md files referenced in tool adapters exist
check_adapter_routes "CLAUDE.md" "${REPO_ROOT}/CLAUDE.md"
check_adapter_routes "CODEX.md" "${REPO_ROOT}/CODEX.md"

# 2. Check that the invariant registry is valid YAML (if python is available)
if [ -f "$REGISTRY" ]; then
  if [ -n "$PYTHON" ]; then
    export _POSTSTOP_REGISTRY="$REGISTRY"
    $PYTHON - <<'PYEOF' || EXIT_CODE=1
import yaml, sys, os
registry = os.environ["_POSTSTOP_REGISTRY"]
try:
    with open(registry) as f:
        yaml.safe_load(f)
    print('PASS: Invariant registry is valid YAML')
except Exception as e:
    print(f'FAIL: Invariant registry has invalid YAML: {e}')
    sys.exit(1)
PYEOF
  else
    echo "SKIP: No python available to validate registry YAML"
  fi
fi

# 3. Check for uncommitted governance file changes without session log entries
GOVERNANCE_FILES=$(git diff --name-only HEAD 2>/dev/null | grep -E '(agents\.md|CLAUDE\.md|CODEX\.md|registry\.yaml|invariants\.md|docs/adr/)' || true)
if [ -n "$GOVERNANCE_FILES" ]; then
  echo "WARN: Uncommitted governance file changes detected:"
  echo "$GOVERNANCE_FILES"
  echo "  Ensure these changes are logged in .armature/session/state.md"
fi

# 4. Check that no agents.md frontmatter references non-existent ADRs
if [ -n "$PYTHON" ]; then
  export _POSTSTOP_REPO_ROOT="$REPO_ROOT"
  $PYTHON - <<'PYEOF' || EXIT_CODE=1
import os, re, sys, glob

repo_root = os.environ["_POSTSTOP_REPO_ROOT"]
exit_code = 0

# Use os.walk so dot-directories (.armature/, .claude/) are traversed.
# glob.glob with ** skips directories starting with '.' by default.
agents_files = []
for dirpath, dirnames, filenames in os.walk(repo_root):
    for filename in filenames:
        if filename.lower() == 'agents.md':
            agents_files.append(os.path.join(dirpath, filename))

checked = 0
for agents_file in agents_files:
    with open(agents_file) as f:
        content = f.read()
    # Extract frontmatter
    if content.startswith('---'):
        end = content.find('---', 3)
        if end > 0:
            frontmatter = content[3:end]
            adrs = re.findall(r'ADR-(\d+)', frontmatter)
            for adr_num in adrs:
                checked += 1
                adr_dir = os.path.join(repo_root, 'docs', 'adr')
                # Try multiple naming conventions, stopping at first match:
                #   1. {num}-*         e.g. 0001-governance-as-files.md
                #   2. ADR-{num}*      e.g. ADR-0001-something.md
                #   3. *{num}*         fallback
                patterns = [
                    os.path.join(adr_dir, f'{adr_num}-*'),
                    os.path.join(adr_dir, f'ADR-{adr_num}*'),
                    os.path.join(adr_dir, f'*{adr_num}*'),
                ]
                found = any(glob.glob(p) for p in patterns)
                if not found:
                    rel_path = os.path.relpath(agents_file, repo_root)
                    print(f'FAIL: {rel_path} references ADR-{adr_num} but no matching ADR file found')
                    exit_code = 1

if exit_code == 0:
    print(f'PASS: All ADR references in agents.md frontmatter resolve ({checked} reference(s) checked across {len(agents_files)} file(s))')
sys.exit(exit_code)
PYEOF
fi

# 5. If application code was modified (dirty marker exists), run project tests
DIRTY_MARKER="${ARMATURE_DIR}/.code-dirty"
if [ -f "$DIRTY_MARKER" ]; then
  TEST_RUNNER=""
  TEST_CMD=""

  # Detection order: pytest, npm test, make test
  if [ -d "${REPO_ROOT}/tests" ] && command -v python3 &>/dev/null; then
    TEST_RUNNER="pytest"
    TEST_CMD="python3 -m pytest -x --tb=short -q"
  elif [ -d "${REPO_ROOT}/tests" ] && command -v python &>/dev/null; then
    TEST_RUNNER="pytest"
    TEST_CMD="python -m pytest -x --tb=short -q"
  elif [ -f "${REPO_ROOT}/package.json" ] && command -v npm &>/dev/null; then
    if _POSTSTOP_PKG="${REPO_ROOT}/package.json" $PYTHON - <<'PYEOF' 2>/dev/null
import json, os, sys
pkg = os.environ["_POSTSTOP_PKG"]
d = json.load(open(pkg))
sys.exit(0 if 'test' in d.get('scripts', {}) else 1)
PYEOF
    then
      TEST_RUNNER="npm"
      TEST_CMD="npm test"
    fi
  elif [ -f "${REPO_ROOT}/Makefile" ]; then
    if grep -qE '^test[[:space:]]*:' "${REPO_ROOT}/Makefile" 2>/dev/null; then
      TEST_RUNNER="make"
      TEST_CMD="make test"
    fi
  fi

  if [ -n "$TEST_RUNNER" ]; then
    echo "INFO: Running application tests via ${TEST_RUNNER}..."
    if (cd "${REPO_ROOT}" && $TEST_CMD 2>&1); then
      rm -f "$DIRTY_MARKER"
      echo "PASS: Application tests passed"
    else
      echo "FAIL: Application tests failed"
      EXIT_CODE=1
    fi
  else
    echo "SKIP: No test runner detected, removing dirty marker"
    rm -f "$DIRTY_MARKER"
  fi
else
  echo "SKIP: No application code changes detected"
fi

echo "=== Armature Validation Complete (exit: ${EXIT_CODE}) ==="
exit $EXIT_CODE
