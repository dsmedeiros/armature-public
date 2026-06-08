#!/usr/bin/env bash
# Armature PostToolUse(Agent) hook — auto-reviewer
# Event: PostToolUse with matcher "Agent" (primary, per Claude Code hooks docs)
#        SubagentStop (legacy fallback; cannot inject context into parent session)
# Invariant: TASK-003
#
# Wiring rationale (canonical fix #19):
#   Claude Code SubagentStop hooks are non-blocking and their stdout is
#   not captured into the parent (orchestrator) session, so the
#   AUTO-REVIEW-REQUIRED marker emitted there reaches no consumer. The
#   documented channel for injecting text into the parent session at
#   subagent completion is PostToolUse matched to the "Agent" tool, which
#   fires in the parent's execution context and supports
#   {"hookSpecificOutput": {"hookEventName": "PostToolUse",
#   "additionalContext": "..."}} stdout envelopes.
#
# Purpose:
#   Emit a structured HTML comment advisory directing the orchestrator to
#   dispatch the reviewer persona.  When red-team trigger conditions are met,
#   set red-team=true so the orchestrator also dispatches the red-team reviewer.
#
# Advisory emission contract (D4 — Orchestrator contract):
#   - The orchestrator reads the <!-- AUTO-REVIEW-REQUIRED --> HTML comment
#     from this hook's stdout as injected context.
#   - On seeing this marker, the orchestrator MUST spawn the reviewer before
#     accepting the deliverable.
#   - If red-team=true, the orchestrator MUST also spawn the red-team reviewer
#     after standard reviewer PASS.
#   - The orchestrator transcribes the advisory into .armature/session/state.md
#     under ## Pending Reviews.
#   - This hook does NOT itself spawn sub-agents — Claude Code hooks cannot do
#     that.  The hook emits a structured advisory; the orchestrator acts on it.
#   - If the orchestrator cannot find the <!-- AUTO-REVIEW-REQUIRED --> marker
#     in its context (e.g., hook output was not injected), the orchestrator
#     persona directive (TASK-003) serves as behavioral backstop.
#
# Red-team trigger conditions (D4) — red-team=true when ANY of:
#   - payload severity field equals "critical" (exact match)
#   - deliverable text contains any of (case-sensitive):
#       CRITICAL, cross-cutting, new invariant, new ADR, schema change
#   - environment variable FORCE_RED_TEAM == "1" (or "true")
#
# Always exits 0 — advisory emission hook, never blocks work.
#
# NUL-byte guard:
#   If stdin payload contains a NUL byte, emit WARN to stderr; still emit
#   the fallback HTML comment with implementer=unknown, exit 0.
#
# Hotfix bypass:
#   If .armature/session/phase == "Hotfix" (ASCII strip only),
#   emit ADVISORY to stderr but STILL emit the HTML comment (the orchestrator
#   may still need to dispatch review).  Exit 0.
#
# HTML comment sanitization:
#   Values are sanitized before emission: -- replaced with - - (cannot appear
#   inside an HTML comment), newlines stripped, values capped at 200 chars.
#
# Cross-platform: bash + Git Bash (Windows) compatible.

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve Python interpreter (python3 preferred, python fallback).
# If neither is available, emit fallback comment and exit 0.
# ---------------------------------------------------------------------------
PY=""
if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
fi

if [ -z "$PY" ]; then
    # Cannot construct a JSON envelope without Python; emit the bare HTML
    # comment as a best-effort fallback. PostToolUse will ignore unwrapped
    # stdout, but local debugging and ad-hoc test invocation still see it.
    printf '<!-- AUTO-REVIEW-REQUIRED\nimplementer=unknown\nscope=unknown\nred-team=false\nreason=no-python\n-->\n'
    exit 0
fi

# ---------------------------------------------------------------------------
# Get REPO_ROOT — fallback to pwd if not in a git repo
# ---------------------------------------------------------------------------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# ---------------------------------------------------------------------------
# Main Python logic.
#
# Python code avoids single quotes so it can be embedded in a bash
# single-quoted heredoc variable (same pattern as task-readiness.sh).
# Always exits 0.
#
# Phase B foldback refactor: trigger detection + marker validation moved
# to .armature/hooks/lib/red_team_check.py for single-source-of-truth
# with pre-pr-create.sh. The shared module is imported below; its
# evaluate_red_team() returns (triggered, reasons) replacing the
# inline Python that previously lived here.
# ---------------------------------------------------------------------------
_PYTHON_MAIN='
import io, json, os, sys

REPO_ROOT = os.environ.get("_AR_REPO_ROOT", "")
PHASE_FILE = os.path.join(REPO_ROOT, ".armature", "session", "phase")

# Add the shared hooks library to sys.path. The module is at
# .armature/hooks/lib/red_team_check.py; import deferred until after stdin
# parsing so a broken module never blocks the hook from emitting the
# fallback advisory.
_LIB_DIR = os.path.join(REPO_ROOT, ".armature", "hooks", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

# Buffer stdout so the eventual emission can be wrapped in the documented
# PostToolUse(Agent) JSON envelope when fired from Claude Code. On
# SubagentStop/legacy invocations we drain the buffer plain.
_REAL_STDOUT = sys.stdout
_BUF = io.StringIO()
sys.stdout = _BUF
_DATA_FOR_EXIT = {"data": None}

def _drain_and_exit(rc=0):
    """Flush buffered advisory to stdout in the right envelope, then exit."""
    sys.stdout = _REAL_STDOUT
    advisory = _BUF.getvalue()
    parsed = _DATA_FOR_EXIT.get("data")
    hook_event = None
    if isinstance(parsed, dict):
        hook_event = parsed.get("hook_event_name") or parsed.get("event")
    if hook_event == "PostToolUse" and advisory.strip():
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": advisory.rstrip(),
            }
        }))
    elif advisory:
        sys.stdout.write(advisory)
        if not advisory.endswith("\n"):
            sys.stdout.write("\n")
    sys.exit(rc)

# ---- Sanitize helper ----
def _sanitize(val, max_len=200):
    """Strip newlines, replace -- with - -, cap length."""
    val = str(val)
    val = val.replace("\n", " ").replace("\r", " ")
    val = val.replace("--", "- -")
    return val[:max_len]

# ---- Emit HTML comment ----
def _emit(implementer, scope, red_team, reason):
    print("<!-- AUTO-REVIEW-REQUIRED")
    print("implementer=" + _sanitize(implementer))
    print("scope=" + _sanitize(scope))
    print("red-team=" + ("true" if red_team else "false"))
    print("reason=" + _sanitize(reason))
    print("-->")

# ---- 1. Read stdin bytes (preserve NUL for detection) ----
try:
    raw = sys.stdin.buffer.read()
except Exception:
    _emit("unknown", "unknown", False, "stdin-read-error")
    _drain_and_exit(0)

# ---- 2. NUL-byte rejection ----
if b"\x00" in raw:
    sys.stderr.write("WARN [TASK-003]: stdin payload contains NUL byte — emitting fallback advisory.\n")
    _emit("unknown", "unknown", False, "nul-byte-payload")
    _drain_and_exit(0)

# ---- 3. Decode and parse JSON (fail-open: emit fallback advisory) ----
data = None
try:
    payload_str = raw.decode("utf-8", errors="replace")
    data = json.loads(payload_str)
except Exception:
    _emit("unknown", "unknown", False, "invalid-payload")
    _drain_and_exit(0)

# Record parsed payload so _drain_and_exit can detect PostToolUse envelope.
_DATA_FOR_EXIT["data"] = data

# ---- 4. Hotfix bypass — emit ADVISORY but STILL emit HTML comment ----
hotfix_active = False
if os.path.isfile(PHASE_FILE):
    try:
        with open(PHASE_FILE, "rb") as _pf:
            _phase_raw = _pf.read()
        if not any(b < 32 and b not in (9, 10, 13) for b in _phase_raw):
            _phase_val = _phase_raw.decode("utf-8", errors="replace").strip(" \t\n\r")
            if _phase_val == "Hotfix":
                sys.stderr.write(
                    "ADVISORY: Hotfix phase active — TASK-003 bypass per TASK-003\n"
                )
                hotfix_active = True
    except Exception:
        pass

# ---- 5. Extract fields ----

# implementer: probe tool_input.subagent_type FIRST per the documented
# Claude Code Agent tool_input shape (prompt/description/subagent_type/
# model), then fall back to legacy top-level fields used by SubagentStop
# payloads and older runtimes. Without the tool_input probe, every
# AUTO-REVIEW-REQUIRED advisory emitted from a real PostToolUse(Agent)
# event reports implementer=unknown and the orchestrator pending-review
# record loses the implementer identity.
implementer = None
tool_input_for_impl = data.get("tool_input")
if isinstance(tool_input_for_impl, dict):
    candidate = tool_input_for_impl.get("subagent_type")
    if isinstance(candidate, str) and candidate:
        implementer = candidate
if not implementer:
    implementer = (
        data.get("subagent_type")
        or data.get("agent_type")
        or data.get("subagent_name")
        or "unknown"
    )
if not isinstance(implementer, str) or not implementer:
    implementer = "unknown"

# scope: from scope, tool_input.scope, or working_directory
scope = data.get("scope")
if not scope:
    ti = data.get("tool_input", {})
    if isinstance(ti, dict):
        scope = ti.get("scope")
if not scope:
    scope = data.get("working_directory")
if not scope or not isinstance(scope, str):
    scope = "unknown"

# severity
severity = data.get("severity")
if not isinstance(severity, str):
    severity = None

# deliverable_text — same ordered field search as task-completion.sh (D2).
# Order matters per the documented payload shapes:
#   PostToolUse(Agent) (primary, per https://code.claude.com/docs/en/hooks):
#     tool_response.text contains the subagent final response.
#   SubagentStop (legacy): last_assistant_message contains the response.
# Other fields are defensive fallbacks for older payload shapes or Codex.
deliverable_text = None

# tool_response — PostToolUse(Agent) primary field. Claude Code may
# deliver the Agent tools final result as either a string (single plain-
# text result) or a dict containing text/content. Handle both so red-team
# trigger keywords like CRITICAL or schema change in a string-shaped
# response are still scanned.
tr_resp = data.get("tool_response")
if isinstance(tr_resp, str):
    deliverable_text = tr_resp
elif isinstance(tr_resp, dict):
    txt = tr_resp.get("text")
    if isinstance(txt, str):
        deliverable_text = txt
    elif isinstance(tr_resp.get("content"), str):
        deliverable_text = tr_resp["content"]
    elif isinstance(tr_resp.get("content"), list):
        parts = []
        for block in tr_resp["content"]:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text", "")
                if isinstance(t, str):
                    parts.append(t)
            elif isinstance(block, str):
                parts.append(block)
        if parts:
            deliverable_text = " ".join(parts)

# last_assistant_message (SubagentStop legacy field)
if deliverable_text is None:
    v = data.get("last_assistant_message")
    if isinstance(v, str):
        deliverable_text = v

# tool_result.content (legacy/fallback)
if deliverable_text is None:
    tr = data.get("tool_result")
    if isinstance(tr, dict):
        content = tr.get("content")
        if isinstance(content, str):
            deliverable_text = content
        elif isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_val = block.get("text", "")
                        if isinstance(text_val, str):
                            parts.append(text_val)
                elif isinstance(block, str):
                    parts.append(block)
            if parts:
                deliverable_text = " ".join(parts)

if deliverable_text is None:
    v = data.get("output")
    if isinstance(v, str):
        deliverable_text = v

if deliverable_text is None:
    v = data.get("result")
    if isinstance(v, str):
        deliverable_text = v

if deliverable_text is None:
    v = data.get("subagent_output")
    if isinstance(v, str):
        deliverable_text = v

if deliverable_text is None:
    v = data.get("message")
    if isinstance(v, str):
        deliverable_text = v

if deliverable_text is None:
    deliverable_text = ""

# ---- 6. Red-team evaluation via shared module (foldback refactor) ----
#
# Delegates red-team trigger detection to red_team_check.evaluate_red_team().
# This ALIGNS the trigger set of this hook with pre-pr-create.sh: previously
# this hook evaluated only FORCE_RED_TEAM / severity / keyword triggers
# inline; via the shared lib it now also evaluates LOC and component-count
# triggers and honors valid PASS-marker suppression, and records a
# pending-advisory on a trigger. Behavior expansion is intentional; the hook
# remains advisory (always exit 0).
# The shared module .armature/hooks/lib/red_team_check.py implements:
#   - FORCE_RED_TEAM / severity / keyword triggers
#   - LOC + multi-component triggers
#   - content_fingerprint algorithm (commit-invariant)
#   - marker file validation + suppression (only when triggered=True)
#
# evaluate_red_team() returns:
#   triggered: bool, reasons: list[str]
# The hook only consumes triggered and reasons.
#
# Module-unavailable fallback (TASK-003 contract):
#   If the import fails for any reason, emit the advisory with
#   reason=module-unavailable and exit 0. The hook must never block.
try:
    from red_team_check import evaluate_red_team
except Exception as _import_err:
    sys.stderr.write(
        "WARN [TASK-003]: red_team_check.py unavailable (" + repr(_import_err)
        + ") - emitting fallback advisory without red-team evaluation.\n"
    )
    _emit(implementer, scope, False, "module-unavailable")
    _drain_and_exit(0)

try:
    _rt_result = evaluate_red_team(
        REPO_ROOT,
        deliverable_text=deliverable_text,
        severity=(severity or ""),
        force_env=os.environ.get("FORCE_RED_TEAM", ""),
    )
    red_team = _rt_result["triggered"]
    reason_parts = list(_rt_result["reasons"])
except Exception as _eval_err:
    sys.stderr.write(
        "WARN [TASK-003]: red_team_check.evaluate_red_team raised ("
        + repr(_eval_err) + ") - emitting fallback advisory.\n"
    )
    _emit(implementer, scope, False, "evaluate-error")
    _drain_and_exit(0)

if red_team:
    reason = "; ".join(reason_parts) if reason_parts else "triggered"
else:
    reason = "; ".join(reason_parts) if reason_parts else "standard-review"

# ---- 6b. Persist pending-advisory state (Phase A->B bridge) ----
# When this hook fires red-team=true, write a pending-advisory file so the
# subsequent pre-pr-create.sh (Phase B blocking gate) can detect Phase A
# triggered the discipline. Required because payload-derived triggers
# (severity=critical, RED_TEAM_KEYWORDS hit) are transient — they only
# exist in the Agent payload of one specific implementer delivery; by
# gh pr create time, the payload is gone and Phase B re-computes
# evaluate_red_team with empty deliverable_text+severity. Without this
# persistence, a small single-component Agent run that triggered Phase A
# on a keyword/severity match would silently slip past Phase B.
# The pending file is gitignored (.armature/session/* rule).
#
# Defensive wrap: if record_pending_advisory raises, the HTML advisory
# comment is STILL emitted and the hook STILL exits 0.
if red_team:
    try:
        from red_team_check import record_pending_advisory
        record_pending_advisory(REPO_ROOT, reason_parts)
    except Exception as _pend_err:
        sys.stderr.write(
            "WARN [TASK-003]: record_pending_advisory raised ("
            + repr(_pend_err) + ") - pending state NOT persisted.\n"
        )

# ---- 7. Emit ----
_emit(implementer, scope, red_team, reason)
_drain_and_exit(0)
'

export _AR_REPO_ROOT="$REPO_ROOT"
_MAIN_RC=0
if command -v python3 >/dev/null 2>&1; then
    python3 -c "$_PYTHON_MAIN" || _MAIN_RC=$?
elif command -v python >/dev/null 2>&1; then
    python -c "$_PYTHON_MAIN" || _MAIN_RC=$?
fi
# Always exit 0 — advisory emission hook
exit 0
