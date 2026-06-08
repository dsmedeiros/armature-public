"""Shared red-team trigger detection + marker validation.

Used by both:
  - .armature/hooks/auto-reviewer.sh (PostToolUse(Agent) — advisory)
  - .armature/hooks/pre-pr-create.sh (PreToolUse(Bash) — blocking on gh pr create
    when ARMATURE_RED_TEAM_ENFORCE=true)

Extracted to a shared library to honor the single-source-of-truth principle —
duplicating ~250 LOC of embedded Python across two hooks creates drift risk for
trigger thresholds, content_fingerprint algorithm, and marker validation.

The module exposes two public functions plus thresholds:

    RED_TEAM_KEYWORDS               # list[str]
    RED_TEAM_LOC_THRESHOLD          # int = 500
    RED_TEAM_COMPONENT_THRESHOLD    # int = 2

    compute_content_fingerprint(repo_root) -> str
    evaluate_red_team(repo_root, *, deliverable_text="", severity="", force_env="")
        -> dict

The algorithm of compute_content_fingerprint is BYTE-IDENTICAL to the
embedded _compute_content_fingerprint() that shipped in canonical Armature.
Any change to the algorithm would invalidate every marker file in flight;
treat as load-bearing.

Backward compat: this module is internal to the .armature/ governance
scaffolding and not consumed by any external system.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess


# ---------------------------------------------------------------------------
# Trigger thresholds — match the values in canonical Armature.
# Any change here MUST also update:
#   - .armature/personas/orchestrator.md "Red-team trigger conditions"
# ---------------------------------------------------------------------------

RED_TEAM_KEYWORDS = [
    "CRITICAL",
    "cross-cutting",
    "new invariant",
    "new ADR",
    "schema change",
]

RED_TEAM_LOC_THRESHOLD = 500
RED_TEAM_COMPONENT_THRESHOLD = 2


# ---------------------------------------------------------------------------
# Git helpers — best-effort, silent on failure (advisory-hook contract).
# ---------------------------------------------------------------------------


def _run_git(repo_root, args, default=""):
    """Run a git subcommand under repo_root; return stdout or default on any error.

    Timeout is 5s per call (matches the Claude Code hook timeout budget).
    """
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return default


def _detect_base_ref(repo_root):
    """Return the first resolvable ref among main / origin/main / master / origin/master.

    origin/main covers shallow clones where main is not a local branch but the
    remote tracker exists. Returns '' if none resolve (shallow clone of a
    repo without main/master; treat trigger-detection LOC/components silently
    skipped).
    """
    for candidate in ("main", "origin/main", "master", "origin/master"):
        if _run_git(repo_root, ["rev-parse", "--verify", "--quiet", candidate]).strip():
            return candidate
    return ""


# ---------------------------------------------------------------------------
# Content fingerprint — load-bearing algorithm. Marker files in flight encode
# their fingerprint under this algorithm; changes invalidate every marker
# until rewritten.
# ---------------------------------------------------------------------------


def compute_content_fingerprint(repo_root):
    """SHA-256 fingerprint of all working-tree file content, by path.

    Algorithm (deterministic; orchestrator persona "Red-Team Marker Write
    Protocol" documents the fingerprint computation requirement):
      1. List tracked files via `git ls-files`.
      2. List untracked-but-not-gitignored files via
         `git ls-files --others --exclude-standard`.
      3. Sort the UNION of both lists lexicographically (deduplicating).
      4. For each path: SHA-256 update with the path bytes + LF + chunked
         file content (65 KiB chunks for memory efficiency).
      5. Return hex digest.

    Files listed by git but missing on disk (unstaged deletions, unstaged
    move-source) are skipped ENTIRELY — neither path nor content hashed.
    This preserves commit-invariance when the orchestrator stages and
    commits a deletion: post-commit the path drops from ls-files; pre-commit
    it was in ls-files but absent from disk. Both produce the same
    fingerprint.

    Trade-offs (orchestrator persona "Red-Team Marker Write Protocol",
    fingerprint note, enumerates):
      - File mode (chmod) changes are NOT reflected (content unchanged).
      - Rename WITHOUT content change DOES invalidate the marker because
        the (path + content) pair changed.
      - .gitignore changes that move files between tracked/untracked DO
        change the fingerprint (different paths visited).
      - Symlinks are followed via os.path.isfile.
      - Performance: O(total file content) per call; chunked 65 KiB reads.

    Unreadable files contribute their path but skip content (silent skip
    on content per advisory-hook contract).
    """
    h = hashlib.sha256()
    tracked_raw = _run_git(repo_root, ["ls-files"]).strip()
    untracked_raw = _run_git(
        repo_root, ["ls-files", "--others", "--exclude-standard"]
    ).strip()
    tracked_paths = (
        [p.strip() for p in tracked_raw.split("\n") if p.strip()]
        if tracked_raw
        else []
    )
    untracked_paths = (
        [p.strip() for p in untracked_raw.split("\n") if p.strip()]
        if untracked_raw
        else []
    )
    all_paths = sorted(set(tracked_paths) | set(untracked_paths))
    for path in all_paths:
        abs_path = os.path.join(repo_root, path)
        if not os.path.isfile(abs_path):
            # Skip ENTIRELY (do not update hash with path bytes) when the
            # file is listed by git but missing from disk. Preserves
            # commit-invariance across deletions/renames.
            continue
        h.update(path.encode("utf-8") + b"\n")
        try:
            with open(abs_path, "rb") as fp:
                while True:
                    chunk = fp.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
        except Exception:
            # Permissions error, file removed mid-read — path bytes still
            # hashed above so the marker reflects file-exists-at-path but
            # content unverifiable. Silent skip on content per advisory-
            # hook contract.
            continue
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Diff-stat parsing.
# ---------------------------------------------------------------------------


_LOC_INSERTION_RE = re.compile(r"(\d+) insertion")
_LOC_DELETION_RE = re.compile(r"(\d+) deletion")


def _sum_loc(shortstat):
    """Parse `git diff --shortstat` insertions + deletions; 0 on parse failure."""
    if not shortstat:
        return 0
    try:
        ins_match = _LOC_INSERTION_RE.search(shortstat)
        del_match = _LOC_DELETION_RE.search(shortstat)
        return (int(ins_match.group(1)) if ins_match else 0) + (
            int(del_match.group(1)) if del_match else 0
        )
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Top-level evaluator.
# ---------------------------------------------------------------------------


def evaluate_red_team(
    repo_root,
    *,
    deliverable_text="",
    severity="",
    force_env="",
):
    """Evaluate red-team trigger conditions and marker status.

    Args:
        repo_root: absolute path to repo root.
        deliverable_text: text to scan for RED_TEAM_KEYWORDS; empty for
            pre-pr-create.sh path where no Agent payload is available.
        severity: severity string from the Agent payload; empty when N/A.
        force_env: value of the FORCE_RED_TEAM env var ('1', 'true', or
            other). Pass the env var verbatim; the function checks for
            ('1', 'true').

    Returns a dict:
        {
            'triggered': bool,
            'reasons': list[str],          # e.g. ['loc:612>=500', 'components:3>=2']
            'loc_total': int,              # 0 if base ref unresolvable
            'components': list[str],       # sorted top-level component names
            'marker_status': str,          # 'valid' | 'stale' | 'missing'
                                           #  | 'no_branch' | 'malformed'
                                           #  | 'unmatched_verdict'
                                           #  'stale' is also used with reason
                                           #  'marker-stale:branch-mismatch' when the
                                           #  marker's 'branch' field does not equal the
                                           #  current full branch name (cross-branch replay
                                           #  protection — the in-file 'branch' field is
                                           #  authoritative over the path-derived slug).
            'marker_verdict': str,         # upper-cased verdict from marker, else ''
            'content_fingerprint': str,    # runtime fingerprint; '' when triggered=False
                                           #  or when no marker file is present
            'pending_status': str,         # 'present' | 'absent'
        }

    Marker validity (all three conditions must hold to suppress):
        1. verdict ∈ {APPROVED, PASS}
        2. stored content_fingerprint matches current working tree
        3. marker's 'branch' field equals the current full branch name (un-normalized)
    Condition 3 prevents cross-branch marker replay: two branches that normalize to
    the same slug (e.g. feature/foo-bar and feature/foo/bar) share a marker path but
    are disambiguated by the in-file 'branch' field. A marker absent the 'branch' field
    is treated as not suppressing (fail-safe). The orchestrator MUST write the 'branch'
    field (full un-normalized name) when writing a marker.

    The function does NOT consult ARMATURE_RED_TEAM_ENFORCE — that is the
    caller's policy decision (advisory vs blocking). The function only
    reports facts: triggered? marker valid?

    The function does NOT mutate state (no marker writes, no logging).
    """
    reasons = []
    triggered = False

    # ---- Forced + payload-derived triggers ----
    if force_env in ("1", "true"):
        triggered = True
        reasons.append("env:FORCE_RED_TEAM")

    if severity == "critical":
        triggered = True
        reasons.append("severity=critical")

    if deliverable_text:
        for kw in RED_TEAM_KEYWORDS:
            if kw in deliverable_text:
                triggered = True
                reasons.append("keyword:" + kw)

    # ---- Pending-advisory check ----
    # Phase A (`auto-reviewer.sh`) can fire red-team=true on payload-derived
    # triggers (severity=critical, RED_TEAM_KEYWORDS hit) that are TRANSIENT
    # — they live only in the Agent payload of one specific implementer
    # delivery. By the time `pre-pr-create.sh` (Phase B) runs at
    # `gh pr create`, the Agent payload is gone; Phase B calls this function
    # with deliverable_text="" and severity="", so those triggers do NOT
    # re-fire. If LOC/components/FORCE also do not fire (small,
    # single-component change), Phase B sees triggered=False and would
    # ALLOW the PR even though Phase A had flagged it.
    #
    # Fix: Phase A persists "this branch had a red-team trigger" via a
    # pending-advisory file at
    #   .armature/session/pending-red-team-${branch//\//-}.json
    # written by `record_pending_advisory` (called from auto-reviewer.sh
    # whenever red-team=true fires). Phase B reads it as an additional
    # trigger source.
    #
    # The pending file persists until either:
    #   1. The orchestrator writes a PASS marker for this branch and
    #      also deletes the pending file (documented in orchestrator
    #      persona "Red-Team Marker Write Protocol"), OR
    #   2. The operator manually deletes it (auditable; pending files
    #      are gitignored under .armature/session/*).
    #
    # The pending file is checked BEFORE the marker-validation block.
    # Rationale: the marker block is gated on `triggered=True`; if the
    # pending file is the only trigger source, we must flip triggered=True
    # first so the marker block runs. A valid PASS marker then takes
    # precedence by flipping triggered back to False with a marker-suppress
    # reason — so the marker still suppresses (pending is the entry signal;
    # marker is the override).
    current_branch = _run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    on_excluded_ref = current_branch in ("HEAD", "") or current_branch.startswith("bc/")

    base_ref = _detect_base_ref(repo_root) if not on_excluded_ref else ""

    loc_total = 0
    components_sorted = []

    if base_ref:
        shortstat_committed = _run_git(
            repo_root, ["diff", "--shortstat", base_ref + "...HEAD"]
        ).strip()
        shortstat_uncommitted = _run_git(
            repo_root, ["diff", "--shortstat", "HEAD"]
        ).strip()

        # Untracked: not in any git diff.
        # Count newlines in non-binary files (NUL-byte heuristic = binary).
        untracked = _run_git(
            repo_root, ["ls-files", "--others", "--exclude-standard"]
        ).strip()
        untracked_loc = 0
        for u_path in (untracked.split("\n") if untracked else ()):
            u_path = u_path.strip()
            if not u_path:
                continue
            u_abs = os.path.join(repo_root, u_path)
            if not os.path.isfile(u_abs):
                continue
            try:
                with open(u_abs, "rb") as uf:
                    u_content = uf.read()
                if b"\x00" in u_content[:8192]:
                    continue
                untracked_loc += u_content.count(b"\n")
            except Exception:
                continue

        loc_total = (
            _sum_loc(shortstat_committed)
            + _sum_loc(shortstat_uncommitted)
            + untracked_loc
        )

        if loc_total >= RED_TEAM_LOC_THRESHOLD:
            triggered = True
            reasons.append(
                "loc:" + str(loc_total) + ">=" + str(RED_TEAM_LOC_THRESHOLD)
            )

        # Component union: (a) committed + (b) uncommitted + (c) untracked.
        name_only_committed = _run_git(
            repo_root, ["diff", "--name-only", base_ref + "...HEAD"]
        ).strip()
        name_only_uncommitted = _run_git(
            repo_root, ["diff", "--name-only", "HEAD"]
        ).strip()
        all_paths = []
        for block in (name_only_committed, name_only_uncommitted, untracked):
            if block:
                all_paths.extend(block.split("\n"))

        components = set()
        for path in all_paths:
            path = path.strip()
            if not path:
                continue
            parts = path.split("/")
            if len(parts) >= 2:
                # Top-level component = first TWO segments (e.g. pkg/policy,
                # cmd/sidecar). Single-segment paths (root files like
                # CLAUDE.md) are their own component.
                components.add(parts[0] + "/" + parts[1])
            elif parts:
                components.add(parts[0])
        components_sorted = sorted(components)

        if len(components_sorted) >= RED_TEAM_COMPONENT_THRESHOLD:
            triggered = True
            reasons.append(
                "components:"
                + str(len(components_sorted))
                + ">="
                + str(RED_TEAM_COMPONENT_THRESHOLD)
            )

    # ---- Pending-advisory check (runs BEFORE marker check) ----
    # When pending file is the only trigger source, we must still run
    # marker validation below — but the marker block is gated on
    # `triggered=True`. So we check pending FIRST: if present, flip
    # triggered=True so the marker block runs and can suppress on PASS.
    # Order: force/severity/keyword/LOC/components -> pending -> marker.
    pending_status = "absent"
    if current_branch and not on_excluded_ref:
        pending_branch_pre = current_branch.replace("/", "-")
        pending_path_pre = os.path.join(
            repo_root,
            ".armature",
            "session",
            "pending-red-team-" + pending_branch_pre + ".json",
        )
        if os.path.isfile(pending_path_pre):
            pending_status = "present"
            if not triggered:
                triggered = True
                reasons.append("pending-advisory:phase-a-flagged")

    # ---- Marker file validation (only when triggered) ----
    #
    # Marker validation is gated on `triggered=True` to match Phase A's
    # behavior byte-for-byte. The current PostToolUse(Agent) hook only
    # enters the marker-suppression block when `red_team and current_branch`
    # — i.e. only when at least one trigger fired. Running marker validation
    # on every call would surface "marker-stale" reasons even on benign
    # commits (no triggers fired) and would change Phase A's HTML output.
    #
    # Implication for pre-pr-create.sh: if triggered=False, the PR is not
    # a red-team candidate; the marker is irrelevant. Block decision is
    # `triggered AND not marker_valid` — which is False when triggered=False
    # regardless of marker state. The gate is correct for both callers.
    #
    # content_fingerprint is also computed lazily only when needed: when
    # triggered=True and a marker file exists. This avoids per-call O(repo)
    # I/O on no-trigger paths (the common case).
    content_fingerprint = ""
    marker_status = "missing"
    marker_verdict = ""

    if triggered and current_branch:
        marker_branch = current_branch.replace("/", "-")
        marker_path = os.path.join(
            repo_root, ".armature", "session", "red-team-" + marker_branch + ".json"
        )
        if os.path.isfile(marker_path):
            try:
                with open(marker_path, "r", encoding="utf-8") as mf:
                    marker_data = json.load(mf)
                marker_verdict = str(marker_data.get("verdict", "")).upper()
                marker_fingerprint = str(
                    marker_data.get("content_fingerprint", "")
                ).strip()
                if marker_verdict not in ("APPROVED", "PASS"):
                    marker_status = "unmatched_verdict"
                elif not marker_fingerprint:
                    marker_status = "stale"  # missing-content-fingerprint-field
                    reasons.append("marker-stale:missing-content-fingerprint-field")
                else:
                    content_fingerprint = compute_content_fingerprint(repo_root)
                    if marker_fingerprint != content_fingerprint:
                        marker_status = "stale"
                        reasons.append("marker-stale:content-fingerprint-mismatch")
                    else:
                        # Fingerprint matches — now check the in-file branch field.
                        # This guards against cross-branch marker replay: two branch
                        # names that differ only in slash vs hyphen (e.g.
                        # feature/foo-bar and feature/foo/bar) normalize to the same
                        # filename slug. The in-file 'branch' field records the FULL
                        # un-normalized branch name and is authoritative.
                        marker_branch = str(marker_data.get("branch", "")).strip()
                        if marker_branch != current_branch:
                            # Branch field absent (empty after get default) or does
                            # not match the current branch — treat as stale. Do NOT
                            # suppress: fail-safe (keep triggered=True).
                            marker_status = "stale"
                            reasons.append("marker-stale:branch-mismatch")
                        else:
                            marker_status = "valid"
                            # Marker SUPPRESSES the trigger (Phase A semantic).
                            # Replaces reasons with a single suppress tag
                            # identifying the marker.
                            marker_sha_informational = str(
                                marker_data.get("sha", "")
                            ).strip()
                            suppress_tag = "marker-suppress:" + marker_verdict
                            if marker_sha_informational:
                                suppress_tag += "@" + marker_sha_informational[:7]
                            triggered = False
                            reasons = [suppress_tag]
            except Exception:
                marker_status = "malformed"
    elif not current_branch:
        marker_status = "no_branch"

    # Note: pending-advisory check runs BEFORE the marker block above (see
    # "Pending-advisory check" section). A valid PASS marker still takes
    # precedence — it flips triggered back to False with marker-suppress
    # reason. The marker_status field reports the marker's state; the
    # pending_status field reports whether a pending file is present.

    return {
        "triggered": triggered,
        "reasons": reasons,
        "loc_total": loc_total,
        "components": components_sorted,
        "marker_status": marker_status,
        "marker_verdict": marker_verdict,
        "content_fingerprint": content_fingerprint,
        "pending_status": pending_status,
    }


def record_pending_advisory(repo_root, reasons):
    """Persist a Phase A red-team=true signal to a pending-advisory file.

    Called by `auto-reviewer.sh` whenever it computes red-team=true for ANY
    trigger (payload-derived or git-derived). The companion check in
    `evaluate_red_team` reads this file on subsequent calls so transient
    payload-derived triggers (severity, keywords) are not lost between
    Phase A (PostToolUse(Agent)) and Phase B (PreToolUse(Bash) on
    gh pr create).

    The file path is `.armature/session/pending-red-team-${branch//\\//-}.json`
    — same canonicalisation scheme as the marker file. It is gitignored via
    `.armature/.gitignore` (`session/*` rule).

    Schema:
        {
            "reasons": [str],          # exact reason list from evaluate_red_team
            "timestamp": str,          # ISO-8601 UTC
        }

    The orchestrator MUST delete this file when writing a PASS marker
    (documented in orchestrator persona "Red-Team Marker Write Protocol").

    Errors are silently swallowed — this is an advisory side-effect, not
    a critical-path action; failing to write must not abort the hook.
    """
    current_branch = _run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if not current_branch or current_branch in ("HEAD", "") or current_branch.startswith("bc/"):
        return
    pending_branch = current_branch.replace("/", "-")
    pending_path = os.path.join(
        repo_root,
        ".armature",
        "session",
        "pending-red-team-" + pending_branch + ".json",
    )
    try:
        import datetime
        os.makedirs(os.path.dirname(pending_path), exist_ok=True)
        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "reasons": list(reasons),
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                },
                f,
            )
    except Exception:
        pass


def clear_pending_advisory(repo_root):
    """Remove the pending-advisory file for the current branch, if present.

    Called by the orchestrator after a PASS marker is written. Idempotent;
    no error if the file is absent.
    """
    current_branch = _run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if not current_branch or current_branch in ("HEAD", "") or current_branch.startswith("bc/"):
        return
    pending_branch = current_branch.replace("/", "-")
    pending_path = os.path.join(
        repo_root,
        ".armature",
        "session",
        "pending-red-team-" + pending_branch + ".json",
    )
    try:
        if os.path.isfile(pending_path):
            os.unlink(pending_path)
    except Exception:
        pass
