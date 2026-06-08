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

  # Pre-process the adapter to drop markdown table HEADER rows. A header
  # row is the line immediately preceding a separator row of the form
  # `|---|---|...|` (optional ':' for alignment, optional surrounding
  # whitespace). Without this, an adapter that uses the documented
  # `| Scope | `agents.md` | ADRs | Implementer |` table header (see
  # .armature/templates/CODEX.md.tmpl) would have its column LABEL
  # `agents.md` extracted as a route and validated as a missing file.
  #
  # awk one-pass with one-line buffer: when we see a separator row,
  # drop the buffered prior line (the header) and the separator itself;
  # otherwise emit the buffered prior line and re-buffer the current.
  local _adapter_no_header
  _adapter_no_header="$(awk '
    /^[[:space:]]*\|[-: |]+\|[[:space:]]*$/ { prev=""; next }
    { if (prev != "") print prev; prev=$0 }
    END { if (prev != "") print prev }
  ' "$adapter_path")"

  # Two-pattern extraction to distinguish routing-table entries from
  # prose mentions of agents.md (operating on the header-stripped text):
  #
  #   1. Path-style refs anywhere (`<dir>/agents.md`): cover scoped
  #      governance files like `.armature/agents.md` or
  #      `.claude/commands/agents.md`. The required '/' excludes bare
  #      prose mentions like CODEX.md line 12 ("Codex will only read
  #      `AGENTS.md`").
  #
  #   2. Bare `agents.md` ONLY inside markdown table data rows (lines
  #      starting with '|'): covers legitimate root-level governance
  #      routes that a routing table may declare without a directory
  #      prefix. Prose mentions appear in narrative paragraphs, not
  #      table cells; header-row labels are removed by the awk pass
  #      above. .armature/ARMATURE.md requires every referenced
  #      governance file — including any root agents.md/AGENTS.md — to
  #      exist, so the route validator must handle this case.
  #
  # Each grep is guarded with `|| true` so a no-match exit (grep
  # returns 1) does NOT abort the brace group under set -euo pipefail.
  # Either branch may legitimately have zero matches in an adapter that
  # uses only the OTHER style of route. Output is unioned and deduped.
  while IFS= read -r ref; do
    [ -z "$ref" ] && continue
    found_refs=1
    agents_path="${REPO_ROOT}/${ref}"
    if [ ! -f "$agents_path" ]; then
      echo "FAIL: ${adapter_name} references ${ref} but file does not exist"
      EXIT_CODE=1
      route_fail=1
    fi
  done < <(
    {
      printf '%s\n' "$_adapter_no_header" \
        | grep -oEi '`[^`]*/agents\.md`' || true
      # Allow optional leading whitespace before the leading '|' so
       # indented markdown tables (common in nested-list contexts) are
       # also recognized. Matches the awk header-stripping pattern which
       # already accepts '^[[:space:]]*\|...'.
      ( printf '%s\n' "$_adapter_no_header" \
          | grep -nEi '^[[:space:]]*\|.*`[^`/]*agents\.md`.*\|' \
          | grep -oEi '`[^`/]*agents\.md`' ) || true
    } | tr -d '`' | sort -u
  )

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
import sys, os
try:
    import yaml
except ImportError:
    print('SKIP: PyYAML not available; cannot validate invariant registry YAML')
    sys.exit(0)
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

# 3. Validate disciplines/triggers.yaml (if it exists and python is available)
TRIGGERS_YAML="${ARMATURE_DIR}/disciplines/triggers.yaml"
if [ -f "$TRIGGERS_YAML" ] && [ -n "$PYTHON" ]; then
  export _POSTSTOP_TRIGGERS_YAML="$TRIGGERS_YAML"
  export _POSTSTOP_DISCIPLINES_DIR="${ARMATURE_DIR}/disciplines"
  # Note: this block intentionally uses EXIT_CODE=2 (not 1) to signal a
  # blocking governance error distinct from ordinary validator failures
  # (which use EXIT_CODE=1). The disciplines validator's Python explicitly
  # uses sys.exit(2) to preserve the distinction. Callers that want a
  # uniform non-zero check should test `[ $? -ne 0 ]`; callers that want
  # to distinguish blocking from warning failures can test for the exact
  # exit code.
  $PYTHON - <<'PYEOF' || EXIT_CODE=2
import sys, os, re
try:
    import yaml
except ImportError:
    print('SKIP: PyYAML not available; cannot validate disciplines/triggers.yaml')
    sys.exit(0)

triggers_path = os.environ["_POSTSTOP_TRIGGERS_YAML"]
disciplines_dir = os.environ["_POSTSTOP_DISCIPLINES_DIR"]
exit_code = 0

VALID_SEVERITIES = {"critical", "high", "standard"}
VALID_COMP_MODES = {"strict", "advisory"}
VALID_TRIGGER_TYPES = {"path", "invariant", "content", "explicit"}

# Allowed discipline ID pattern: lowercase alphanumeric and hyphens only,
# must start with alphanumeric.  Prevents path traversal (LOW-3).
ID_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]*$')

# --- Parse triggers.yaml ---
try:
    with open(triggers_path) as f:
        data = yaml.safe_load(f)
except Exception as e:
    print(f"FAIL: disciplines/triggers.yaml has invalid YAML: {e}")
    sys.exit(2)

triggers = data.get("triggers", {}) if isinstance(data, dict) else {}
if not isinstance(triggers, dict):
    print("FAIL: disciplines/triggers.yaml: 'triggers' key must be a mapping")
    sys.exit(2)

# --- Validate each discipline ID against safe pattern before any path ops ---
for discipline_id in list(triggers.keys()):
    if not ID_PATTERN.match(str(discipline_id)):
        print(f"FAIL: triggers.yaml: discipline ID '{discipline_id}' is invalid (must match [a-z0-9][a-z0-9-]*)")
        sys.exit(2)

# --- Validate each entry ---
for discipline_id, entry in triggers.items():
    if not isinstance(entry, dict):
        print(f"FAIL: triggers.yaml: entry '{discipline_id}' must be a mapping")
        exit_code = 2
        continue

    # Referential integrity: discipline file must exist
    disc_file = os.path.join(disciplines_dir, f"{discipline_id}.md")
    if not os.path.isfile(disc_file):
        print(f"FAIL: triggers.yaml references '{discipline_id}' but .armature/disciplines/{discipline_id}.md does not exist")
        exit_code = 2

    # severity must be from allowed set
    severity = entry.get("severity", "")
    if severity not in VALID_SEVERITIES:
        print(f"FAIL: triggers.yaml '{discipline_id}': invalid severity '{severity}' (must be one of {sorted(VALID_SEVERITIES)})")
        exit_code = 2

    # composition-mode must be from allowed set
    comp_mode = entry.get("composition-mode", "")
    if comp_mode not in VALID_COMP_MODES:
        print(f"FAIL: triggers.yaml '{discipline_id}': invalid composition-mode '{comp_mode}' (must be one of {sorted(VALID_COMP_MODES)})")
        exit_code = 2

    # triggers list: each type must be from allowed set
    for trig in entry.get("triggers", []):
        if not isinstance(trig, dict):
            print(f"FAIL: triggers.yaml '{discipline_id}': trigger entry must be a mapping")
            exit_code = 2
            continue
        trig_type = trig.get("type", "")
        if trig_type not in VALID_TRIGGER_TYPES:
            print(f"FAIL: triggers.yaml '{discipline_id}': invalid trigger type '{trig_type}' (must be one of {sorted(VALID_TRIGGER_TYPES)})")
            exit_code = 2

    # Cross-check: triggers.yaml severity must match discipline frontmatter severity
    if os.path.isfile(disc_file):
        with open(disc_file) as f:
            fm_text = f.read()
        fm_severity = None
        fm_comp_mode = None
        if fm_text.startswith("---"):
            end = fm_text.find("---", 3)
            if end > 0:
                fm = fm_text[3:end]
                m = re.search(r"severity:\s*(\S+)", fm)
                if m:
                    fm_severity = m.group(1)
                m = re.search(r"composition-mode:\s*(\S+)", fm)
                if m:
                    fm_comp_mode = m.group(1)

        if fm_severity is not None and severity and severity != fm_severity:
            print(f"FAIL: triggers.yaml '{discipline_id}': severity '{severity}' does not match discipline frontmatter severity '{fm_severity}'")
            exit_code = 2

        if fm_comp_mode is not None and comp_mode and comp_mode != fm_comp_mode:
            print(f"FAIL: triggers.yaml '{discipline_id}': composition-mode '{comp_mode}' does not match discipline frontmatter composition-mode '{fm_comp_mode}'")
            exit_code = 2

# --- Validate discipline frontmatter enums (carry-forward from CP1 review) ---
for fname in os.listdir(disciplines_dir):
    if not fname.endswith(".md"):
        continue
    disc_path = os.path.join(disciplines_dir, fname)
    with open(disc_path) as f:
        text = f.read()
    if not text.startswith("---"):
        continue
    end = text.find("---", 3)
    if end <= 0:
        continue
    fm = text[3:end]
    m_sev = re.search(r"severity:\s*(\S+)", fm)
    m_comp = re.search(r"composition-mode:\s*(\S+)", fm)
    disc_id = fname[:-3]

    if m_sev:
        fm_sev = m_sev.group(1)
        if fm_sev not in VALID_SEVERITIES:
            print(f"FAIL: {fname} frontmatter: invalid severity '{fm_sev}' (must be one of {sorted(VALID_SEVERITIES)})")
            exit_code = 2

    if m_comp:
        fm_comp = m_comp.group(1)
        if fm_comp not in VALID_COMP_MODES:
            print(f"FAIL: {fname} frontmatter: invalid composition-mode '{fm_comp}' (must be one of {sorted(VALID_COMP_MODES)})")
            exit_code = 2

if exit_code == 0:
    print(f"PASS: disciplines/triggers.yaml is valid ({len(triggers)} discipline(s) checked)")
sys.exit(exit_code)
PYEOF
fi

# 4. GC stale active-delegations correlation files (TASK-002, >24h)
# Advisory-only: any Python-level failure (e.g., TOCTOU on os.listdir) must
# NOT propagate to post-stop's exit code under `set -euo pipefail`. The
# `|| true` tail ensures GC failures stay warnings.
if [ -n "$PYTHON" ]; then
  export _POSTSTOP_REPO_ROOT="$REPO_ROOT"
  $PYTHON - <<'PYEOF' || true
import os, sys, time

repo_root = os.environ["_POSTSTOP_REPO_ROOT"]
GC_THRESHOLD_SECONDS = 24 * 3600
deleg_dir = os.path.join(repo_root, ".armature", "session", "active-delegations")
if os.path.isdir(deleg_dir):
    now = time.time()
    try:
        entries = os.listdir(deleg_dir)
    except OSError as e:
        print(f"WARN: post-stop.sh could not list active-delegations/: {e}")
        sys.exit(0)
    for entry in entries:
        if not entry.endswith(".json"):
            continue
        full = os.path.join(deleg_dir, entry)
        try:
            mtime = os.path.getmtime(full)
            if now - mtime > GC_THRESHOLD_SECONDS:
                os.remove(full)
                print(f"WARN: post-stop.sh removed stale correlation file {entry} (>24h)")
        except OSError as e:
            print(f"WARN: post-stop.sh could not GC {entry}: {e}")
PYEOF
fi

# 5. Check for uncommitted governance file changes without session log entries
GOVERNANCE_FILES=$(git diff --name-only HEAD 2>/dev/null | grep -E '(agents\.md|CLAUDE\.md|CODEX\.md|registry\.yaml|invariants\.md|docs/adr/)' || true)
if [ -n "$GOVERNANCE_FILES" ]; then
  echo "WARN: Uncommitted governance file changes detected:"
  echo "$GOVERNANCE_FILES"
  echo "  Ensure these changes are logged in .armature/session/state.md"
fi

# 6. Check that no agents.md frontmatter references non-existent ADRs
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

# 7. If application code was modified (dirty marker exists), run project tests
#
# Governance vs. application code classification (HOOK-003):
#   mark-dirty.sh sets .code-dirty only for files NOT under a governance prefix
#   (.armature/, .claude/, docs/, CLAUDE.md, CODEX.md, ARMATURE.md, etc.).
#   Therefore .armature/tests/ — being under .armature/ — is classified as
#   governance and does NOT trigger .code-dirty when test files are edited.
#   This is intentional: hook tests are governance artifacts, not application code.
#   The hook-tests CI job (governance.yml) is the authoritative test gate for them.
DIRTY_MARKER="${ARMATURE_DIR}/.code-dirty"
if [ -f "$DIRTY_MARKER" ]; then
  TEST_RUNNER=""
  # TEST_CMD is a bash ARRAY (not a string) so package directory paths
  # containing spaces survive the eventual `"${TEST_CMD[@]}"` expansion
  # without word-splitting on the embedded space.
  TEST_CMD=()

  # Detection order: pytest, npm test, make test
  # Probe for a Python test layout in this priority:
  #   1. Repo-root tests/                  e.g. /repo/tests/
  #   2. One-level package-local           e.g. /repo/cwt-sim/tests/
  #   3. Two-level monorepo workspace      e.g. /repo/packages/foo/tests/
  #                                             /repo/apps/foo/tests/
  #                                             /repo/services/foo/tests/
  # The original implementation only handled (1) and (2); (3) covers the
  # common monorepo workspace layout where packages/, apps/, or services/
  # is the parent of the actual package directories. Python edits in any
  # of these layouts now route to pytest scoped to the detected package
  # rather than falling through to npm/make. .armature/tests/ is
  # deliberately not matched — it is governance, not application.
  # Helper: returns 0 (true) only if the directory contains at least one
  # .py file recursively. A `tests/` directory full of *.ts/*.js (e.g.
  # vitest/jest fixtures) would otherwise make this hook claim a Python
  # layout, run pytest against it, and get exit 5 (no tests collected) —
  # blocking the smoke check despite a working npm runner being one branch
  # below.
  _has_py_files() {
    local dir="$1"
    [ -d "$dir" ] || return 1
    # Use find -quit to short-circuit after the first match. Fall back to
    # a glob if find is unavailable (extremely rare; bash hosts always have
    # find). 2>/dev/null swallows permission-denied noise on locked subdirs.
    if command -v find >/dev/null 2>&1; then
      find "$dir" -name '*.py' -print -quit 2>/dev/null | grep -q .
    else
      compgen -G "${dir}/**/*.py" >/dev/null 2>&1
    fi
  }

  PY_TESTS_FOUND=""
  PY_TESTS_PATH=""
  if [ -d "${REPO_ROOT}/tests" ] && _has_py_files "${REPO_ROOT}/tests"; then
    PY_TESTS_FOUND="repo-root"
    PY_TESTS_PATH="tests"
  else
    for top_dir in "${REPO_ROOT}"/*/; do
      # Skip framework / governance / build-tooling directories that should
      # never be probed as application package roots. Aligned with
      # mark-dirty.sh's governance classification (which excludes these
      # paths from triggering .code-dirty): .armature/, .claude/, docs/
      # are governance scope, .git/ is VCS metadata, node_modules/ is
      # package-manager cache. docs/tests/<*.py> is documentation test
      # tooling, not application code.
      case "${top_dir%/}" in
        "${REPO_ROOT}/.armature"|"${REPO_ROOT}/.claude"|"${REPO_ROOT}/.git"|"${REPO_ROOT}/node_modules"|"${REPO_ROOT}/docs") continue ;;
      esac
      # (2) One-level: <top>/tests/ — must contain Python files.
      if [ -d "${top_dir}tests" ] && _has_py_files "${top_dir}tests"; then
        PY_TESTS_FOUND="package-local"
        # Strip the REPO_ROOT prefix and the trailing slash from top_dir,
        # then append "tests". This produces e.g. "cwt-sim/tests" or
        # "myapp/tests" so pytest is scoped to the detected package and
        # does NOT collect unrelated sibling test trees (which may have
        # collection errors or use a different test framework, e.g.
        # jest's __tests__).
        pkg_rel="${top_dir#${REPO_ROOT}/}"
        pkg_rel="${pkg_rel%/}"
        PY_TESTS_PATH="${pkg_rel}/tests"
        break
      fi
      # (3) Two-level monorepo workspace: only descend into directories
      # whose name matches a known workspace root. This avoids globbing
      # every package's contents (slow on large monorepos) and prevents
      # accidental matches in unrelated subdirs. Same Python-files
      # requirement applies — a JS-only workspace package is skipped so
      # the detector falls through to the npm branch below.
      case "${top_dir%/}" in
        "${REPO_ROOT}/packages"|"${REPO_ROOT}/apps"|"${REPO_ROOT}/services")
          for sub_dir in "${top_dir}"*/; do
            if [ -d "${sub_dir}tests" ] && _has_py_files "${sub_dir}tests"; then
              PY_TESTS_FOUND="workspace-local"
              pkg_rel="${sub_dir#${REPO_ROOT}/}"
              pkg_rel="${pkg_rel%/}"
              PY_TESTS_PATH="${pkg_rel}/tests"
              break 2
            fi
          done
          ;;
      esac
    done
  fi

  # Scope pytest to the detected tree (PY_TESTS_PATH) so we don't accidentally
  # collect unrelated trees (e.g. baselines/__tests__/ jest files) that fail
  # collection when invoked from repo root. Quote PY_TESTS_PATH so package
  # directories whose names contain spaces (e.g. "my package/tests") are
  # passed as a single argument to pytest, not word-split.
  if [ -n "$PY_TESTS_FOUND" ] && command -v python3 &>/dev/null; then
    TEST_RUNNER="pytest"
    TEST_CMD=(python3 -m pytest "${PY_TESTS_PATH}" -x --tb=short -q)
  elif [ -n "$PY_TESTS_FOUND" ] && command -v python &>/dev/null; then
    TEST_RUNNER="pytest"
    TEST_CMD=(python -m pytest "${PY_TESTS_PATH}" -x --tb=short -q)
  elif [ -f "${REPO_ROOT}/package.json" ] && command -v npm &>/dev/null; then
    if _POSTSTOP_PKG="${REPO_ROOT}/package.json" $PYTHON - <<'PYEOF' 2>/dev/null
import json, os, sys
pkg = os.environ["_POSTSTOP_PKG"]
d = json.load(open(pkg))
sys.exit(0 if 'test' in d.get('scripts', {}) else 1)
PYEOF
    then
      TEST_RUNNER="npm"
      TEST_CMD=(npm test)
    fi
  elif [ -f "${REPO_ROOT}/Makefile" ]; then
    if grep -qE '^test[[:space:]]*:' "${REPO_ROOT}/Makefile" 2>/dev/null; then
      TEST_RUNNER="make"
      TEST_CMD=(make test)
    fi
  fi

  # NOTE on marker lifecycle: post-stop.sh runs a single best-effort stack
  # (the first runner it detects) as a fast-feedback smoke test, but it does
  # NOT clear $DIRTY_MARKER. Marker clearance is the responsibility of
  # run-ci.sh, which executes the configured full pipeline (test + types +
  # lint + invariants) defined in .armature/ci.yaml. In multi-stack repos
  # (e.g., Python + TypeScript), post-stop.sh only exercises one stack and
  # would otherwise prematurely clear the marker, causing run-ci.sh to skip
  # the other stacks. Leaving the marker intact preserves CI-001 coverage.
  if [ -n "$TEST_RUNNER" ]; then
    echo "INFO: Running application tests via ${TEST_RUNNER} (smoke; full pipeline runs in run-ci.sh)..."
    # Expand TEST_CMD as an array so each element is one argv slot —
    # preserves spaces in PY_TESTS_PATH (e.g. "my package/tests").
    if (cd "${REPO_ROOT}" && "${TEST_CMD[@]}" 2>&1); then
      echo "PASS: Application smoke tests passed (run-ci.sh will execute the full pipeline)"
    else
      echo "FAIL: Application smoke tests failed"
      EXIT_CODE=1
    fi
  else
    echo "SKIP: No test runner detected; deferring to run-ci.sh for marker clearance"
  fi
else
  echo "SKIP: No application code changes detected"
fi

# 8. Validate .armature/ci.yaml schema (if present and python is available)
# Catches malformed ci.yaml at governance validation time, not at runtime (D11).
# FAIL propagates via EXIT_CODE=1 — this is a structural validation, not advisory.
if [ -n "$PYTHON" ]; then
  export _POSTSTOP_CI_YAML="${ARMATURE_DIR}/ci.yaml"
  export _POSTSTOP_REPO_ROOT="$REPO_ROOT"
  $PYTHON - <<'PYEOF' || EXIT_CODE=1
import os, sys
try:
    import yaml
except ImportError:
    print('SKIP: PyYAML not available; cannot validate .armature/ci.yaml schema')
    sys.exit(0)

repo_root = os.environ["_POSTSTOP_REPO_ROOT"]
ci_yaml = os.environ["_POSTSTOP_CI_YAML"]

if not os.path.isfile(ci_yaml):
    print("SKIP: .armature/ci.yaml not present (CI hook will skip)")
    sys.exit(0)

try:
    with open(ci_yaml, "rb") as f:
        raw = f.read()
    if b"\x00" in raw:
        print("FAIL: .armature/ci.yaml contains NUL bytes")
        sys.exit(1)
    data = yaml.safe_load(raw.decode("utf-8", errors="replace"))
except yaml.YAMLError as e:
    print(f"FAIL: .armature/ci.yaml is not valid YAML: {e}")
    sys.exit(1)
except OSError as e:
    print(f"FAIL: .armature/ci.yaml could not be read: {e}")
    sys.exit(1)

if data is None:
    print("PASS: .armature/ci.yaml is empty (all steps skipped)")
    sys.exit(0)

if not isinstance(data, dict):
    print(f"FAIL: .armature/ci.yaml must be a YAML mapping, got {type(data).__name__}")
    sys.exit(1)

ALLOWED_KEYS = {"test", "types", "lint", "invariants"}
unknown = set(data.keys()) - ALLOWED_KEYS
if unknown:
    print(f"FAIL: .armature/ci.yaml has unknown top-level keys: {sorted(unknown)}")
    sys.exit(1)

errors = []
for key, val in data.items():
    if not isinstance(val, dict):
        errors.append(f"{key!r} must be a mapping, got {type(val).__name__}")
        continue
    cmd = val.get("command")
    if cmd is not None and not isinstance(cmd, str):
        errors.append(f"{key}.command must be null or string, got {type(cmd).__name__}")
    tos = val.get("timeout_seconds")
    if tos is not None and (not isinstance(tos, int) or isinstance(tos, bool) or tos <= 0):
        errors.append(f"{key}.timeout_seconds must be positive integer, got {tos!r}")

if errors:
    for e in errors:
        print(f"FAIL: .armature/ci.yaml: {e}")
    sys.exit(1)

print(f"PASS: .armature/ci.yaml schema valid ({len(data)} step(s) defined)")
sys.exit(0)
PYEOF
fi

# 9. Invariant-ID resolution check (DRIFT-001)
# Scans governed markdown for [A-Z]+-\d+ tokens and verifies each is either
# (a) a registered invariant key in registry.yaml, or (b) matched by a
# universal allowlist pattern (ADR refs, PR refs, checkpoint/cycle/severity
# codes, well-known technical standards, spec-illustrative placeholders).
# Catches typos, stale renames, and dangling references in governance prose.
# Scope: .armature/**.md (excluding session/escalations/reviews/postmortems),
# docs/adr/*.md, every agents.md / AGENTS.md (excluding .claude/worktrees),
# and top-level CLAUDE.md / CODEX.md / AGENTS.md / PROJECT.md / DOMAIN.md /
# README.md when present.
if [ -n "$PYTHON" ]; then
  export _POSTSTOP_REPO_ROOT="$REPO_ROOT"
  export _POSTSTOP_REGISTRY="$REGISTRY"
  $PYTHON - <<'PYEOF' || EXIT_CODE=1
import os, re, sys
try:
    import yaml
except ImportError:
    print("SKIP: PyYAML not available; cannot run invariant-ID resolution check")
    sys.exit(0)

repo_root = os.environ["_POSTSTOP_REPO_ROOT"]
registry_path = os.environ["_POSTSTOP_REGISTRY"]
armature_dir = os.path.join(repo_root, ".armature")

if not os.path.isfile(registry_path):
    print("SKIP: invariant-ID resolution: registry.yaml not present (bootstrap)")
    sys.exit(0)

# --- Load known invariant IDs from registry ---
try:
    with open(registry_path, encoding="utf-8") as f:
        reg = yaml.safe_load(f) or {}
    known_ids = set((reg.get("invariants") or {}).keys())
except Exception as e:
    print(f"FAIL: invariant-ID resolution: could not load registry: {e}")
    sys.exit(1)

# --- Ephemeral / per-task dirs excluded from .armature/ scan ---
# session/         — living session state, regenerated each session
# escalations/     — circuit-breaker handoff packages
# reviews/         — per-task reviewer verdicts; may cite finding codes scoped to one PR
# postmortems/     — per-incident records with scoped finding codes
ARMATURE_EXCLUDE = {"session", "escalations", "reviews", "postmortems"}

# --- General dirs excluded at any depth ---
GENERAL_EXCLUDE = {"node_modules", "__pycache__", ".venv", ".git"}

# --- Path-prefix exclusions: worktree snapshots are stale and noisy ---
EXCLUDE_PATH_PREFIXES = {
    os.path.normpath(os.path.join(repo_root, ".claude", "worktrees")),
}

def _is_excluded_prefix(path):
    norm = os.path.normpath(path)
    for prefix in EXCLUDE_PATH_PREFIXES:
        if norm == prefix or norm.startswith(prefix + os.sep):
            return True
    return False

# Token regex: TWO+ uppercase letters (optionally followed by uppercase
# alphanumerics), then a dash, then one-or-more digits. Word-boundary
# anchored. The two-letter prefix requirement is deliberate:
#   - Every registered invariant ID in canonical Armature has a >=2-letter
#     prefix (CI-001, REF-001, TIER0-001, etc.); narrowing the regex this
#     way loses no real coverage.
#   - It excludes substrings of regex literals that appear in this same
#     spec/invariants.md prose (e.g. the `Z0-9` inside `[A-Z0-9]+` would
#     otherwise be matched and would create a self-referential FAIL).
# GATE-PHASE-001 yields a single match on PHASE-001 (which is itself a
# registered invariant key); the leading "GATE-" prefix is consumed by
# word-boundary handling, not by the regex.
TOKEN_RE = re.compile(r'\b([A-Z]{2,}[A-Z0-9]*-\d+)\b')

# Universal allowlist patterns. Anchored — only the full token form is
# allowlisted. Patterns are project-agnostic: ADR refs, PR refs, checkpoint
# and cycle nomenclature, red-team finding severity codes, well-known
# technical standards, and the illustrative SEQ-001 / DIGEST-002 placeholders
# used in ARMATURE.md spec examples.
ALLOWLIST = [
    re.compile(r'^ADR-\d+$'),       # ADR file references — tracked by REF-002
    re.compile(r'^PR-\d+$'),        # pull-request references in journal
    re.compile(r'^CP-?\d+$'),       # checkpoint references (CP1, CP-1, CP02, ...)
    re.compile(r'^CYCLE-\d+$'),     # review-cycle references
    re.compile(r'^CRITICAL-\d+$'),  # red-team finding severity codes
    re.compile(r'^HIGH-\d+$'),
    re.compile(r'^MEDIUM-\d+$'),
    re.compile(r'^LOW-\d+$'),
    re.compile(r'^SEQ-\d+$'),       # illustrative invariant ID in ARMATURE.md
    re.compile(r'^DIGEST-\d+$'),    # illustrative invariant ID in ARMATURE.md
    re.compile(r'^AES-\d+$'),       # cryptographic standard reference
    re.compile(r'^SHA-\d+$'),       # hash standard reference
    re.compile(r'^IEEE-\d+$'),      # IEEE standard reference (e.g. IEEE-754)
    re.compile(r'^UTF-\d+$'),       # Unicode encoding reference (UTF-8)
    re.compile(r'^PEP-\d+$'),       # Python Enhancement Proposal reference
]

def is_allowlisted(tok):
    for pat in ALLOWLIST:
        if pat.match(tok):
            return True
    return False

# --- Collect files to scan ---
scan_files = []

# (a) .armature/ recursive, excluding ephemeral dirs
if os.path.isdir(armature_dir):
    for dirpath, dirnames, filenames in os.walk(armature_dir):
        rel = os.path.relpath(dirpath, armature_dir).replace("\\", "/")
        parts = rel.split("/")
        if any(p in ARMATURE_EXCLUDE for p in parts):
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in GENERAL_EXCLUDE]
        for fname in filenames:
            if fname.endswith(".md"):
                scan_files.append(os.path.join(dirpath, fname))

# (b) docs/adr/
adr_dir = os.path.join(repo_root, "docs", "adr")
if os.path.isdir(adr_dir):
    for dirpath, dirnames, filenames in os.walk(adr_dir):
        dirnames[:] = [d for d in dirnames if d not in GENERAL_EXCLUDE]
        for fname in filenames:
            if fname.endswith(".md"):
                scan_files.append(os.path.join(dirpath, fname))

# (c) Every agents.md / AGENTS.md at any depth (excluding worktree snapshots)
for dirpath, dirnames, filenames in os.walk(repo_root):
    dirnames[:] = [
        d for d in dirnames
        if d not in GENERAL_EXCLUDE
        and not d.startswith(".git")
        and not _is_excluded_prefix(os.path.join(dirpath, d))
    ]
    if _is_excluded_prefix(dirpath):
        continue
    for fname in filenames:
        if fname.lower() == "agents.md":
            scan_files.append(os.path.join(dirpath, fname))

# (d) Top-level well-known docs. AGENTS.md is also incidentally collected
# by section (c)'s repo-wide agents.md walk; listing it here too keeps the
# explicit list self-consistent with the documented scope in invariants.md.
for top_file in ["CLAUDE.md", "CODEX.md", "AGENTS.md", "PROJECT.md", "DOMAIN.md", "README.md"]:
    fp = os.path.join(repo_root, top_file)
    if os.path.isfile(fp):
        scan_files.append(fp)

scan_files = sorted(set(scan_files))

# --- Scan tokens ---
violations = []
total_tokens = 0
for fp in scan_files:
    try:
        with open(fp, encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, 1):
                for m in TOKEN_RE.finditer(line):
                    tok = m.group(1)
                    total_tokens += 1
                    if tok not in known_ids and not is_allowlisted(tok):
                        rel = os.path.relpath(fp, repo_root)
                        violations.append((rel, lineno, tok))
    except OSError as e:
        print(f"WARN: invariant-ID resolution: could not read {fp}: {e}")

if violations:
    for rel, lineno, tok in violations:
        print(f"FAIL: {rel}:{lineno}: unknown invariant ID '{tok}'")
    sys.exit(1)

print(
    f"PASS: invariant-ID resolution ({len(scan_files)} files scanned, "
    f"{total_tokens} tokens checked, {len(known_ids)} known invariants in registry)"
)
sys.exit(0)
PYEOF
fi

echo "=== Armature Validation Complete (exit: ${EXIT_CODE}) ==="
exit $EXIT_CODE
