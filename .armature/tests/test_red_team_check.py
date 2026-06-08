"""Behavior-matrix regression tests for red_team_check.py.

Runs synthetic-repository scenarios that exercise every documented branch
of `evaluate_red_team` and `compute_content_fingerprint`. Establishes the
test convention for .armature/hooks/lib/ shared modules.

Per the Phase B claim-of-invariance sub-discipline: any structural claim
in the module's docstrings (commit-invariance, byte-identity with Phase A,
suppression-on-valid-marker, gate-marker-only-when-triggered) MUST have a
synthetic test that proves it, not just prose asserting it.

Usage:
    python -m pytest .armature/tests/test_red_team_check.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Make red_team_check importable via canonical path.
# ---------------------------------------------------------------------------
_REPO_ROOT = str(
    subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
    ).strip()
)
sys.path.insert(0, os.path.join(_REPO_ROOT, ".armature", "hooks", "lib"))

import red_team_check as rtc  # noqa: E402


# ---------------------------------------------------------------------------
# Module-level helpers (shared across all test classes)
# ---------------------------------------------------------------------------

def _init_repo(path, base_branch="main"):
    """Initialize a git repo at path with a baseline commit on `base_branch`.

    Mirrors the gitignore semantics: `.armature/session/*` is gitignored
    (except `.armature/session/phase`). The `compute_content_fingerprint`
    algorithm uses `git ls-files --others --exclude-standard`, which respects
    gitignore; marker files written to `.armature/session/red-team-*.json`
    would otherwise appear as untracked and pollute the fingerprint, breaking
    suppression for tests that write a marker after measuring fingerprint.
    The dependency on this gitignore rule is documented in the algorithm
    contract; tests must replicate it to exercise real-world behavior.
    """
    subprocess.run(["git", "init", "-q", "-b", base_branch, path], check=True)
    subprocess.run(
        ["git", "-C", path, "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", path, "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", path, "config", "commit.gpgsign", "false"], check=True
    )
    # Mirror .armature/.gitignore — session/* (except phase).
    armature_dir = os.path.join(path, ".armature")
    os.makedirs(armature_dir, exist_ok=True)
    with open(os.path.join(armature_dir, ".gitignore"), "w") as f:
        f.write("session/*\n!session/phase\n")
    with open(os.path.join(path, ".gitkeep"), "w") as f:
        f.write("")
    subprocess.run(
        ["git", "-C", path, "add", ".gitkeep", ".armature/.gitignore"], check=True
    )
    subprocess.run(
        ["git", "-C", path, "commit", "-q", "-m", "baseline"], check=True
    )


_SENTINEL = object()  # sentinel for _write_marker marker_branch default


def _write_marker(
    repo, branch, *, verdict, fingerprint=None, sha="abc1234567890",
    marker_branch=_SENTINEL, path_branch=None,
):
    """Write a marker file at the canonical path for `branch`.

    Args:
        repo: path to the repo root.
        branch: the branch name used to derive the marker filename slug
            (slashes replaced with hyphens). Also used as the in-file
            'branch' field value UNLESS `marker_branch` is explicitly passed.
        verdict: marker verdict string.
        fingerprint: content_fingerprint value; omitted from JSON when None.
        sha: informational SHA stored in the marker.
        marker_branch: value to write into the in-file 'branch' field. Pass
            the sentinel (default) to use `branch` (the normal case — full
            branch name matches the slug source). Pass an explicit string
            (including '') to override — useful for testing collision scenarios
            where the file-path slug and the in-file branch name differ.
            Pass None to omit the 'branch' field entirely (tests missing-field
            fail-safe).
        path_branch: if given, use THIS value (after slug normalization) for
            the marker filename instead of `branch`. Useful for placing a
            marker at a path that a different branch would look up.

    NOTE: As of the branch-mismatch fix, markers MUST include a 'branch'
    field equal to the current full branch name to be valid. Existing tests
    that call _write_marker without `marker_branch` are automatically updated
    to write the correct 'branch' field (the default sentinel → branch).
    """
    marker_dir = os.path.join(repo, ".armature", "session")
    os.makedirs(marker_dir, exist_ok=True)
    slug_source = path_branch if path_branch is not None else branch
    canonical = slug_source.replace("/", "-")
    marker_path = os.path.join(marker_dir, "red-team-" + canonical + ".json")
    data = {
        "verdict": verdict,
        "sha": sha,
        "findings": [],
        "timestamp": "2026-05-27T00:00:00Z",
    }
    if fingerprint is not None:
        data["content_fingerprint"] = fingerprint
    # Write the in-file 'branch' field (authoritative for cross-branch replay
    # protection). Default: use `branch` (full name). Pass None to omit
    # (tests the fail-safe: absent field → does not suppress).
    effective_marker_branch = branch if marker_branch is _SENTINEL else marker_branch
    if effective_marker_branch is not None:
        data["branch"] = effective_marker_branch
    with open(marker_path, "w") as f:
        json.dump(data, f)
    return marker_path


# ===========================================================================
# ContentFingerprintTests
# ===========================================================================

class TestContentFingerprint:
    """Verify the content_fingerprint algorithm contract."""

    def test_hex_string_of_correct_length(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            fp = rtc.compute_content_fingerprint(repo)
            assert len(fp) == 64, "SHA-256 hex must be 64 chars"
            assert all(c in "0123456789abcdef" for c in fp)

    def test_same_tree_same_fingerprint(self):
        """Determinism: same tree -> same fingerprint."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            fp1 = rtc.compute_content_fingerprint(repo)
            fp2 = rtc.compute_content_fingerprint(repo)
            assert fp1 == fp2

    def test_content_change_changes_fingerprint(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            fp_before = rtc.compute_content_fingerprint(repo)
            with open(os.path.join(repo, "new_file.txt"), "w") as f:
                f.write("hello world\n")
            fp_after = rtc.compute_content_fingerprint(repo)
            assert fp_before != fp_after

    def test_commit_invariance_for_modifications(self):
        """Committing reviewed dirty state must not change the fingerprint."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            # Modify a tracked file
            with open(os.path.join(repo, ".gitkeep"), "w") as f:
                f.write("modified\n")
            fp_before_commit = rtc.compute_content_fingerprint(repo)
            subprocess.run(["git", "-C", repo, "add", ".gitkeep"], check=True)
            subprocess.run(
                ["git", "-C", repo, "commit", "-q", "-m", "mod"], check=True
            )
            fp_after_commit = rtc.compute_content_fingerprint(repo)
            assert fp_before_commit == fp_after_commit, (
                "Commit-invariance broken for modifications"
            )

    def test_commit_invariance_for_deletions(self):
        """Committing a deletion must not change the fingerprint (path absent
        on disk both pre- and post-commit)."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            # Add a file first so we have something to delete
            target = os.path.join(repo, "doomed.txt")
            with open(target, "w") as f:
                f.write("will be deleted\n")
            subprocess.run(["git", "-C", repo, "add", "doomed.txt"], check=True)
            subprocess.run(
                ["git", "-C", repo, "commit", "-q", "-m", "add doomed"],
                check=True,
            )
            # Delete the file (unstaged)
            os.unlink(target)
            fp_before_commit = rtc.compute_content_fingerprint(repo)
            # Stage and commit the deletion
            subprocess.run(
                ["git", "-C", repo, "add", "doomed.txt"], check=True
            )
            subprocess.run(
                ["git", "-C", repo, "commit", "-q", "-m", "remove doomed"],
                check=True,
            )
            fp_after_commit = rtc.compute_content_fingerprint(repo)
            assert fp_before_commit == fp_after_commit, (
                "Commit-invariance broken for deletions"
            )

    def test_untracked_files_included(self):
        """Untracked-but-not-gitignored files contribute to the fingerprint."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            fp_before = rtc.compute_content_fingerprint(repo)
            with open(os.path.join(repo, "untracked.txt"), "w") as f:
                f.write("untracked content\n")
            fp_after = rtc.compute_content_fingerprint(repo)
            assert fp_before != fp_after, (
                "Untracked files must affect the fingerprint"
            )

    def test_gitignored_files_excluded(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            with open(os.path.join(repo, ".gitignore"), "w") as f:
                f.write("ignored.txt\n")
            subprocess.run(["git", "-C", repo, "add", ".gitignore"], check=True)
            subprocess.run(
                ["git", "-C", repo, "commit", "-q", "-m", "gitignore"],
                check=True,
            )
            fp_before = rtc.compute_content_fingerprint(repo)
            with open(os.path.join(repo, "ignored.txt"), "w") as f:
                f.write("this is gitignored\n")
            fp_after = rtc.compute_content_fingerprint(repo)
            assert fp_before == fp_after, "Gitignored files must NOT affect fingerprint"


# ===========================================================================
# TriggerDetectionTests
# ===========================================================================

class TestTriggerDetection:
    """Verify trigger detection without marker validation."""

    def _ctx(self, repo):
        """Standard kwargs to evaluate_red_team for these tests."""
        return {"repo_root": repo}

    def test_no_triggers_no_marker(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            result = rtc.evaluate_red_team(**self._ctx(repo))
            assert not result["triggered"]
            assert result["reasons"] == []

    def test_force_env_triggers(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            result = rtc.evaluate_red_team(repo, force_env="1")
            assert result["triggered"]
            assert "env:FORCE_RED_TEAM" in result["reasons"]

            result = rtc.evaluate_red_team(repo, force_env="true")
            assert result["triggered"]

            result = rtc.evaluate_red_team(repo, force_env="yes")
            assert not result["triggered"], "Only '1' and 'true' should trigger"

    def test_severity_critical(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            result = rtc.evaluate_red_team(repo, severity="critical")
            assert result["triggered"]
            assert "severity=critical" in result["reasons"]

            result = rtc.evaluate_red_team(repo, severity="high")
            assert not result["triggered"]

    def test_keyword_triggers(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            for kw in rtc.RED_TEAM_KEYWORDS:
                result = rtc.evaluate_red_team(
                    repo, deliverable_text=f"some text with {kw} embedded"
                )
                assert result["triggered"], f"Keyword {kw} should trigger"
                assert "keyword:" + kw in result["reasons"]

    def test_keyword_case_sensitive(self):
        """CRITICAL triggers but 'critical' alone does not (case-sensitive)."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            result = rtc.evaluate_red_team(
                repo, deliverable_text="this is critical work"
            )
            assert not result["triggered"], "lowercase 'critical' should not trigger"

    def test_loc_threshold(self):
        """LOC trigger fires only on the BRANCH delta — synthetic tree where
        new branch has >500 LOC delta vs base."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            # Create a branch with >500 LOC of new content
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"],
                check=True,
            )
            with open(os.path.join(repo, "big.txt"), "w") as f:
                for i in range(600):
                    f.write(f"line {i}\n")
            subprocess.run(["git", "-C", repo, "add", "big.txt"], check=True)
            subprocess.run(
                ["git", "-C", repo, "commit", "-q", "-m", "big"], check=True
            )
            result = rtc.evaluate_red_team(repo)
            assert result["triggered"], "LOC > 500 should trigger"
            assert any("loc:" in r and ">=500" in r for r in result["reasons"]), (
                f"Expected loc:N>=500 in reasons; got {result['reasons']}"
            )
            assert result["loc_total"] >= 500

    def test_component_threshold(self):
        """Component trigger fires when union of changed paths spans >= 2
        top-level components."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"],
                check=True,
            )
            # Create paths in 2 top-level components
            os.makedirs(os.path.join(repo, "pkg", "alpha"), exist_ok=True)
            os.makedirs(os.path.join(repo, "cmd", "beta"), exist_ok=True)
            with open(os.path.join(repo, "pkg", "alpha", "a.txt"), "w") as f:
                f.write("a\n")
            with open(os.path.join(repo, "cmd", "beta", "b.txt"), "w") as f:
                f.write("b\n")
            subprocess.run(["git", "-C", repo, "add", "."], check=True)
            subprocess.run(
                ["git", "-C", repo, "commit", "-q", "-m", "multi-comp"],
                check=True,
            )
            result = rtc.evaluate_red_team(repo)
            assert result["triggered"]
            assert len(result["components"]) >= 2
            assert "pkg/alpha" in result["components"]
            assert "cmd/beta" in result["components"]

    def test_bc_branch_excluded(self):
        """Branches under bc/* are excluded from LOC/component checks."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "bc/2026-01-01/001"],
                check=True,
            )
            # Add a huge file that WOULD trigger LOC
            with open(os.path.join(repo, "big.txt"), "w") as f:
                for i in range(600):
                    f.write(f"line {i}\n")
            subprocess.run(["git", "-C", repo, "add", "big.txt"], check=True)
            subprocess.run(
                ["git", "-C", repo, "commit", "-q", "-m", "big"], check=True
            )
            result = rtc.evaluate_red_team(repo)
            assert not result["triggered"], (
                "bc/* branches should be excluded from LOC/component checks"
            )


# ===========================================================================
# MarkerValidationTests
# ===========================================================================

class TestMarkerValidation:
    """Verify marker file validation and suppression semantics."""

    def test_marker_valid_suppresses_trigger(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"],
                check=True,
            )
            fp = rtc.compute_content_fingerprint(repo)
            _write_marker(repo, "feature", verdict="PASS", fingerprint=fp)
            result = rtc.evaluate_red_team(repo, force_env="1")
            assert not result["triggered"], "Valid marker must suppress"
            assert result["marker_status"] == "valid"
            assert len(result["reasons"]) == 1
            assert result["reasons"][0].startswith("marker-suppress:PASS")

    def test_marker_valid_suppresses_with_approved_verdict(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"],
                check=True,
            )
            fp = rtc.compute_content_fingerprint(repo)
            _write_marker(repo, "feature", verdict="APPROVED", fingerprint=fp)
            result = rtc.evaluate_red_team(repo, force_env="1")
            assert not result["triggered"]
            assert result["reasons"][0].startswith("marker-suppress:APPROVED")

    def test_marker_stale_fingerprint(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"],
                check=True,
            )
            _write_marker(
                repo,
                "feature",
                verdict="PASS",
                fingerprint="0" * 64,  # not the real fingerprint
            )
            result = rtc.evaluate_red_team(repo, force_env="1")
            assert result["triggered"]
            assert result["marker_status"] == "stale"
            assert "marker-stale:content-fingerprint-mismatch" in result["reasons"]

    def test_marker_missing_fingerprint_field(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"],
                check=True,
            )
            _write_marker(repo, "feature", verdict="PASS")  # no fingerprint
            result = rtc.evaluate_red_team(repo, force_env="1")
            assert result["triggered"]
            assert "marker-stale:missing-content-fingerprint-field" in result["reasons"]

    def test_marker_wrong_verdict(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"],
                check=True,
            )
            fp = rtc.compute_content_fingerprint(repo)
            _write_marker(repo, "feature", verdict="FAIL", fingerprint=fp)
            result = rtc.evaluate_red_team(repo, force_env="1")
            assert result["triggered"], "FAIL verdict must not suppress"
            assert result["marker_status"] == "unmatched_verdict"

    def test_marker_branch_canonicalization(self):
        """Branches with `/` are flattened to `-` in the marker filename."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "claude/foo/bar"],
                check=True,
            )
            fp = rtc.compute_content_fingerprint(repo)
            marker_path = _write_marker(
                repo, "claude/foo/bar", verdict="PASS", fingerprint=fp
            )
            assert "red-team-claude-foo-bar.json" in marker_path
            result = rtc.evaluate_red_team(repo, force_env="1")
            assert not result["triggered"]
            assert result["marker_status"] == "valid"

    def test_marker_not_checked_when_triggered_false(self):
        """Phase A semantic: when triggered=False, marker is NOT consulted -
        even a malformed/stale marker doesn't surface in reasons."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"],
                check=True,
            )
            _write_marker(
                repo, "feature", verdict="PASS", fingerprint="0" * 64
            )
            # No FORCE_RED_TEAM, no big LOC, no critical severity
            result = rtc.evaluate_red_team(repo)
            assert not result["triggered"]
            assert result["reasons"] == [], (
                "When not triggered, marker reasons should NOT appear"
            )

    def test_marker_malformed_json(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"],
                check=True,
            )
            marker_dir = os.path.join(repo, ".armature", "session")
            os.makedirs(marker_dir, exist_ok=True)
            with open(
                os.path.join(marker_dir, "red-team-feature.json"), "w"
            ) as f:
                f.write("not valid json {{{")
            result = rtc.evaluate_red_team(repo, force_env="1")
            # Triggered remains True (FORCE_RED_TEAM); marker malformed
            assert result["triggered"]
            assert result["marker_status"] == "malformed"

    # --- Branch-field validation tests (cross-branch marker replay fix) ---

    def test_marker_with_matching_branch_field_suppresses(self):
        """Happy path: marker with correct 'branch' field suppresses (triggered=False).

        NOTE: This test (and all _write_marker-using tests) now pass `branch`
        to _write_marker which auto-writes the in-file 'branch' field equal to
        the branch name. This is the correct marker schema; the default sentinel
        wires the field automatically for all existing tests as well.
        """
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature/foo-bar"],
                check=True,
            )
            fp = rtc.compute_content_fingerprint(repo)
            # Default: marker_branch = _SENTINEL -> branch field = "feature/foo-bar"
            _write_marker(repo, "feature/foo-bar", verdict="PASS", fingerprint=fp)
            result = rtc.evaluate_red_team(repo, force_env="1")
            assert not result["triggered"], "Marker with matching branch field must suppress"
            assert result["marker_status"] == "valid"
            assert result["reasons"][0].startswith("marker-suppress:PASS")

    def test_marker_cross_branch_collision_does_not_suppress(self):
        """Collision anti-replay: marker written for feature/foo/bar (branch field =
        'feature/foo/bar') placed at the path that feature/foo-bar would read
        (same slug). Same fingerprint, valid verdict. Gate on feature/foo-bar
        must NOT be suppressed — in-file branch field is authoritative.

        This is the exact codex P2 scenario: feature/foo/bar and feature/foo-bar
        both normalize to red-team-feature-foo-bar.json, so the marker file exists
        at the path the gate looks up, but the 'branch' field inside it records
        'feature/foo/bar', which does not equal the current branch 'feature/foo-bar'.
        """
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            # Current branch is feature/foo-bar (slug: feature-foo-bar)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature/foo-bar"],
                check=True,
            )
            fp = rtc.compute_content_fingerprint(repo)
            # Write marker at path for feature/foo-bar (same slug as feature/foo/bar)
            # but with in-file branch = "feature/foo/bar" (simulates cross-branch replay).
            _write_marker(
                repo,
                "feature/foo-bar",        # path slug source
                verdict="PASS",
                fingerprint=fp,
                marker_branch="feature/foo/bar",  # WRONG branch in file
            )
            result = rtc.evaluate_red_team(repo, force_env="1")
            assert result["triggered"], (
                "Cross-branch marker replay must NOT suppress the gate"
            )
            assert result["marker_status"] == "stale", (
                "Branch-mismatch marker must be reported as stale"
            )
            assert "marker-stale:branch-mismatch" in result["reasons"], (
                f"Expected 'marker-stale:branch-mismatch' in reasons; got {result['reasons']}"
            )

    def test_marker_missing_branch_field_does_not_suppress(self):
        """Fail-safe: a marker with no 'branch' field does NOT suppress.

        Markers written before the branch-field requirement was introduced lack
        the field. The gate must treat absence as a mismatch (fail-safe: keep
        triggered=True). Pass marker_branch=None to _write_marker to omit the
        field entirely.
        """
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"],
                check=True,
            )
            fp = rtc.compute_content_fingerprint(repo)
            # marker_branch=None → 'branch' field omitted from JSON
            _write_marker(
                repo, "feature", verdict="PASS", fingerprint=fp, marker_branch=None
            )
            result = rtc.evaluate_red_team(repo, force_env="1")
            assert result["triggered"], "Marker missing 'branch' field must not suppress"
            assert result["marker_status"] == "stale"
            assert "marker-stale:branch-mismatch" in result["reasons"]


# ===========================================================================
# PendingAdvisoryTests
# ===========================================================================

class TestPendingAdvisory:
    """Phase A payload-derived triggers must propagate to Phase B via a
    pending-advisory file. evaluate_red_team treats the file as an additional
    trigger source; record_pending_advisory writes it from auto-reviewer.sh;
    clear_pending_advisory removes it after a PASS marker is written."""

    def _pending_path(self, repo, branch):
        return os.path.join(
            repo,
            ".armature",
            "session",
            "pending-red-team-" + branch.replace("/", "-") + ".json",
        )

    def test_record_pending_advisory_creates_file(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"], check=True
            )
            rtc.record_pending_advisory(repo, ["severity=critical", "keyword:CRITICAL"])
            p = self._pending_path(repo, "feature")
            assert os.path.isfile(p)
            with open(p) as f:
                data = json.load(f)
            assert "severity=critical" in data["reasons"]
            assert "timestamp" in data

    def test_record_pending_advisory_branch_canonicalization(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "claude/foo/bar"],
                check=True,
            )
            rtc.record_pending_advisory(repo, ["env:FORCE_RED_TEAM"])
            assert os.path.isfile(self._pending_path(repo, "claude/foo/bar"))

    def test_pending_advisory_triggers_phase_b(self):
        """Pending file alone (no LOC/components/keywords) must trigger
        Phase B detection."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"], check=True
            )
            # Simulate Phase A having written a pending file
            rtc.record_pending_advisory(repo, ["severity=critical"])

            # Phase B-style call: no deliverable_text, no severity
            result = rtc.evaluate_red_team(repo)
            assert result["triggered"], "Pending advisory alone must trigger Phase B"
            assert result["pending_status"] == "present"
            assert "pending-advisory:phase-a-flagged" in result["reasons"]

    def test_pending_advisory_alone_no_other_triggers(self):
        """No pending file + no triggers = not triggered."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"], check=True
            )
            result = rtc.evaluate_red_team(repo)
            assert not result["triggered"]
            assert result["pending_status"] == "absent"

    def test_valid_marker_supersedes_pending(self):
        """A valid PASS marker takes precedence over a pending file -
        the marker indicates red-team review has been completed."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"], check=True
            )
            # Write a pending file
            rtc.record_pending_advisory(repo, ["severity=critical"])
            # And a valid marker for the current state
            fp = rtc.compute_content_fingerprint(repo)
            _write_marker(repo, "feature", verdict="PASS", fingerprint=fp)
            # Force a trigger so marker validation runs
            result = rtc.evaluate_red_team(repo, force_env="1")
            assert not result["triggered"], "Valid marker must suppress pending"
            assert result["marker_status"] == "valid"
            assert result["reasons"][0].startswith("marker-suppress:")

    def test_stale_marker_does_not_suppress_pending(self):
        """A stale marker (fingerprint mismatch) does NOT suppress pending -
        the discipline is unsatisfied and Phase B must block."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"], check=True
            )
            rtc.record_pending_advisory(repo, ["severity=critical"])
            _write_marker(
                repo, "feature", verdict="PASS", fingerprint="0" * 64
            )
            result = rtc.evaluate_red_team(repo)
            # Stale marker + pending -> triggered=True (from pending)
            assert result["triggered"]
            assert result["marker_status"] == "stale"
            assert result["pending_status"] == "present"

    def test_clear_pending_advisory_removes_file(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"], check=True
            )
            rtc.record_pending_advisory(repo, ["severity=critical"])
            p = self._pending_path(repo, "feature")
            assert os.path.isfile(p)
            rtc.clear_pending_advisory(repo)
            assert not os.path.isfile(p)

    def test_clear_pending_advisory_idempotent(self):
        """No error when file is already absent."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "feature"], check=True
            )
            # Should not raise
            rtc.clear_pending_advisory(repo)
            rtc.clear_pending_advisory(repo)

    def test_pending_advisory_not_recorded_on_bc_branch(self):
        """bc/* branches are excluded from the discipline entirely."""
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            subprocess.run(
                ["git", "-C", repo, "checkout", "-q", "-b", "bc/2026-01-01/001"],
                check=True,
            )
            rtc.record_pending_advisory(repo, ["severity=critical"])
            assert not os.path.isfile(
                self._pending_path(repo, "bc/2026-01-01/001")
            )
