#!/usr/bin/env bash
# Armature cascade-rule enforcement hook (DRIFT-002, Tier 2)
#
# Checks that when a "trigger" file is in the changeset, all required companion
# files are also in it. Rules are defined in .armature/cascade-rules.yaml.
#
# Usage:
#   bash .armature/hooks/check-cascade.sh [--staged-only]
#   bash .armature/hooks/check-cascade.sh --files PATH [PATH...]
#   bash .armature/hooks/check-cascade.sh --from-stdin   (reads paths from stdin, one per line)
#
# Exit codes:
#   0   PASS or SKIP (rules file absent, or empty changeset)
#   2   FAIL — one or more blocking cascade rules violated (exit 2 = blocking
#       on PreToolUse, matching the project's other PreToolUse gates)
#
# Python interpreter: resolved via $PYTHON (python3 preferred, python fallback),
# mirroring post-stop.sh.

set -euo pipefail

ARMATURE_DIR="${ARMATURE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
RULES_FILE="${ARMATURE_DIR}/cascade-rules.yaml"

# Find Python (mirror post-stop.sh)
if command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
else
    echo "FAIL: cascade check — no Python interpreter available" >&2
    exit 2
fi

# ---- Collect paths to evaluate ----------------------------------------

MODE="staged-only"
EXPLICIT_FILES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --staged-only)
      MODE="staged-only"
      shift
      ;;
    --files)
      MODE="files"
      shift
      # Everything after --files is a file path. Consume greedily and do NOT
      # treat --prefixed tokens as options: a git-tracked file may legally be
      # named e.g. "--staged-only" or "--from-stdin", and callers (the cascade
      # gate) always pass --files LAST, so nothing after it is ever an option.
      # An optional "--" terminator is accepted and skipped for explicit callers.
      if [[ $# -gt 0 && "$1" == "--" ]]; then shift; fi
      while [[ $# -gt 0 ]]; do
        EXPLICIT_FILES+=("$1")
        shift
      done
      ;;
    --from-stdin)
      MODE="stdin"
      shift
      ;;
    *)
      echo "FAIL: check-cascade.sh: unknown argument '$1'" >&2
      exit 2
      ;;
  esac
done

# ---- Rules file guard -------------------------------------------------

if [ ! -f "$RULES_FILE" ]; then
  echo "SKIP: cascade-rules.yaml not found"
  exit 0
fi

# ---- Build changeset --------------------------------------------------

CHANGESET_FILE="$(mktemp)"
trap 'rm -f "$CHANGESET_FILE"' EXIT

case "$MODE" in
  staged-only)
    # --no-renames so a staged rename appears as delete(old) + add(new),
    # putting BOTH paths in the changeset. Without it, `git diff --cached
    # --name-only` reports only the post-rename path, letting a pure rename of
    # a trigger file (e.g. `git mv registry.yaml x.yaml`) bypass its cascade
    # rule because the old trigger path is never matched.
    git diff --cached --name-only --no-renames 2>/dev/null > "$CHANGESET_FILE" || true
    ;;
  files)
    if [ "${#EXPLICIT_FILES[@]}" -gt 0 ]; then
      printf '%s\n' "${EXPLICIT_FILES[@]}" > "$CHANGESET_FILE"
    fi
    ;;
  stdin)
    cat > "$CHANGESET_FILE"
    ;;
esac

# Empty changeset — nothing to check
if [ ! -s "$CHANGESET_FILE" ]; then
  echo "PASS: cascade check (no staged paths)"
  exit 0
fi

# ---- Python evaluation ------------------------------------------------
# Parse cascade-rules.yaml and evaluate each rule against the changeset.
# Uses fnmatch.fnmatchcase() for glob patterns (handles ** correctly).
# For must_also_touch_same_dir: resolves the scope-root directory from the
# triggered path (using the configurable same_dir_roots list) and checks for
# the required filename there.

export _CASCADE_RULES_FILE="$RULES_FILE"
export _CASCADE_CHANGESET_FILE="$CHANGESET_FILE"

"$PYTHON" - <<'PYEOF'
import fnmatch, os, sys
from pathlib import PurePosixPath

try:
    import yaml
except ImportError:
    # Fail CLOSED. This path is only reached when .armature/cascade-rules.yaml
    # EXISTS (the bash guard SKIPs and exits 0 when it is absent), so the
    # project has opted into cascade enforcement. A blocking commit gate that
    # cannot parse its own rules must not silently allow every commit —
    # exiting 0 here would disable DRIFT-002 for all rules. Exit 2 with an
    # actionable message instead. PyYAML is a DECLARED RUNTIME dependency of
    # Armature (pyproject.toml [project].dependencies) precisely because the
    # governance hooks parse YAML at enforcement time; a missing parser is a
    # broken environment, not an expected optional-extra case.
    print(
        "FAIL: cascade check — PyYAML is required to parse cascade-rules.yaml "
        "but is not installed; DRIFT-002 cannot be enforced. PyYAML is a runtime "
        "dependency of Armature: install it (pip install pyyaml, or pip install "
        "-e . in the scaffold) or remove .armature/cascade-rules.yaml if this "
        "project defines no cascade rules.",
        file=sys.stderr,
    )
    sys.exit(2)

rules_file = os.environ["_CASCADE_RULES_FILE"]
changeset_file = os.environ["_CASCADE_CHANGESET_FILE"]

# ---- Load rules -------------------------------------------------------
try:
    with open(rules_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)
except Exception as e:
    print(f"FAIL: check-cascade.sh: could not parse cascade-rules.yaml: {e}", file=sys.stderr)
    sys.exit(2)

if data is None:
    print("PASS: cascade check (empty rules file)")
    sys.exit(0)
if not isinstance(data, dict):
    print(f"FAIL: cascade-rules.yaml: top level must be a mapping, got {type(data).__name__}", file=sys.stderr)
    sys.exit(2)

rules = data.get("rules", [])
if not isinstance(rules, list):
    print(f"FAIL: cascade-rules.yaml: 'rules' must be a list, got {type(rules).__name__}", file=sys.stderr)
    sys.exit(2)

# ---- same_dir_roots (configurable; default empty) ---------------------
same_dir_roots = data.get("same_dir_roots", []) or []
if not isinstance(same_dir_roots, list):
    print(f"FAIL: cascade-rules.yaml: 'same_dir_roots' must be a list, got {type(same_dir_roots).__name__}", file=sys.stderr)
    sys.exit(2)
for idx, entry in enumerate(same_dir_roots):
    if not isinstance(entry, str) or not entry:
        print(f"FAIL: cascade-rules.yaml: same_dir_roots[{idx}] must be a non-empty string", file=sys.stderr)
        sys.exit(2)
SCOPE_PARENTS = set(same_dir_roots)

# ---- Validate rules schema --------------------------------------------
for idx, rule in enumerate(rules):
    if not isinstance(rule, dict):
        print(f"FAIL: cascade-rules.yaml: rule #{idx} is not a mapping", file=sys.stderr)
        sys.exit(2)
    name = rule.get("name")
    if not isinstance(name, str) or not name:
        print(f"FAIL: cascade-rules.yaml: rule #{idx} missing or invalid 'name'", file=sys.stderr)
        sys.exit(2)
    wt = rule.get("when_touched")
    if not isinstance(wt, list) or not wt:
        print(f"FAIL: cascade-rules.yaml: rule '{name}' missing or empty 'when_touched'", file=sys.stderr)
        sys.exit(2)
    for idx_e, entry in enumerate(wt):
        if not isinstance(entry, str):
            print(f"FAIL: cascade-rules.yaml: rule '{name}' when_touched[{idx_e}] must be a string, got {type(entry).__name__}", file=sys.stderr)
            sys.exit(2)
    mat = rule.get("must_also_touch")
    if mat is not None and not isinstance(mat, list):
        print(f"FAIL: cascade-rules.yaml: rule '{name}' must_also_touch must be a list, got {type(mat).__name__}", file=sys.stderr)
        sys.exit(2)
    mat = mat or []
    matsd = rule.get("must_also_touch_same_dir")
    if matsd is not None and not isinstance(matsd, list):
        print(f"FAIL: cascade-rules.yaml: rule '{name}' must_also_touch_same_dir must be a list, got {type(matsd).__name__}", file=sys.stderr)
        sys.exit(2)
    matsd = matsd or []
    if not mat and not matsd:
        print(f"FAIL: cascade-rules.yaml: rule '{name}' has no companions (must_also_touch or must_also_touch_same_dir)", file=sys.stderr)
        sys.exit(2)
    for idx_e, entry in enumerate(mat):
        if not isinstance(entry, str):
            print(f"FAIL: cascade-rules.yaml: rule '{name}' must_also_touch[{idx_e}] must be a string, got {type(entry).__name__}", file=sys.stderr)
            sys.exit(2)
    for idx_e, entry in enumerate(matsd):
        if not isinstance(entry, str):
            print(f"FAIL: cascade-rules.yaml: rule '{name}' must_also_touch_same_dir[{idx_e}] must be a string, got {type(entry).__name__}", file=sys.stderr)
            sys.exit(2)
    if matsd and not SCOPE_PARENTS:
        # Inert rule: same-dir companions declared but no same_dir_roots
        # configured to resolve a scope root. Warn so it is not silently skipped.
        print(
            f"WARN: cascade-rules.yaml: rule '{name}' declares must_also_touch_same_dir "
            f"but top-level 'same_dir_roots' is empty; the same-dir companions cannot "
            f"be resolved and will be skipped.",
            file=sys.stderr
        )
    sev = rule.get("severity", "blocking")
    if sev not in ("blocking", "advisory"):
        print(f"FAIL: cascade-rules.yaml: rule '{name}' has invalid severity '{sev}'", file=sys.stderr)
        sys.exit(2)

# ---- Load changeset ---------------------------------------------------
with open(changeset_file, encoding="utf-8") as f:
    changeset = [line.strip().replace("\\", "/") for line in f if line.strip()]

changeset_set = set(changeset)

# ---- Helper: glob match -----------------------------------------------
def _expand_globstar_variants(pattern):
    """Expand each globstar path segment into zero-dir and one-or-more-dir forms.

    fnmatch translates `**` to `.*`, but the surrounding slashes in `a/**/b`
    become `a/.*/b`, which REQUIRES an intermediate path component — so a file
    directly under `a` (`a/b`, zero intervening directories) does NOT match.
    That is a false negative for the common "top-level OR nested" rule form.

    To fix it without losing any of fnmatch's other semantics (character
    classes, `?`, single `*`), we expand each globstar into both forms and let
    fnmatch test all of them:
      - `a/**/b`   → ["a/**/b" (one-or-more dirs), "a/b" (zero dirs)]
      - leading `**/b` → ["**/b" (one-or-more), "b" (zero)]
    For k globstars this yields 2^k variants; k is 0-2 in practice. The result
    can only ADD matches (over-match), never drop one, preserving the
    never-under-match invariant the cascade check relies on.
    """
    idx = pattern.find("/**/")
    if idx != -1:
        head, tail = pattern[:idx], pattern[idx + 4:]
        out = []
        for sub in _expand_globstar_variants(tail):
            out.append(head + "/**/" + sub)  # one or more directory levels
            out.append(head + "/" + sub)      # zero directory levels
        return out
    if pattern.startswith("**/"):
        out = []
        for sub in _expand_globstar_variants(pattern[3:]):
            out.append("**/" + sub)  # one or more leading directory levels
            out.append(sub)           # zero leading directories
        return out
    return [pattern]


def matches_glob(path_str, pattern):
    """
    Match a POSIX path string against a glob pattern.

    Uses fnmatch.fnmatchcase() for the base semantics (it supports `*`, `?`, and
    character classes; PurePosixPath.match() does NOT support recursive ** even
    on 3.12+). On top of fnmatch we expand globstar (`**`) path segments via
    _expand_globstar_variants() so that `a/**/b` matches BOTH `a/b` (zero
    intervening dirs) and `a/x/.../b` (one or more) — fnmatch alone misses the
    zero-dir case. Matching is intentionally permissive (over-match tolerant):
    it can only ADD cascade triggers, never silently skip a required companion.
    """
    path_str = path_str.replace("\\", "/")
    pattern = pattern.replace("\\", "/")
    if path_str == pattern:
        return True
    return any(
        fnmatch.fnmatchcase(path_str, variant)
        for variant in _expand_globstar_variants(pattern)
    )

# ---- Helper: resolve scope root from a triggered path -----------------
# The scope root is '<parent>/<name>' when the path is under a configured
# top-level parent (from same_dir_roots) with at least one nested directory.
def scope_root_of(path_str):
    """Return 'parent/name' when path is under a configured same_dir_root with
    at least one nested directory; return None otherwise."""
    path_str = path_str.replace("\\", "/")
    parts = PurePosixPath(path_str).parts
    if len(parts) < 3:
        # Need: parent / name / at-least-one-more-segment
        return None
    if parts[0] not in SCOPE_PARENTS:
        return None
    return str(PurePosixPath(*parts[:2]))

# ---- Evaluate rules ---------------------------------------------------
violations = []
rules_evaluated = 0
rules_triggered = 0

for rule in rules:
    name = rule.get("name", "<unnamed>")
    when_touched = rule.get("when_touched", [])
    must_also_touch = rule.get("must_also_touch", []) or []
    must_also_touch_same_dir = rule.get("must_also_touch_same_dir", []) or []
    severity = rule.get("severity", "blocking")
    reason = rule.get("reason", "")

    rules_evaluated += 1

    # Only blocking rules can cause a FAIL exit.
    if severity != "blocking":
        continue

    # Find all trigger matches in the changeset.
    for staged_path in changeset:
        trigger_matched = any(matches_glob(staged_path, pat) for pat in when_touched)
        if not trigger_matched:
            continue

        rules_triggered += 1

        # Check must_also_touch paths (exact membership in changeset).
        for required in must_also_touch:
            req_norm = required.replace("\\", "/")
            if req_norm not in changeset_set:
                violations.append(
                    f"FAIL: cascade rule [{name}] -- staged '{staged_path}' "
                    f"requires '{required}' to also be staged. Reason: {reason}"
                )

        # Check must_also_touch_same_dir paths.
        if must_also_touch_same_dir and SCOPE_PARENTS:
            scope_root = scope_root_of(staged_path)
            if scope_root is not None:
                for required_name in must_also_touch_same_dir:
                    required_path = f"{scope_root}/{required_name}"
                    if required_path not in changeset_set:
                        violations.append(
                            f"FAIL: cascade rule [{name}] -- staged '{staged_path}' "
                            f"requires '{required_path}' to also be staged. Reason: {reason}"
                        )
            # scope_root is None → path not under a configured same_dir_root;
            # same-dir resolution is inapplicable, skip quietly.

# ---- Report -----------------------------------------------------------
n_paths = len(changeset)

if violations:
    # De-duplicate while preserving order (a path can match multiple globs).
    seen = set()
    for v in violations:
        if v not in seen:
            seen.add(v)
            print(v, file=sys.stderr)
    sys.exit(2)

print(
    f"PASS: cascade check ({rules_evaluated} rules evaluated, "
    f"{rules_triggered} rule-triggerings, {n_paths} paths in changeset)"
)
sys.exit(0)
PYEOF
