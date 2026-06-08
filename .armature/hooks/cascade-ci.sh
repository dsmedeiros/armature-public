#!/usr/bin/env bash
# Armature CI backstop for cascade rules (DRIFT-002).
#
# This is the AUTHORITATIVE DRIFT-002 layer. Unlike the PreToolUse gate
# (precommit-cascade-gate.sh), which must parse the Bash command string before
# it runs and therefore cannot model every shell form (edit-before-stage,
# exotic operators, etc.), this script evaluates the ACTUAL committed changeset
# after the fact. It runs check-cascade.sh per-commit over a commit range, so a
# cascade-violating commit is caught no matter how it was produced.
#
# Per-commit (not union) matches the atomic-landing guarantee: each commit must
# carry a triggered rule's companions itself, so the violation cannot survive a
# later cherry-pick/revert/rebase of that single commit.
#
# Usage:
#   bash .armature/hooks/cascade-ci.sh <base>..<head>     explicit range
#   bash .armature/hooks/cascade-ci.sh                    default range
#
# Default range: origin/<default-branch>..HEAD if resolvable, else HEAD~1..HEAD,
# else just HEAD (initial commit). An all-zero/unresolvable base (new branch
# push) falls back to checking HEAD only.
#
# Exit codes:
#   0  PASS / SKIP (no rules file, or no violating commit)
#   2  FAIL — at least one commit violates a blocking cascade rule

set -euo pipefail

ARMATURE_DIR="${ARMATURE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
CHECK_CASCADE="${ARMATURE_DIR}/hooks/check-cascade.sh"
RULES_FILE="${ARMATURE_DIR}/cascade-rules.yaml"

if [ ! -f "$RULES_FILE" ]; then
  echo "SKIP: cascade-ci — cascade-rules.yaml not found"
  exit 0
fi
if [ ! -f "$CHECK_CASCADE" ]; then
  echo "FAIL: cascade-ci — check-cascade.sh not found at $CHECK_CASCADE" >&2
  exit 2
fi

RANGE="${1:-}"

# Resolve a default range when none is supplied.
if [ -z "$RANGE" ]; then
  default_branch=""
  if git symbolic-ref --quiet refs/remotes/origin/HEAD >/dev/null 2>&1; then
    default_branch="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || true)"
  fi
  if [ -n "$default_branch" ] && git rev-parse --verify --quiet "$default_branch" >/dev/null 2>&1; then
    RANGE="${default_branch}..HEAD"
  elif git rev-parse --verify --quiet "HEAD~1" >/dev/null 2>&1; then
    RANGE="HEAD~1..HEAD"
  else
    RANGE="HEAD"   # initial commit; rev-list HEAD lists all commits
  fi
fi

# If the range has an explicit base that is unresolvable (e.g. the all-zero SHA
# GitHub sends for a new-branch push), fall back to HEAD-only.
case "$RANGE" in
  *..*)
    base="${RANGE%%..*}"
    if ! git rev-parse --verify --quiet "${base}^{commit}" >/dev/null 2>&1; then
      echo "WARN: cascade-ci — base '${base}' unresolvable; checking HEAD only" >&2
      RANGE="HEAD~1..HEAD"
      git rev-parse --verify --quiet "HEAD~1" >/dev/null 2>&1 || RANGE="HEAD"
    fi
    ;;
esac

# List commits oldest-first so violations are reported in apply order.
if ! commits="$(git rev-list --reverse "$RANGE" 2>/dev/null)"; then
  echo "WARN: cascade-ci — could not resolve range '$RANGE'; nothing checked" >&2
  exit 0
fi

if [ -z "$commits" ]; then
  echo "PASS: cascade-ci (no commits in range $RANGE)"
  exit 0
fi

rc=0
n_checked=0
n_violating=0
for sha in $commits; do
  # Per-commit file set; --no-renames so a renamed trigger surfaces its old
  # path too. Merge commits emit no files here (default) → nothing to check.
  files="$(git show --name-only --no-renames --format= "$sha" 2>/dev/null | sed '/^[[:space:]]*$/d' || true)"
  [ -z "$files" ] && continue
  n_checked=$((n_checked + 1))
  # Suppress per-commit PASS chatter on stdout; FAIL diagnostics go to stderr.
  if ! printf '%s\n' "$files" | bash "$CHECK_CASCADE" --from-stdin >/dev/null; then
    echo "FAIL: cascade-ci — violation in commit $sha" >&2
    n_violating=$((n_violating + 1))
    rc=2
  fi
done

if [ "$rc" -eq 0 ]; then
  echo "PASS: cascade-ci ($n_checked commit(s) checked in range $RANGE)"
else
  echo "FAIL: cascade-ci ($n_violating of $n_checked checked commit(s) violate a blocking cascade rule)" >&2
fi
exit $rc
