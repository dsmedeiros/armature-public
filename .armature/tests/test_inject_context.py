"""
Tests for inject-context.sh (HOOK-004).

Hook behaviour (verified from source):
  - Does NOT block; always exits 0.
  - Reads stdin JSON for scope hint (keys: file, path, scope, cwd, workingDirectory).
  - Stdout always contains three section headers:
      ## Active Invariants
      ## Session State
      ## Scope Context
  - Active Invariants:
      registry.yaml absent  → HTML comment "not found, skipping"
      registry.yaml present → entries listed as "- **{ID}** ({severity}): {rule}"
      (only entries with status: active are included)
  - Session State:
      state.md absent → HTML comment "not found, skipping"
      state.md present with ## Current Objective → that section's content appears
  - Scope Context:
      payload with scope key pointing to dir with agents.md → frontmatter fields appear
      no scope key / no agents.md found → "no agents.md found in scope path hierarchy"

pyyaml-absent path: skipped (marked as manual verification — uninstalling pyyaml
mid-test is hostile to the dev environment).
"""

import json

import pytest

from .helpers import subagent_start_event


# ---------------------------------------------------------------------------
# JSON envelope helper
# ---------------------------------------------------------------------------

def _context(stdout):
    """Decode the JSON envelope and return additionalContext.

    Falls back to raw stdout if the envelope is absent (e.g. fail-open
    path with no Python). Tests should use this rather than
    result.stdout directly so the same assertions work for both paths.
    """
    stdout = stdout.strip()
    if not stdout:
        return ""
    try:
        envelope = json.loads(stdout)
        return envelope.get("hookSpecificOutput", {}).get("additionalContext", "")
    except (json.JSONDecodeError, ValueError):
        return stdout


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_REGISTRY = """\
invariants:
  TEST-001:
    name: "Test invariant"
    severity: high
    rule: "This is a test rule."
    status: active
  INACTIVE-001:
    name: "Inactive invariant"
    severity: standard
    rule: "This rule is inactive."
    status: inactive
"""

MINIMAL_STATE = """\
## Current Objective
Verify inject-context output.

## Active Delegation
None.

## Invariants Touched
None.
"""


def _write_registry(tmp_armature, content=MINIMAL_REGISTRY):
    registry = tmp_armature / ".armature" / "invariants" / "registry.yaml"
    registry.write_text(content)
    return registry


def _write_state(tmp_armature, content=MINIMAL_STATE):
    state = tmp_armature / ".armature" / "session" / "state.md"
    state.write_text(content)
    return state


def _make_scope_with_agents(tmp_path):
    """Create a sub-directory with agents.md that has YAML frontmatter."""
    scope_dir = tmp_path / "my_scope"
    scope_dir.mkdir(parents=True, exist_ok=True)
    (scope_dir / "agents.md").write_text(
        "---\n"
        "scope: my_scope\n"
        "governs: Test scope content\n"
        "adrs: [ADR-0001]\n"
        "---\n\n# My Scope\n"
    )
    return scope_dir


# ---------------------------------------------------------------------------
# MUST: always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_zero_real_repo(run_hook):
    """Hook must always exit 0 against the real repo."""
    result = run_hook("inject-context.sh", subagent_start_event())
    assert result.returncode == 0


def test_always_exits_zero_empty_tmp_armature(run_hook, tmp_armature):
    """Hook must exit 0 even when registry and state are absent."""
    result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
    assert result.returncode == 0


def test_always_exits_zero_with_registry(run_hook, tmp_armature):
    """Hook must exit 0 when registry.yaml is present and valid."""
    _write_registry(tmp_armature)
    result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
    assert result.returncode == 0


def test_always_exits_zero_with_state(run_hook, tmp_armature):
    """Hook must exit 0 when state.md is present."""
    _write_state(tmp_armature)
    result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST: stdout always has all 3 section headers
# ---------------------------------------------------------------------------

def test_stdout_contains_active_invariants_header(run_hook):
    result = run_hook("inject-context.sh", subagent_start_event())
    assert "## Active Invariants" in _context(result.stdout)


def test_stdout_contains_session_state_header(run_hook):
    result = run_hook("inject-context.sh", subagent_start_event())
    assert "## Session State" in _context(result.stdout)


def test_stdout_contains_scope_context_header(run_hook):
    result = run_hook("inject-context.sh", subagent_start_event())
    assert "## Scope Context" in _context(result.stdout)


def test_all_three_headers_present_in_one_run(run_hook, tmp_armature):
    """All three headers must be present even in a minimal tmp repo."""
    result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
    assert "## Active Invariants" in _context(result.stdout)
    assert "## Session State" in _context(result.stdout)
    assert "## Scope Context" in _context(result.stdout)


# ---------------------------------------------------------------------------
# MUST: missing registry.yaml → "not found, skipping" comment
# ---------------------------------------------------------------------------

def test_missing_registry_emits_not_found_comment(run_hook, tmp_armature):
    """When registry.yaml is absent, output should include 'not found, skipping'."""
    registry = tmp_armature / ".armature" / "invariants" / "registry.yaml"
    assert not registry.exists()
    result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "not found, skipping" in _context(result.stdout)


def test_missing_registry_no_invariant_listings(run_hook, tmp_armature):
    """When registry.yaml is absent, no bold invariant ID lines should appear."""
    result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
    assert result.returncode == 0
    # No "- **SOMETHING**" pattern should appear
    assert "- **" not in _context(result.stdout)


# ---------------------------------------------------------------------------
# MUST: populated registry → entries listed with ID and rule text
# ---------------------------------------------------------------------------

def test_populated_registry_lists_active_entries(run_hook, tmp_armature):
    """Active invariants from registry.yaml must be listed in ## Active Invariants."""
    _write_registry(tmp_armature)
    result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "TEST-001" in _context(result.stdout)
    assert "This is a test rule." in _context(result.stdout)


def test_populated_registry_includes_severity(run_hook, tmp_armature):
    """Each active entry must include its severity in the listing."""
    _write_registry(tmp_armature)
    result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "high" in _context(result.stdout)


def test_populated_registry_excludes_inactive_entries(run_hook, tmp_armature):
    """Inactive invariants must NOT appear in the output."""
    _write_registry(tmp_armature)
    result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "INACTIVE-001" not in _context(result.stdout)


# ---------------------------------------------------------------------------
# MUST: missing state.md → "not found, skipping" comment
# ---------------------------------------------------------------------------

def test_missing_state_md_emits_not_found_comment(run_hook, tmp_armature):
    """When state.md is absent, 'not found, skipping' must appear under ## Session State."""
    state = tmp_armature / ".armature" / "session" / "state.md"
    assert not state.exists()
    result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "not found, skipping" in _context(result.stdout)


# ---------------------------------------------------------------------------
# MUST: populated state.md with ## Current Objective → section content appears
# ---------------------------------------------------------------------------

def test_populated_state_md_current_objective_appears(run_hook, tmp_armature):
    """## Current Objective section content from state.md must appear in output."""
    _write_state(tmp_armature)
    result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "Verify inject-context output." in _context(result.stdout)


def test_populated_state_md_section_header_in_output(run_hook, tmp_armature):
    """The '## Current Objective' header itself must appear in the injected output."""
    _write_state(tmp_armature)
    result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
    assert result.returncode == 0
    assert "## Current Objective" in _context(result.stdout)


def test_irrelevant_state_sections_excluded(run_hook, tmp_armature):
    """Sections not in the target list (Current Objective, Active Delegation, Invariants Touched)
    should not be emitted if state.md has only those sections."""
    state_content = "## Random Section\nRandom content.\n"
    _write_state(tmp_armature, state_content)
    result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
    assert result.returncode == 0
    # The irrelevant section content should not appear
    assert "Random content." not in _context(result.stdout)


# ---------------------------------------------------------------------------
# MUST: payload with scope key pointing to dir with agents.md → frontmatter fields appear
# ---------------------------------------------------------------------------

def test_scope_key_with_agents_md_shows_frontmatter(run_hook, tmp_armature):
    """When the payload has 'scope' pointing to a dir containing agents.md, its
    frontmatter fields (scope, governs) must appear in ## Scope Context."""
    scope_dir = _make_scope_with_agents(tmp_armature)
    payload = subagent_start_event(scope=scope_dir.as_posix())
    result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
    assert result.returncode == 0
    # Both "scope" and "governs" fields from the frontmatter must appear
    assert "my_scope" in _context(result.stdout)
    assert "Test scope content" in _context(result.stdout)


def test_scope_key_shows_source_path(run_hook, tmp_armature):
    """When agents.md is found for scope, its relative path must appear in output."""
    scope_dir = _make_scope_with_agents(tmp_armature)
    payload = subagent_start_event(scope=scope_dir.as_posix())
    result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
    assert result.returncode == 0
    # Source path annotation "_Source: <rel-path>_" must appear
    assert "agents.md" in _context(result.stdout)


# ---------------------------------------------------------------------------
# MUST: no scope key → "no agents.md found in scope path hierarchy"
# ---------------------------------------------------------------------------

def test_no_scope_key_emits_no_agents_found_comment(run_hook, tmp_armature):
    """When payload has no scope key, scope context section must note no agents.md found."""
    # tmp_armature has no root-level agents.md (only .armature/agents.md)
    # An empty object payload won't find agents.md at repo root
    result = run_hook("inject-context.sh", "{}", cwd=str(tmp_armature))
    assert result.returncode == 0
    # Hook emits HTML comment when no agents.md / AGENTS.md found. Both
    # the old form ("no agents.md found") and the updated form ("no
    # agents.md / AGENTS.md found") contain the substring "no agents.md".
    # Decode through _context() because inject-context.sh now wraps its
    # output in the SubagentStart JSON envelope (PR #22).
    assert "no agents.md" in _context(result.stdout)


# ---------------------------------------------------------------------------
# AGENTS.md (uppercase) case-handling tests
# ---------------------------------------------------------------------------

def test_uppercase_agents_md_at_scope_dir_resolves(run_hook, tmp_armature):
    """When only AGENTS.md (uppercase) exists at the scope dir, Section 3 must resolve it.

    This tests the case-handling fix: the walk-up loop now probes both
    'agents.md' and 'AGENTS.md' so that projects using uppercase AGENTS.md
    at project root have their frontmatter injected correctly.
    """
    scope_dir = tmp_armature / "uppercase_scope"
    scope_dir.mkdir(parents=True, exist_ok=True)
    # Write AGENTS.md (uppercase) — NOT agents.md
    (scope_dir / "AGENTS.md").write_text(
        "---\n"
        "scope: uppercase_scope\n"
        "governs: Uppercase agents content\n"
        "adrs: [ADR-0001]\n"
        "---\n\n# Uppercase Scope\n"
    )
    payload = subagent_start_event(scope=scope_dir.as_posix())
    result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
    assert result.returncode == 0
    # Frontmatter content from AGENTS.md must appear in ## Scope Context
    # (decoded through the JSON envelope wrapper added by PR #22).
    ctx = _context(result.stdout)
    assert "uppercase_scope" in ctx
    assert "Uppercase agents content" in ctx
    # Must not emit the "not found" comment
    assert "no agents.md / AGENTS.md found in scope path hierarchy" not in ctx


def test_uppercase_agents_md_for_disciplines_walk_up(run_hook, tmp_armature):
    """When only AGENTS.md (uppercase) exists at the scope dir, Section 4 must resolve it.

    This tests the Section 4 walk-up fix: discipline tags declared in AGENTS.md
    (uppercase) must be read and applied so that explicit-trigger disciplines fire.
    """
    # Write triggers.yaml with an explicit-trigger discipline
    _write_triggers_yaml_inline = tmp_armature / ".armature" / "disciplines"
    _write_triggers_yaml_inline.mkdir(parents=True, exist_ok=True)
    (tmp_armature / ".armature" / "disciplines" / "triggers.yaml").write_text(
        "triggers:\n"
        "  uppercase-test-disc:\n"
        "    severity: standard\n"
        "    composition-mode: advisory\n"
        "    triggers:\n"
        "      - type: explicit\n"
        "        pattern: uppercase-test\n"
    )
    # Write discipline file
    (tmp_armature / ".armature" / "disciplines" / "uppercase-test-disc.md").write_text(
        "---\nid: uppercase-test-disc\nseverity: standard\ncomposition-mode: advisory\n---\n\n"
        "# Uppercase Test Discipline body\n"
    )
    # Create scope dir with AGENTS.md (uppercase) carrying the discipline tag
    scope_dir = tmp_armature / "disc_uppercase_scope"
    scope_dir.mkdir(parents=True, exist_ok=True)
    (scope_dir / "AGENTS.md").write_text(
        "---\n"
        "scope: disc_uppercase_scope\n"
        "governs: Discipline uppercase test\n"
        "discipline-tags: ['uppercase-test']\n"
        "---\n\n# Disc Uppercase Scope\n"
    )
    payload = subagent_start_event(scope=scope_dir.as_posix())
    result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
    assert result.returncode == 0
    # The explicit-trigger discipline must have fired because AGENTS.md was
    # found. Decode through the JSON envelope.
    ctx = _context(result.stdout)
    assert "uppercase-test-disc" in ctx
    assert "no disciplines fired for this scope" not in ctx


# ---------------------------------------------------------------------------
# SHOULD: pyyaml-absent fallback path — manual verification only
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="manual verification: pyyaml absent path — uninstalling pyyaml mid-test is hostile to dev environment")
def test_pyyaml_absent_fallback():
    """When pyyaml is not installed, the hook should emit a comment about inability to parse.
    Verified manually by temporarily removing pyyaml and running the hook directly."""
    pass


# ---------------------------------------------------------------------------
# Helpers for Active Disciplines tests
# ---------------------------------------------------------------------------

def _make_scope_with_disciplines(
    tmp_armature,
    *,
    scope_path: str,
    invariants: list | None = None,
    discipline_tags: list | None = None,
) -> "pathlib.Path":
    """
    Create a directory at scope_path (relative to tmp_armature) with an agents.md
    that carries the specified frontmatter fields.

    Returns the created scope directory as a Path.
    """
    import pathlib

    scope_dir = tmp_armature / scope_path
    scope_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---\n", f"scope: {scope_path}\n", "governs: Test discipline scope\n"]
    if invariants is not None:
        lines.append(f"invariants: {invariants!r}\n")
    if discipline_tags is not None:
        lines.append(f"discipline-tags: {discipline_tags!r}\n")
    lines.append("---\n\n# Scope\n")
    (scope_dir / "agents.md").write_text("".join(lines))
    return scope_dir


def _write_triggers_yaml(tmp_armature, content: str) -> "pathlib.Path":
    """Write a custom triggers.yaml to the tmp repo's disciplines directory."""
    disciplines_dir = tmp_armature / ".armature" / "disciplines"
    disciplines_dir.mkdir(parents=True, exist_ok=True)
    triggers_file = disciplines_dir / "triggers.yaml"
    triggers_file.write_text(content)
    return triggers_file


def _write_discipline_file(tmp_armature, disc_id: str, body: str = "") -> "pathlib.Path":
    """Write a minimal discipline .md file with frontmatter and body."""
    disciplines_dir = tmp_armature / ".armature" / "disciplines"
    disciplines_dir.mkdir(parents=True, exist_ok=True)
    content = f"---\nid: {disc_id}\nseverity: standard\ncomposition-mode: advisory\n---\n\n{body or f'# {disc_id} body'}\n"
    disc_file = disciplines_dir / f"{disc_id}.md"
    disc_file.write_text(content)
    return disc_file


# Minimal triggers.yaml for most tests — only uses explicit trigger so path matching
# doesn't produce unpredictable results across platforms.
_SIMPLE_TRIGGERS = """\
triggers:
  adr-process:
    severity: high
    composition-mode: strict
    triggers:
      - type: explicit
        pattern: "adr-process"
  python-conventions:
    severity: standard
    composition-mode: advisory
    triggers:
      - type: path
        pattern: "**/*.py"
  tdd-workflow:
    severity: high
    composition-mode: strict
    triggers:
      - type: invariant
        pattern: ["TDD-001"]
  testing-standards:
    severity: high
    composition-mode: advisory
    triggers:
      - type: invariant
        pattern: ["TDD-001"]
  test-naming:
    severity: standard
    composition-mode: advisory
    triggers:
      - type: invariant
        pattern: ["TDD-001"]
  interactive-user-input:
    severity: standard
    composition-mode: advisory
    triggers:
      - type: content
        pattern: "(interactive|prompt)"
"""

# Extended triggers for composition-cap tests — uses explicit triggers to guarantee
# > 4 fire regardless of scope path, so cap behaviour is deterministic.
_CAP_TRIGGERS = """\
triggers:
  disc-alpha:
    severity: high
    composition-mode: strict
    triggers:
      - type: explicit
        pattern: "cap-test"
  disc-beta:
    severity: high
    composition-mode: strict
    triggers:
      - type: explicit
        pattern: "cap-test"
  disc-gamma:
    severity: high
    composition-mode: advisory
    triggers:
      - type: explicit
        pattern: "cap-test"
  disc-delta:
    severity: standard
    composition-mode: strict
    triggers:
      - type: explicit
        pattern: "cap-test"
  disc-epsilon:
    severity: standard
    composition-mode: advisory
    triggers:
      - type: explicit
        pattern: "cap-test"
"""


# ---------------------------------------------------------------------------
# Section 4: Active Disciplines tests
# ---------------------------------------------------------------------------

class TestActiveDisciplines:
    """Tests for the ## Active Disciplines section (Section 4) of inject-context.sh."""

    def test_active_disciplines_header_always_present(self, run_hook, tmp_armature):
        """## Active Disciplines header must appear even when triggers.yaml is absent."""
        result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
        assert result.returncode == 0
        assert "## Active Disciplines" in _context(result.stdout)

    def test_no_triggers_yaml_emits_comment(self, run_hook, tmp_armature):
        """When triggers.yaml is absent, output includes 'not found, skipping' comment."""
        triggers = tmp_armature / ".armature" / "disciplines" / "triggers.yaml"
        assert not triggers.exists()
        result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
        assert result.returncode == 0
        assert "triggers.yaml not found, skipping discipline injection" in _context(result.stdout)

    def test_path_trigger_fires_for_matching_scope(self, run_hook, tmp_armature):
        """Scope path containing .py files activates python-conventions (path trigger)."""
        _write_triggers_yaml(tmp_armature, _SIMPLE_TRIGGERS)
        _write_discipline_file(
            tmp_armature,
            "python-conventions",
            "Follow PEP-8 and type-hint all public APIs.",
        )
        # Create a scope directory whose posix path ends in .py (simulates a file scope)
        scope_dir = tmp_armature / "src" / "module.py"
        scope_dir.mkdir(parents=True, exist_ok=True)
        (scope_dir / "agents.md").write_text(
            "---\nscope: src/module.py\ngoverns: Python module\n---\n\n# Module\n"
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        # python-conventions should have fired and its body content should appear
        assert "python-conventions" in _context(result.stdout)
        assert "PEP-8" in _context(result.stdout)

    def test_invariant_trigger_fires(self, run_hook, tmp_armature):
        """Scope with TDD-001 in invariants list fires tdd-workflow, testing-standards, test-naming."""
        _write_triggers_yaml(tmp_armature, _SIMPLE_TRIGGERS)
        for disc_id in ("tdd-workflow", "testing-standards", "test-naming"):
            _write_discipline_file(tmp_armature, disc_id, f"{disc_id} content here.")
        scope_dir = _make_scope_with_disciplines(
            tmp_armature,
            scope_path="src/impl",
            invariants=["TDD-001"],
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        # All three invariant-triggered disciplines should fire and appear
        assert "tdd-workflow" in _context(result.stdout)
        assert "testing-standards" in _context(result.stdout)

    def test_explicit_trigger_fires(self, run_hook, tmp_armature):
        """Scope with discipline-tags: [adr-process] activates adr-process discipline."""
        _write_triggers_yaml(tmp_armature, _SIMPLE_TRIGGERS)
        _write_discipline_file(
            tmp_armature,
            "adr-process",
            "Record every architectural decision in docs/adr/.",
        )
        scope_dir = _make_scope_with_disciplines(
            tmp_armature,
            scope_path="docs",
            discipline_tags=["adr-process"],
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        assert "adr-process" in _context(result.stdout)
        assert "docs/adr/" in _context(result.stdout)

    def test_composition_cap_enforced(self, run_hook, tmp_armature):
        """When more than 4 disciplines fire, output contains exactly 4 subsections."""
        _write_triggers_yaml(tmp_armature, _CAP_TRIGGERS)
        for disc_id in ("disc-alpha", "disc-beta", "disc-gamma", "disc-delta", "disc-epsilon"):
            _write_discipline_file(tmp_armature, disc_id, f"{disc_id} body content.")
        scope_dir = _make_scope_with_disciplines(
            tmp_armature,
            scope_path="capped_scope",
            discipline_tags=["cap-test"],
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        # Count ### subsection headers for disciplines
        ctx = _context(result.stdout)
        subsection_count = ctx.count("\n### disc-")
        assert subsection_count == 4, (
            f"Expected exactly 4 discipline subsections, got {subsection_count}. "
            f"Output:\n{ctx}"
        )

    def test_composition_cap_priority(self, run_hook, tmp_armature):
        """When cap kicks in, highest severity (then strict > advisory) disciplines win."""
        _write_triggers_yaml(tmp_armature, _CAP_TRIGGERS)
        for disc_id in ("disc-alpha", "disc-beta", "disc-gamma", "disc-delta", "disc-epsilon"):
            _write_discipline_file(tmp_armature, disc_id, f"{disc_id} body content.")
        scope_dir = _make_scope_with_disciplines(
            tmp_armature,
            scope_path="priority_scope",
            discipline_tags=["cap-test"],
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        # disc-alpha (high/strict), disc-beta (high/strict), disc-gamma (high/advisory),
        # disc-delta (standard/strict) should be selected; disc-epsilon (standard/advisory) truncated
        assert "### disc-alpha" in _context(result.stdout)
        assert "### disc-beta" in _context(result.stdout)
        assert "### disc-gamma" in _context(result.stdout)
        assert "### disc-delta" in _context(result.stdout)
        assert "### disc-epsilon" not in _context(result.stdout)

    def test_attribution_block_present(self, run_hook, tmp_armature):
        """DISCIPLINE-ATTRIBUTION comment block must appear when any discipline fires."""
        _write_triggers_yaml(tmp_armature, _SIMPLE_TRIGGERS)
        _write_discipline_file(tmp_armature, "adr-process", "ADR process content.")
        scope_dir = _make_scope_with_disciplines(
            tmp_armature,
            scope_path="attributed_scope",
            discipline_tags=["adr-process"],
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        assert "<!-- DISCIPLINE-ATTRIBUTION" in _context(result.stdout)
        assert "fired:" in _context(result.stdout)
        assert "selected:" in _context(result.stdout)
        assert "truncated:" in _context(result.stdout)
        assert "trigger_modes:" in _context(result.stdout)

    def test_attribution_lists_truncated_disciplines(self, run_hook, tmp_armature):
        """When composition cap fires, truncated list in attribution is non-empty."""
        _write_triggers_yaml(tmp_armature, _CAP_TRIGGERS)
        for disc_id in ("disc-alpha", "disc-beta", "disc-gamma", "disc-delta", "disc-epsilon"):
            _write_discipline_file(tmp_armature, disc_id, f"{disc_id} body content.")
        scope_dir = _make_scope_with_disciplines(
            tmp_armature,
            scope_path="truncated_scope",
            discipline_tags=["cap-test"],
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        # Extract the truncated line
        ctx = _context(result.stdout)
        truncated_line = [
            line for line in ctx.splitlines()
            if line.strip().startswith("truncated:")
        ]
        assert truncated_line, "No 'truncated:' line found in output"
        truncated_value = truncated_line[0].split("truncated:", 1)[1].strip()
        assert truncated_value != "none", (
            f"Expected truncated to be non-empty, got: {truncated_value!r}"
        )

    def test_content_trigger_deferred(self, run_hook, tmp_armature):
        """A discipline with only a content trigger emits the deferral comment."""
        content_only_triggers = """\
triggers:
  interactive-user-input:
    severity: standard
    composition-mode: advisory
    triggers:
      - type: content
        pattern: "(interactive|prompt)"
"""
        _write_triggers_yaml(tmp_armature, content_only_triggers)
        _write_discipline_file(tmp_armature, "interactive-user-input", "Interactive input content.")
        scope_dir = _make_scope_with_disciplines(
            tmp_armature,
            scope_path="content_scope",
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        assert "content trigger requires orchestrator pre-evaluation" in _context(result.stdout)

    def test_missing_discipline_file_handled_gracefully(self, run_hook, tmp_armature):
        """Fired discipline whose .md file is missing emits comment but doesn't crash."""
        _write_triggers_yaml(tmp_armature, _SIMPLE_TRIGGERS)
        # Intentionally do NOT write adr-process.md
        scope_dir = _make_scope_with_disciplines(
            tmp_armature,
            scope_path="missing_file_scope",
            discipline_tags=["adr-process"],
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        assert "fired but file not found, skipping" in _context(result.stdout)

    def test_no_fired_disciplines_emits_comment(self, run_hook, tmp_armature):
        """Scope with no matching triggers emits 'no disciplines fired' comment."""
        # Use triggers that only fire on explicit tags, but give scope no discipline-tags
        explicit_only_triggers = """\
triggers:
  adr-process:
    severity: high
    composition-mode: strict
    triggers:
      - type: explicit
        pattern: "adr-process"
"""
        _write_triggers_yaml(tmp_armature, explicit_only_triggers)
        _write_discipline_file(tmp_armature, "adr-process", "ADR process content.")
        # Scope with NO discipline-tags — trigger won't fire
        scope_dir = _make_scope_with_disciplines(
            tmp_armature,
            scope_path="no_match_scope",
            discipline_tags=[],
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        assert "no disciplines fired for this scope" in _context(result.stdout)

    def test_hook_always_exits_zero(self, run_hook, tmp_armature):
        """Even with a malformed triggers.yaml, hook must exit 0."""
        # Write a syntactically invalid YAML file
        disciplines_dir = tmp_armature / ".armature" / "disciplines"
        disciplines_dir.mkdir(parents=True, exist_ok=True)
        (disciplines_dir / "triggers.yaml").write_text(
            "triggers:\n  bad: {unclosed\n"
        )
        result = run_hook("inject-context.sh", subagent_start_event(), cwd=str(tmp_armature))
        assert result.returncode == 0

    # -------------------------------------------------------------------------
    # Cycle-2 fixes: MEDIUM-1 always-on discipline semantics
    # -------------------------------------------------------------------------

    def test_always_on_discipline_no_triggers_list(self, run_hook, tmp_armature):
        """Discipline entry that omits the triggers: key entirely fires for every delegation.

        Per ARMATURE.md §8.4: an entry with no triggers list is always-on.
        """
        _write_triggers_yaml(
            tmp_armature,
            "triggers:\n"
            "  experimental:\n"
            "    severity: standard\n"
            "    composition-mode: advisory\n"
            # No 'triggers:' key at all
        )
        _write_discipline_file(tmp_armature, "experimental", "Experimental discipline body.")
        # Use a scope with no matching path/invariant/explicit — only always-on should fire
        scope_dir = _make_scope_with_disciplines(
            tmp_armature,
            scope_path="no_trigger_scope",
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        ctx = _context(result.stdout)
        assert "experimental" in ctx, (
            f"Always-on discipline (no triggers key) did not fire.\nOutput:\n{ctx}"
        )
        assert "no disciplines fired for this scope" not in ctx

    def test_always_on_discipline_empty_triggers_list(self, run_hook, tmp_armature):
        """Discipline entry with triggers: [] fires for every delegation.

        Per ARMATURE.md §8.4: an empty triggers list is always-on.
        """
        _write_triggers_yaml(
            tmp_armature,
            "triggers:\n"
            "  experimental:\n"
            "    severity: standard\n"
            "    composition-mode: advisory\n"
            "    triggers: []\n"
        )
        _write_discipline_file(tmp_armature, "experimental", "Experimental discipline body.")
        scope_dir = _make_scope_with_disciplines(
            tmp_armature,
            scope_path="empty_triggers_scope",
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        ctx = _context(result.stdout)
        assert "experimental" in ctx, (
            f"Always-on discipline (triggers: []) did not fire.\nOutput:\n{ctx}"
        )
        assert "no disciplines fired for this scope" not in ctx

    def test_always_on_attribution_records_always_on(self, run_hook, tmp_armature):
        """Fired always-on discipline shows trigger_mode 'always-on' in attribution block."""
        _write_triggers_yaml(
            tmp_armature,
            "triggers:\n"
            "  experimental:\n"
            "    severity: standard\n"
            "    composition-mode: advisory\n"
            "    triggers: []\n"
        )
        _write_discipline_file(tmp_armature, "experimental", "Experimental discipline body.")
        scope_dir = _make_scope_with_disciplines(
            tmp_armature,
            scope_path="attribution_scope",
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        ctx = _context(result.stdout)
        assert "always-on" in ctx, (
            f"Expected 'always-on' in trigger_modes attribution block.\nOutput:\n{ctx}"
        )

    # -------------------------------------------------------------------------
    # Cycle-2 fixes: MEDIUM-2 body extraction robustness
    # -------------------------------------------------------------------------

    def test_body_extraction_handles_dashes_in_yaml_value(self, run_hook, tmp_armature):
        """Discipline file with --- inside a frontmatter YAML value yields clean body.

        Per MEDIUM-2 fix: closing frontmatter fence must be found at line-start,
        not by substring search which matches --- inside scalar values.
        """
        _write_triggers_yaml(
            tmp_armature,
            "triggers:\n"
            "  dash-discipline:\n"
            "    severity: standard\n"
            "    composition-mode: advisory\n"
            "    triggers: []\n"
        )
        # Write discipline file with --- embedded inside a YAML scalar value
        disciplines_dir = tmp_armature / ".armature" / "disciplines"
        disciplines_dir.mkdir(parents=True, exist_ok=True)
        disc_content = (
            "---\n"
            "id: dash-discipline\n"
            "description: \"uses --- as separator\"\n"
            "severity: standard\n"
            "composition-mode: advisory\n"
            "---\n"
            "\n"
            "# Clean Body\n"
            "\n"
            "Only this should appear.\n"
        )
        (disciplines_dir / "dash-discipline.md").write_text(disc_content)
        scope_dir = _make_scope_with_disciplines(
            tmp_armature,
            scope_path="dash_scope",
        )
        payload = subagent_start_event(scope=scope_dir.as_posix())
        result = run_hook("inject-context.sh", payload, cwd=str(tmp_armature))
        assert result.returncode == 0
        ctx = _context(result.stdout)
        # The body should contain the clean content, not leftover frontmatter bytes
        assert "Only this should appear." in ctx, (
            f"Body content missing from output.\nOutput:\n{ctx}"
        )
        # Crucially, the description: value's --- must NOT appear as a stray header
        # The output should NOT contain raw frontmatter lines like 'id: dash-discipline'
        # after the discipline header
        disc_section_start = ctx.find("### dash-discipline")
        assert disc_section_start >= 0, "Discipline section header not found"
        disc_section = ctx[disc_section_start:]
        # Frontmatter lines (id:, description:, severity:) must not appear in body
        assert "id: dash-discipline" not in disc_section, (
            f"Frontmatter leaked into body.\nDiscipline section:\n{disc_section}"
        )


# ---------------------------------------------------------------------------
# Cycle-16: JSON envelope — new tests for SubagentStart wrapper
# ---------------------------------------------------------------------------

def test_emit_is_valid_json_envelope(run_hook, tmp_armature):
    """Hook output must be a valid JSON envelope with the correct hookEventName."""
    _write_registry(tmp_armature)
    result = run_hook(
        "inject-context.sh",
        subagent_start_event(scope=str(tmp_armature / ".armature")),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    assert envelope["hookSpecificOutput"]["hookEventName"] == "SubagentStart"
    additional = envelope["hookSpecificOutput"]["additionalContext"]
    assert isinstance(additional, str) and len(additional) > 0


def test_json_envelope_contains_active_invariants_header(run_hook, tmp_armature):
    """The additionalContext must include the ## Active Invariants section header."""
    _write_registry(tmp_armature)
    result = run_hook(
        "inject-context.sh",
        subagent_start_event(scope=str(tmp_armature / ".armature")),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    additional = envelope["hookSpecificOutput"]["additionalContext"]
    assert "## Active Invariants" in additional


def test_json_envelope_contains_session_state_header(run_hook, tmp_armature):
    """The additionalContext must include the ## Session State section header."""
    _write_registry(tmp_armature)
    result = run_hook(
        "inject-context.sh",
        subagent_start_event(scope=str(tmp_armature / ".armature")),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    additional = envelope["hookSpecificOutput"]["additionalContext"]
    assert "## Session State" in additional


def test_json_envelope_contains_scope_context_header(run_hook, tmp_armature):
    """The additionalContext must include the ## Scope Context section header."""
    _write_registry(tmp_armature)
    result = run_hook(
        "inject-context.sh",
        subagent_start_event(scope=str(tmp_armature / ".armature")),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    additional = envelope["hookSpecificOutput"]["additionalContext"]
    assert "## Scope Context" in additional
