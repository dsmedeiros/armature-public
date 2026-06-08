#!/usr/bin/env bash
# Armature PreToolUse + SubagentStart hook — task-readiness
# Event(s): PreToolUse(Agent) and SubagentStart (dual-mode per R1)
#
# Per https://code.claude.com/docs/en/hooks, "Agent" is the documented
# canonical tool name for subagent delegation in Claude Code. "Task" is
# the legacy alias retained for backwards compatibility.
# Invariant: TASK-001
#
# Purpose:
#   Gate sub-agent delegation by requiring acceptance criteria in the task
#   prompt.  Fail-closed: if no criteria are detected, exit 2 and block the
#   delegation.  Fail-open on parse errors, Python unavailability, and
#   NUL-byte payloads (defense-in-depth, not primary guard).
#
# Dual-mode event handling (R1):
#   Claude Code may fire this hook via PreToolUse(Task) or SubagentStart.
#   - PreToolUse(Task): outer payload has tool_name == "Task";
#     prompt is in tool_input.prompt (fallback: tool_input.description,
#     tool_input.task, bare prompt).
#   - SubagentStart: outer payload has no tool_name but has a scope field;
#     prompt is in prompt or subagent_prompt field.
#   - If neither shape applies -> fail-open, exit 0.
#
# Criterion detection — two modes:
#   Strict (default): heading present AND followed by >=1 non-blank bullet/
#   numbered list item.
#     Patterns (case-insensitive, line-anchored):
#       ^#{1,6}\s+Acceptance\s+Criteria\s*$
#       ^\*\*Acceptance\s+Criteria:\*\*  (anywhere on line)
#       ^Acceptance\s+criteria:\s*$
#   Lenient (fallback): bullet/numbered list block with >=2 items where >=2
#   contain criterion keywords (whole-word, case-insensitive):
#     must, should, verify, assert, expect, given, when, then, check, test, pass
#
# Block behavior:
#   Neither mode matches -> exit 2, stderr contains:
#     "Task requires acceptance criteria before delegation per TASK-001"
#   Lenient succeeded -> WARN advisory to stderr, exit 0.
#
# Correlation file (D3):
#   On PASS, writes .armature/session/active-delegations/<hash>.json where
#   <hash> = first 16 hex chars of SHA-256(normalized prompt text).
#   Normalization: lower-case + collapse whitespace via re.sub(\s+, space, t).strip()
#   File write failure -> WARN to stderr + exit 0 (fail-open, do NOT block).
#   This file is consumed by task-completion.sh (CP2) and GC'd by post-stop.sh
#   (CP3).  See D3 contract in m5-plan.md.
#
# Known limitation (R2 — correlation race):
#   Under concurrent sub-agent delegation (atypical in Armature's single-
#   threaded model), task-completion.sh may read the wrong correlation file
#   because it uses the most-recently-modified file as its heuristic.  Deferred
#   until Claude Code exposes a stable subagent_id field (noted as R3 in plan).
# Known limitation: fenced code blocks are NOT excluded from criterion
#   detection (conservative match — see SHOULD test 17 and m5-plan.md
#   §CP1 red-team analysis).
#
# Hotfix bypass:
#   If .armature/session/phase contains exactly "Hotfix" (ASCII strip only —
#   Unicode whitespace bypass is a known attack vector per M3 CP3 finding),
#   emit ADVISORY and exit 0.
#
# Exit codes:
#   0  = pass (fail-open, hotfix bypass, NUL-byte WARN, or criteria found)
#   2  = block (criteria absent — BLOCK message contains "TASK-001")
#
# Fail-open conditions (exit 0):
#   - Python unavailable
#   - stdin payload is invalid JSON
#   - NUL bytes in payload (WARN + exit 0 — defense-in-depth)
#   - tool_name is neither "Agent"/"Task" nor absent-with-scope
#   - Phase is "Hotfix"
#   - .armature/session/active-delegations/ not writable (WARN + exit 0)
#
# Cross-platform: works on Git Bash (Windows), bash on Linux, bash on macOS.

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve Python interpreter (python3 preferred, python fallback).
# If neither is available, fail-open immediately.
# ---------------------------------------------------------------------------
PY=""
if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
fi

[ -z "$PY" ] && exit 0  # fail-open: no Python

# ---------------------------------------------------------------------------
# Get REPO_ROOT — fail-open if not in a git repo
# ---------------------------------------------------------------------------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
[ -z "$REPO_ROOT" ] && exit 0

# ---------------------------------------------------------------------------
# Main Python logic: read stdin, detect criteria, write correlation file.
#
# Python code avoids single quotes so it can be embedded in a bash
# single-quoted variable (same pattern as phase-gate.sh and tdd-gate.sh).
# Values needing dynamic substitution are passed via environment variables.
# Exit codes: 0 = pass/fail-open, 2 = block.
# ---------------------------------------------------------------------------
_PYTHON_MAIN='
import hashlib, json, os, re, sys
from datetime import datetime, timezone

REPO_ROOT = os.environ.get("_TR_REPO_ROOT", "")
PHASE_FILE = os.path.join(REPO_ROOT, ".armature", "session", "phase")

# ---- 1. Read stdin bytes (preserve NUL for detection) ----
try:
    raw = sys.stdin.buffer.read()
except Exception:
    sys.exit(0)

# ---- 2. NUL-byte rejection (defense-in-depth) ----
if b"\x00" in raw:
    sys.stderr.write("WARN [TASK-001]: stdin payload contains NUL byte — skipping.\n")
    sys.exit(0)

# ---- 3. Decode and parse JSON ----
try:
    payload_str = raw.decode("utf-8", errors="replace")
    data = json.loads(payload_str)
except Exception:
    sys.exit(0)

# ---- 4. Determine event mode and extract prompt ----
tool_name = data.get("tool_name")
scope = data.get("scope")

prompt = None
event_tool_name = None
if tool_name in ("Task", "Agent"):
    ti = data.get("tool_input", {})
    prompt = (
        ti.get("prompt")
        or ti.get("description")
        or ti.get("task")
        or data.get("prompt")
    )
    event_tool_name = tool_name
elif tool_name is None and scope is not None:
    prompt = data.get("prompt") or data.get("subagent_prompt")
    event_tool_name = "SubagentStart"
else:
    sys.exit(0)

if not prompt or not isinstance(prompt, str):
    sys.exit(0)

# ---- 4b. Normalize line endings (CRLF and CR-only) ----
prompt = prompt.replace("\r\n", "\n").replace("\r", "\n")

# ---- 5. Hotfix bypass ----
# ASCII-only strip (M3 CP3 lesson: Unicode whitespace bypass via .strip()
# without args is a known attack vector).
if os.path.isfile(PHASE_FILE):
    try:
        with open(PHASE_FILE, "rb") as pf:
            phase_raw = pf.read()
        if not any(b < 32 and b not in (9, 10, 13) for b in phase_raw):
            phase_val = phase_raw.decode("utf-8", errors="replace").strip(" \t\n\r")
            if phase_val == "Hotfix":
                sys.stderr.write(
                    "ADVISORY: Hotfix phase active — TASK-001 bypass per TASK-001\n"
                )
                sys.exit(0)
    except Exception:
        pass

# ---- 6. Criterion detection ----

STRICT_HEADING_RE = re.compile(
    r"(^#{1,6}\s+Acceptance\s+Criteria\s*$"
    r"|^\*\*Acceptance\s+Criteria:\*\*"
    r"|^Acceptance\s+criteria:\s*$)",
    re.IGNORECASE | re.MULTILINE,
)

LIST_ITEM_RE = re.compile(r"^\s*[-*+]|\s*\d+\.", re.MULTILINE)
CRITERION_KEYWORDS = re.compile(
    r"\b(must|should|verify|assert|expect|given|when|then|check|test|pass)\b",
    re.IGNORECASE,
)


def _extract_list_items_after(text, start_pos):
    lines = text[start_pos:].split("\n")
    items = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if LIST_ITEM_RE.match(line):
            in_block = True
            item_text = re.sub(r"^(\s*[-*+]\s*|\s*\d+\.\s*)", "", line).strip()
            if item_text:
                items.append(item_text)
        elif stripped == "" and in_block:
            if items:
                break
        elif in_block and stripped:
            break
    return items


def detect_strict(text):
    m = STRICT_HEADING_RE.search(text)
    if not m:
        return False, [], ""
    after_pos = m.end()
    items = _extract_list_items_after(text, after_pos)
    if not items:
        return False, [], ""
    end_offset = after_pos + len("\n".join(items)) + 50
    criteria_raw = text[m.start():min(end_offset, len(text))]
    return True, items, criteria_raw


def detect_lenient(text):
    lines = text.split("\n")
    all_items = []
    for line in lines:
        if LIST_ITEM_RE.match(line):
            item_text = re.sub(r"^(\s*[-*+]\s*|\s*\d+\.\s*)", "", line).strip()
            if item_text:
                all_items.append(item_text)
    if len(all_items) < 2:
        return False, [], ""
    kw_items = [item for item in all_items if CRITERION_KEYWORDS.search(item)]
    if len(kw_items) >= 2:
        return True, kw_items, "\n".join("- " + i for i in kw_items)
    return False, [], ""


strict_ok, strict_items, strict_raw = detect_strict(prompt)
match_mode = None
criteria_items = []
criteria_raw = ""

if strict_ok:
    match_mode = "strict"
    criteria_items = strict_items
    criteria_raw = strict_raw
else:
    lenient_ok, lenient_items, lenient_raw = detect_lenient(prompt)
    if lenient_ok:
        match_mode = "lenient"
        criteria_items = lenient_items
        criteria_raw = lenient_raw

# ---- 7. Block or pass ----
if match_mode is None:
    sys.stderr.write(
        "BLOCK [TASK-001]: Task requires acceptance criteria before delegation per TASK-001\n"
    )
    sys.exit(2)

if match_mode == "lenient":
    sys.stderr.write(
        "WARN [TASK-001]: Acceptance criteria found (lenient match) — "
        "canonical ## Acceptance Criteria heading recommended\n"
    )

# ---- 8. Write correlation file (D3) ----
normalized = re.sub(r"\s+", " ", prompt.lower()).strip()
prompt_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

delegations_dir = os.path.join(REPO_ROOT, ".armature", "session", "active-delegations")
try:
    os.makedirs(delegations_dir, exist_ok=True)
    corr_file = os.path.join(delegations_dir, prompt_hash + ".json")
    corr_data = {
        "prompt_hash": prompt_hash,
        "criteria_raw": criteria_raw,
        "criteria_items": criteria_items,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool_name": event_tool_name,
    }
    with open(corr_file, "w", encoding="utf-8") as cf:
        json.dump(corr_data, cf, indent=2)
except Exception as exc:
    sys.stderr.write("WARN [TASK-001]: Could not write correlation file: " + str(exc) + "\n")

sys.exit(0)
'

export _TR_REPO_ROOT="$REPO_ROOT"
_MAIN_RC=0
if command -v python3 >/dev/null 2>&1; then
    python3 -c "$_PYTHON_MAIN" || _MAIN_RC=$?
elif command -v python >/dev/null 2>&1; then
    python -c "$_PYTHON_MAIN" || _MAIN_RC=$?
fi
exit "$_MAIN_RC"
