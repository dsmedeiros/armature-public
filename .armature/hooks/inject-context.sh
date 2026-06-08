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

set -euo pipefail

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
# Output protocol (PR #297 cycle-12 finding #23):
#
# Claude Code's SubagentStart hook does NOT capture plain stdout. Per the
# hooks.md spec, context must be returned via JSON output:
#
#   {"hookSpecificOutput": {
#       "hookEventName": "SubagentStart",
#       "additionalContext": "<text content>"
#   }}
#
# We collect all section emissions into a buffer file, then JSON-encode
# the buffer's contents at the end and emit the envelope as the sole
# stdout output. fd 9 is reserved for the real stdout; fd 1 redirects to
# the buffer during the body.
#
# If python is unavailable for the final JSON encoding, fall back to
# plain-text emission on real stdout (best-effort; Claude Code will not
# inject the context but the content is at least visible for debug).
# ---------------------------------------------------------------------------
_INJECT_BUFFER="$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/inject-context-buffer-$$")"
_INJECT_DRAINED=0

# ---------------------------------------------------------------------------
# Fail-open drain function: restores fd 1 from fd 9 (idempotent), reads the
# buffer (which may be partial if a mid-script error fired errexit), and
# emits the JSON envelope on real stdout. Always exits 0 — this hook is
# documented as fail-open, so even on internal Python errors the parent
# Claude Code session must not see a non-zero hook exit (which would block
# subagent start). The trap on EXIT/INT/TERM calls this so every exit path
# (success, set -e abort, signal) drains uniformly.
# ---------------------------------------------------------------------------
_inject_drain() {
    # Idempotent guard: if we already drained (e.g. explicit call followed
    # by EXIT trap), skip the second invocation.
    if [ "$_INJECT_DRAINED" = "1" ]; then
        rm -f "$_INJECT_BUFFER" 2>/dev/null || true
        return 0
    fi
    _INJECT_DRAINED=1
    # Restore fd 1 from fd 9 if redirected. Swallow "Bad file descriptor"
    # on early-exit paths where fd 9 was never opened.
    exec 1>&9 9>&- 2>/dev/null || true
    if [ -f "$_INJECT_BUFFER" ]; then
        if [ -n "${PYTHON:-}" ]; then
            export _INJECT_BUFFER_PATH="$_INJECT_BUFFER"
            "$PYTHON" - <<'PYEOF' 2>/dev/null || cat "$_INJECT_BUFFER" 2>/dev/null || true
import json, os
buf_path = os.environ["_INJECT_BUFFER_PATH"]
try:
    with open(buf_path, "r", encoding="utf-8") as f:
        content = f.read()
except Exception:
    content = ""
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SubagentStart",
        "additionalContext": content,
    }
}))
PYEOF
        else
            # Python unavailable: emit raw content (best-effort fallback;
            # Claude Code will not inject this but the content is at least
            # visible for debug).
            cat "$_INJECT_BUFFER" 2>/dev/null || true
        fi
    fi
    rm -f "$_INJECT_BUFFER" 2>/dev/null || true
}
trap '_inject_drain; exit 0' EXIT INT TERM
exec 9>&1 1>"$_INJECT_BUFFER"

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
# Probe both lowercase and uppercase forms. Per ARMATURE.md §3, scoped
# governance files use lowercase agents.md by convention; the project-root
# directives file uses uppercase AGENTS.md (the agnostic alias for projects
# that follow that convention). Both forms are equivalent for governance
# lookup; the first one found wins.
while True:
    for name in ("agents.md", "AGENTS.md"):
        probe = os.path.join(current, name)
        if os.path.isfile(probe):
            agents_file = probe
            break
    if agents_file:
        break
    parent = os.path.dirname(current)
    if parent == current:
        break
    current = parent

if not agents_file:
    print("<!-- no agents.md / AGENTS.md found in scope path hierarchy, skipping -->")
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

# ---------------------------------------------------------------------------
# Section 4: Active Disciplines
# ---------------------------------------------------------------------------
echo "## Active Disciplines"
echo ""

if [ -z "$PYTHON" ]; then
  echo "<!-- python not available; cannot evaluate disciplines -->"
else
  export _INJECT_ARMATURE_DIR="$ARMATURE_DIR"
  $PYTHON - <<'PYEOF'
import json, os, sys, fnmatch

repo_root = os.environ.get("_INJECT_REPO_ROOT", "")
stdin_json = os.environ.get("_INJECT_STDIN_JSON", "")
armature_dir = os.environ.get("_INJECT_ARMATURE_DIR", "")

triggers_path = os.path.join(armature_dir, "disciplines", "triggers.yaml")

if not os.path.isfile(triggers_path):
    print("<!-- triggers.yaml not found, skipping discipline injection -->")
    sys.exit(0)

try:
    import yaml
except ImportError:
    print("<!-- pyyaml not available, skipping discipline injection -->")
    sys.exit(0)

try:
    with open(triggers_path) as f:
        triggers_data = yaml.safe_load(f)
except Exception as e:
    print(f"<!-- triggers.yaml parse error: {e}, skipping -->")
    sys.exit(0)

all_disciplines = triggers_data.get("triggers", {}) if triggers_data else {}

# ---- Resolve scope hint (same logic as Section 3) ----
candidate_path = None
if stdin_json.strip():
    try:
        data = json.loads(stdin_json)
        for key in ("file", "path", "scope", "cwd", "workingDirectory"):
            val = data.get(key)
            if val and isinstance(val, str):
                candidate_path = val
                break
    except Exception:
        pass

scope_path = candidate_path if candidate_path else repo_root

# ---- Resolve nearest agents.md for scope ----
search_dir = scope_path if scope_path else repo_root
if not os.path.isdir(search_dir):
    search_dir = os.path.dirname(search_dir)

agents_file = None
current = os.path.abspath(search_dir)
# Probe both lowercase and uppercase forms (parallels the Scope Context
# lookup earlier). Without this, projects using uppercase AGENTS.md at
# project root get empty scope_invariants/scope_discipline_tags, so
# invariant- and explicit-trigger disciplines silently fail to inject.
while True:
    for name in ("agents.md", "AGENTS.md"):
        probe = os.path.join(current, name)
        if os.path.isfile(probe):
            agents_file = probe
            break
    if agents_file:
        break
    parent = os.path.dirname(current)
    if parent == current:
        break
    current = parent

# ---- Parse agents.md frontmatter for invariants + discipline-tags ----
scope_invariants = []
scope_discipline_tags = []
# Use posix path for scope matching
scope_posix = scope_path.replace("\\", "/") if scope_path else ""

if agents_file:
    try:
        with open(agents_file) as f:
            agents_content = f.read()
        if agents_content.startswith("---"):
            end = agents_content.find("---", 3)
            if end >= 0:
                fm_raw = agents_content[3:end].strip()
                fm = None
                try:
                    fm = yaml.safe_load(fm_raw)
                except Exception:
                    pass
                if fm and isinstance(fm, dict):
                    inv = fm.get("invariants", [])
                    if isinstance(inv, list):
                        scope_invariants = [str(i) for i in inv]
                    tags = fm.get("discipline-tags", [])
                    if isinstance(tags, list):
                        scope_discipline_tags = [str(t) for t in tags]
    except Exception:
        pass

# ---- fnmatch helper: translate ** to * for conservative approximation ----
def _match_path_pattern(pattern, scope):
    """
    Match scope_posix against a glob pattern.
    ** is translated to * (conservative approximation per plan R5).
    Matching is done on the full posix path AND on the basename.
    """
    # Normalise pattern: replace ** with *
    norm_pattern = pattern.replace("**", "*")
    # Try against full path
    if fnmatch.fnmatch(scope, norm_pattern):
        return True
    # Try against basename
    basename = os.path.basename(scope)
    if fnmatch.fnmatch(basename, norm_pattern.lstrip("/*")):
        return True
    # Try matching any path component with recursive pattern
    # e.g. "*tests*" should match paths containing /tests/
    parts = scope.replace("\\", "/").split("/")
    for part in parts:
        if fnmatch.fnmatch(part, norm_pattern.strip("/")):
            return True
    return False

# ---- Evaluate triggers ----
# Severity order for sorting
SEVERITY_ORDER = {"critical": 0, "high": 1, "standard": 2}
# Composition mode order
MODE_ORDER = {"strict": 0, "advisory": 1}

fired = {}      # id -> trigger_type_that_fired
decl_order = list(all_disciplines.keys())  # declaration order from triggers.yaml

for disc_id, disc_cfg in all_disciplines.items():
    if not isinstance(disc_cfg, dict):
        continue
    trigger_list = disc_cfg.get("triggers", [])
    if not isinstance(trigger_list, list):
        continue

    # Per ARMATURE.md §8.4: a missing or empty triggers list is always-on —
    # the discipline fires for every delegation without trigger evaluation.
    if len(trigger_list) == 0:
        fired[disc_id] = "always-on"
        continue

    fired_type = None
    for trigger in trigger_list:
        if not isinstance(trigger, dict):
            continue
        ttype = trigger.get("type", "")
        pattern = trigger.get("pattern")

        if ttype == "content":
            # Content triggers deferred — emit comment but don't fire
            print(f"<!-- discipline {disc_id}: content trigger requires orchestrator pre-evaluation; skipped at hook level -->")
            continue

        if ttype == "path" and scope_posix:
            patterns = pattern if isinstance(pattern, list) else [pattern] if pattern else []
            for pat in patterns:
                if pat and _match_path_pattern(str(pat), scope_posix):
                    fired_type = "path"
                    break

        elif ttype == "invariant":
            patterns = pattern if isinstance(pattern, list) else [pattern] if pattern else []
            # Intersect patterns with scope_invariants
            if any(p in scope_invariants for p in patterns if p):
                fired_type = "invariant"

        elif ttype == "explicit":
            # Pattern is a single string; check if it matches a discipline-tag
            if isinstance(pattern, str) and pattern in scope_discipline_tags:
                fired_type = "explicit"

        if fired_type:
            break

    if fired_type:
        fired[disc_id] = fired_type

if not fired:
    print("<!-- no disciplines fired for this scope -->")
    sys.exit(0)

# ---- Composition cap (§4.8): max 4 disciplines ----
# Sort: severity asc (critical=0, high=1, standard=2), then mode asc (strict=0, advisory=1),
# then declaration order
def _sort_key(disc_id):
    cfg = all_disciplines.get(disc_id, {})
    severity = cfg.get("severity", "standard")
    mode = cfg.get("composition-mode", "advisory")
    sev_rank = SEVERITY_ORDER.get(severity, 99)
    mode_rank = MODE_ORDER.get(mode, 99)
    decl_rank = decl_order.index(disc_id) if disc_id in decl_order else 9999
    return (sev_rank, mode_rank, decl_rank)

fired_sorted = sorted(fired.keys(), key=_sort_key)

CAP = 4
selected = fired_sorted[:CAP]
truncated = fired_sorted[CAP:]

# ---- Emit discipline content ----
disciplines_dir = os.path.join(armature_dir, "disciplines")

for disc_id in selected:
    disc_file = os.path.join(disciplines_dir, f"{disc_id}.md")
    if not os.path.isfile(disc_file):
        print(f"<!-- discipline {disc_id} fired but file not found, skipping -->")
        continue
    try:
        with open(disc_file) as f:
            disc_content = f.read()
    except Exception as e:
        print(f"<!-- discipline {disc_id}: could not read file: {e}, skipping -->")
        continue
    # Strip frontmatter — find closing --- at the START of a line (not
    # inside a YAML scalar value).  Per ARMATURE.md §8.4 / MEDIUM-2 fix.
    body = disc_content
    if disc_content.startswith("---"):
        lines = disc_content.split("\n")
        closing_idx = None
        for _i in range(1, len(lines)):
            if lines[_i].strip() == "---":
                closing_idx = _i
                break
        if closing_idx is not None:
            body = "\n".join(lines[closing_idx + 1:]).lstrip("\n")
    print(f"### {disc_id}")
    print("")
    print(body.rstrip())
    print("")

# ---- Emit attribution block ----
trigger_modes = {disc_id: fired[disc_id] for disc_id in selected}
fired_list = ", ".join(fired_sorted) if fired_sorted else "none"
selected_list = ", ".join(selected) if selected else "none"
truncated_list = ", ".join(truncated) if truncated else "none"
trigger_modes_str = str(trigger_modes)

print("<!-- DISCIPLINE-ATTRIBUTION")
print(f"fired: {fired_list}")
print(f"selected: {selected_list}")
print(f"truncated: {truncated_list}")
print(f"trigger_modes: {trigger_modes_str}")
print("-->")
PYEOF
fi

echo ""

# ---------------------------------------------------------------------------
# All section emissions complete. The EXIT trap above (_inject_drain) will
# restore fd 1 from fd 9, emit the JSON envelope wrapping the buffer, clean
# up the temp file, and exit 0. This unified path means a Python parser
# error or any other errexit-triggering failure mid-script still produces
# a valid (possibly partial) JSON envelope to the parent session, honoring
# the fail-open contract documented in the header.
# ---------------------------------------------------------------------------
