"""
End-to-end integration test for the M4 discipline pipeline (CP1–CP4).

Proves that inject-context.sh correctly assembles discipline content from the
real corpus files and real triggers.yaml when given a scope agents.md that
carries BOTH an explicit discipline tag and an invariant that maps to a
separate discipline.

Specifically:
  - discipline-tags: [adr-process]   → fires adr-process via explicit trigger
  - invariants: [TDD-001]            → fires tdd-workflow via invariant trigger
  - Both fired disciplines appear as ### subsections with real body content
  - Attribution block lists both disciplines
  - Hook exits 0

This test is the bookend for M4: CP1 (corpus) + CP2 (triggers.yaml) +
CP3 (inject-context.sh composition) + CP4 (agents.md frontmatter) must all
work together for this test to pass.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from .helpers import subagent_start_event


# ---------------------------------------------------------------------------
# Skip guard — same bash guard applied throughout the test suite
# ---------------------------------------------------------------------------
BASH_BIN = shutil.which("bash")
if BASH_BIN is None:
    pytest.skip("bash not available on PATH", allow_module_level=True)


# ---------------------------------------------------------------------------
# Helper: copy a subset of real disciplines + triggers into a temp repo
# ---------------------------------------------------------------------------

def _setup_integration_repo(
    tmp_armature: Path,
    real_repo_root: Path,
    discipline_ids: list,
) -> Path:
    """
    Populate tmp_armature's .armature/disciplines/ with:
      - triggers.yaml from the live repo
      - one {id}.md file per discipline_id from the live corpus

    Returns the disciplines directory path.
    """
    real_disciplines = real_repo_root / ".armature" / "disciplines"
    tmp_disciplines = tmp_armature / ".armature" / "disciplines"
    tmp_disciplines.mkdir(parents=True, exist_ok=True)

    # Copy triggers.yaml from the live repo
    real_triggers = real_disciplines / "triggers.yaml"
    assert real_triggers.exists(), f"Live triggers.yaml not found at {real_triggers}"
    shutil.copy(str(real_triggers), str(tmp_disciplines / "triggers.yaml"))

    # Copy each requested discipline file
    for disc_id in discipline_ids:
        src = real_disciplines / f"{disc_id}.md"
        assert src.exists(), f"Live discipline file not found: {src}"
        shutil.copy(str(src), str(tmp_disciplines / f"{disc_id}.md"))

    return tmp_disciplines


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------

def test_full_m4_pipeline_end_to_end(run_hook, tmp_armature, repo_root):
    """
    Verify that inject-context.sh correctly composes discipline content from
    real corpus files using the real triggers.yaml.

    Scope carries:
      discipline-tags: [adr-process]   -> explicit trigger fires adr-process
      invariants: [TDD-001]            -> invariant trigger fires tdd-workflow

    Expected output:
      - ## Active Disciplines header
      - ### adr-process subsection with non-empty body (explicit trigger)
      - ### tdd-workflow subsection with non-empty body (invariant trigger)
      - <!-- DISCIPLINE-ATTRIBUTION block listing both fired disciplines
      - Hook exit code 0
    """
    # -- Step 1: Seed the temp repo with a subset of real discipline files ----
    disciplines_to_copy = [
        "adr-process",
        "tdd-workflow",
        "definition-of-done",
        "clean-code",
    ]
    _setup_integration_repo(tmp_armature, repo_root, disciplines_to_copy)

    # -- Step 2: Create a scope agents.md with both trigger types ------------
    scope_dir = tmp_armature / "integration_scope"
    scope_dir.mkdir(parents=True, exist_ok=True)
    (scope_dir / "agents.md").write_text(
        "---\n"
        "scope: integration_scope\n"
        "governs: Integration test scope for M4 bookend\n"
        "adrs: [ADR-0001]\n"
        "invariants: ['TDD-001']\n"
        "discipline-tags: ['adr-process']\n"
        "---\n\n"
        "# Integration Scope\n\n"
        "This scope exists solely for the M4 end-to-end integration test.\n"
    )

    # -- Step 3: Invoke inject-context.sh with the scope payload --------------
    payload = subagent_start_event(scope=scope_dir.as_posix())
    result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))

    # -- Step 4: Hook must always exit 0 (informational, never a gate) --------
    assert result.returncode == 0, (
        f"inject-context.sh exited {result.returncode}.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    stdout = result.stdout

    # -- Step 5: ## Active Disciplines header must be present -----------------
    assert "## Active Disciplines" in stdout, (
        "Expected '## Active Disciplines' section header in output.\n"
        f"stdout:\n{stdout}"
    )

    # -- Step 6: adr-process subsection must appear with real body content ----
    assert "### adr-process" in stdout, (
        "Expected '### adr-process' subsection (explicit trigger via discipline-tags).\n"
        f"stdout:\n{stdout}"
    )
    # The real adr-process.md contains "docs/adr/" in its body — verify non-empty body
    assert "docs/adr/" in stdout, (
        "Expected real adr-process body content ('docs/adr/') to appear.\n"
        f"stdout:\n{stdout}"
    )

    # -- Step 7: tdd-workflow subsection must appear with real body content ---
    assert "### tdd-workflow" in stdout, (
        "Expected '### tdd-workflow' subsection (invariant trigger via TDD-001).\n"
        f"stdout:\n{stdout}"
    )
    # The real tdd-workflow.md body contains "Red-Green-Refactor"
    assert "Red-Green-Refactor" in stdout, (
        "Expected real tdd-workflow body content ('Red-Green-Refactor') to appear.\n"
        f"stdout:\n{stdout}"
    )

    # -- Step 8: Attribution block must be present and list both disciplines --
    assert "<!-- DISCIPLINE-ATTRIBUTION" in stdout, (
        "Expected '<!-- DISCIPLINE-ATTRIBUTION' block in output.\n"
        f"stdout:\n{stdout}"
    )

    # Extract the attribution block for targeted assertions
    attr_start = stdout.find("<!-- DISCIPLINE-ATTRIBUTION")
    attr_end = stdout.find("-->", attr_start)
    assert attr_end > attr_start, "Attribution block not closed with -->"
    attribution_block = stdout[attr_start : attr_end + 3]

    assert "adr-process" in attribution_block, (
        "Expected 'adr-process' to appear in DISCIPLINE-ATTRIBUTION block.\n"
        f"Attribution block:\n{attribution_block}"
    )
    assert "tdd-workflow" in attribution_block, (
        "Expected 'tdd-workflow' to appear in DISCIPLINE-ATTRIBUTION block.\n"
        f"Attribution block:\n{attribution_block}"
    )
    assert "fired:" in attribution_block, (
        "Expected 'fired:' field in DISCIPLINE-ATTRIBUTION block.\n"
        f"Attribution block:\n{attribution_block}"
    )
    assert "selected:" in attribution_block, (
        "Expected 'selected:' field in DISCIPLINE-ATTRIBUTION block.\n"
        f"Attribution block:\n{attribution_block}"
    )
    assert "truncated:" in attribution_block, (
        "Expected 'truncated:' field in DISCIPLINE-ATTRIBUTION block.\n"
        f"Attribution block:\n{attribution_block}"
    )
    assert "trigger_modes:" in attribution_block, (
        "Expected 'trigger_modes:' field in DISCIPLINE-ATTRIBUTION block.\n"
        f"Attribution block:\n{attribution_block}"
    )


# ---------------------------------------------------------------------------
# Skipped placeholder — kept per M4 plan skip-count contract
# ---------------------------------------------------------------------------

@pytest.mark.skip(
    reason=(
        "manual verification: content trigger integration requires orchestrator "
        "pre-evaluation; hook-level test cannot exercise this path."
    )
)
def test_content_trigger_integration_manual_only():
    """
    Content triggers (type: content) are evaluated by the orchestrator at Phase C
    pre-flight, not by inject-context.sh.  Hook-level integration testing of this
    path is deferred per M4 plan D4/D6.  Verified manually by supplying
    'discipline-tags: [interactive-user-input]' as an explicit override.
    """
    pass
