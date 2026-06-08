"""
Tests for phase-gate.sh (PHASE-001).

Hook behaviour (verified from source):
  - Reads tool_input.file_path from stdin JSON.
  - Rejects control characters in file_path → exit 2 + "BLOCK [PHASE-001]".
  - Rejects NUL bytes in raw JSON stdin → exit 2 + "BLOCK [PHASE-001]".
  - Empty / missing file_path → exit 0 (fail-open).
  - JSON null for file_path → exit 0 (treated as absent; fail-open).
  - Invalid JSON → exit 0 (fail-open).
  - Reads SDLC phase from .armature/session/phase (single line, stripped).
  - Missing / empty / unknown phase → WARN on stderr + default to Implementation.
  - Phase = "Hotfix" (case-sensitive) → ADVISORY on stderr + exit 0 (bypass).
  - Classifies file into one of 8 classes (first-match wins):
      tier0-doc, governance (adapter files), spec-doc, hook-script, test-file,
      governance (other .armature/.claude), implementation-code, config-file, other.
  - CLAUDE.md, CODEX.md, agents.md, AGENTS.md → governance (not spec-doc).
  - Checks (phase, class) against PERMITTED table:
      Discovery:      tier0-doc, spec-doc, governance, other
      Design:         spec-doc, governance, config-file, other
      Implementation: all classes
      Review:         governance, other
      Release:        governance, config-file, other
      Hotfix:         bypass (handled before classification)
  - Block → exit 2, "BLOCK [PHASE-001]", phase/class/permitted in message.
  - Allow → exit 0.

All tests use tmp_armature so the real repo is never mutated.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from .helpers import edit_event


# ---------------------------------------------------------------------------
# Helper: write the phase file
# ---------------------------------------------------------------------------

def _write_phase(tmp_armature: Path, phase: str) -> None:
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.parent.mkdir(parents=True, exist_ok=True)
    phase_file.write_text(phase)


# ===========================================================================
# MUST tests (16)
# ===========================================================================

# ---------------------------------------------------------------------------
# MUST 1: Discovery allows tier0-doc (DOMAIN.md)
# ---------------------------------------------------------------------------

def test_discovery_allows_tier0_doc(run_hook, tmp_armature):
    """phase=Discovery, file=DOMAIN.md → exit 0 (tier0-doc is permitted)."""
    _write_phase(tmp_armature, "Discovery")
    result = run_hook(
        "phase-gate.sh",
        edit_event("DOMAIN.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 2: Discovery blocks implementation-code
# ---------------------------------------------------------------------------

def test_discovery_blocks_implementation_code(run_hook, tmp_armature):
    """phase=Discovery, file=src/foo.py → exit 2 + BLOCK + PHASE-001."""
    _write_phase(tmp_armature, "Discovery")
    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "PHASE-001" in result.stderr


# ---------------------------------------------------------------------------
# MUST 3: Discovery allows spec-doc
# ---------------------------------------------------------------------------

def test_discovery_allows_spec_doc(run_hook, tmp_armature):
    """phase=Discovery, file=docs/adr/0001.md → exit 0 (spec-doc is permitted)."""
    _write_phase(tmp_armature, "Discovery")
    result = run_hook(
        "phase-gate.sh",
        edit_event("docs/adr/0001.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 4: Design allows spec-doc
# ---------------------------------------------------------------------------

def test_design_allows_spec_doc(run_hook, tmp_armature):
    """phase=Design, file=docs/adr/0001.md → exit 0 (spec-doc is permitted)."""
    _write_phase(tmp_armature, "Design")
    result = run_hook(
        "phase-gate.sh",
        edit_event("docs/adr/0001.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 5: Design blocks implementation-code
# ---------------------------------------------------------------------------

def test_design_blocks_implementation_code(run_hook, tmp_armature):
    """phase=Design, file=src/foo.py → exit 2."""
    _write_phase(tmp_armature, "Design")
    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "PHASE-001" in result.stderr


# ---------------------------------------------------------------------------
# MUST 6: Implementation allows implementation-code
# ---------------------------------------------------------------------------

def test_implementation_allows_implementation_code(run_hook, tmp_armature):
    """phase=Implementation, file=src/foo.py → exit 0."""
    _write_phase(tmp_armature, "Implementation")
    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 7: Implementation allows hook-script
# ---------------------------------------------------------------------------

def test_implementation_allows_hook_script(run_hook, tmp_armature):
    """phase=Implementation, file=.armature/hooks/foo.sh → exit 0."""
    _write_phase(tmp_armature, "Implementation")
    result = run_hook(
        "phase-gate.sh",
        edit_event(".armature/hooks/foo.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 8: Implementation allows test-file
# ---------------------------------------------------------------------------

def test_implementation_allows_test_file(run_hook, tmp_armature):
    """phase=Implementation, file=tests/test_foo.py → exit 0."""
    _write_phase(tmp_armature, "Implementation")
    result = run_hook(
        "phase-gate.sh",
        edit_event("tests/test_foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 9: Review blocks implementation-code
# ---------------------------------------------------------------------------

def test_review_blocks_implementation_code(run_hook, tmp_armature):
    """phase=Review, file=src/foo.py → exit 2."""
    _write_phase(tmp_armature, "Review")
    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "PHASE-001" in result.stderr


# ---------------------------------------------------------------------------
# MUST 10: Review allows governance
# ---------------------------------------------------------------------------

def test_review_allows_governance(run_hook, tmp_armature):
    """phase=Review, file=.armature/agents.md → exit 0 (governance is permitted)."""
    _write_phase(tmp_armature, "Review")
    result = run_hook(
        "phase-gate.sh",
        edit_event(".armature/agents.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 11: Release blocks implementation-code
# ---------------------------------------------------------------------------

def test_release_blocks_implementation_code(run_hook, tmp_armature):
    """phase=Release, file=src/foo.py → exit 2."""
    _write_phase(tmp_armature, "Release")
    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "PHASE-001" in result.stderr


# ---------------------------------------------------------------------------
# MUST 12: Release allows governance (config-file — uses .armature/config.yaml)
# ---------------------------------------------------------------------------

def test_release_allows_governance(run_hook, tmp_armature):
    """phase=Release, file=.armature/config.yaml → exit 0 (governance is permitted)."""
    _write_phase(tmp_armature, "Release")
    result = run_hook(
        "phase-gate.sh",
        edit_event(".armature/config.yaml"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 13: Hotfix bypasses all file classes
# ---------------------------------------------------------------------------

def test_hotfix_bypasses_all(run_hook, tmp_armature):
    """phase=Hotfix, file=src/foo.py → exit 0 + 'ADVISORY' on stderr."""
    _write_phase(tmp_armature, "Hotfix")
    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" in result.stderr


# ---------------------------------------------------------------------------
# MUST 14: Phase file missing → WARN + default Implementation (fail-open)
# ---------------------------------------------------------------------------

def test_phase_file_missing_warns_and_defaults_to_implementation(run_hook, tmp_armature):
    """No .armature/session/phase file, file=src/foo.py → exit 0 + WARN on stderr.

    Implementation is the default phase when the phase file is absent; it
    permits implementation-code, so the edit is allowed.
    """
    # Ensure phase file does NOT exist (tmp_armature creates the session dir but
    # never creates the phase file, so this should already hold)
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    assert not phase_file.exists(), "phase file should not exist for this test"

    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "WARN" in result.stderr


# ---------------------------------------------------------------------------
# MUST 15: Invalid JSON → exit 0 (fail-open)
# ---------------------------------------------------------------------------

def test_fail_open_invalid_json(run_hook, tmp_armature):
    """Invalid JSON stdin → exit 0 (fail-open, cannot parse file_path)."""
    result = run_hook(
        "phase-gate.sh",
        "{{not json at all",
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 16: No file_path → exit 0 (fail-open)
# ---------------------------------------------------------------------------

def test_fail_open_no_file_path(run_hook, tmp_armature):
    """JSON missing file_path → exit 0 (fail-open)."""
    payload = json.dumps({"tool_input": {"command": "echo hi"}})
    result = run_hook(
        "phase-gate.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ===========================================================================
# SHOULD tests (10)
# ===========================================================================

# ---------------------------------------------------------------------------
# SHOULD 17: BLOCK message names the phase
# ---------------------------------------------------------------------------

def test_block_message_names_phase(run_hook, tmp_armature):
    """BLOCK stderr contains the active phase name."""
    _write_phase(tmp_armature, "Review")
    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "Review" in result.stderr


# ---------------------------------------------------------------------------
# SHOULD 18: BLOCK message names the file class
# ---------------------------------------------------------------------------

def test_block_message_names_file_class(run_hook, tmp_armature):
    """BLOCK stderr contains the classified file class."""
    _write_phase(tmp_armature, "Review")
    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "implementation-code" in result.stderr


# ---------------------------------------------------------------------------
# SHOULD 19: BLOCK message lists permitted phases for the blocked class
# ---------------------------------------------------------------------------

def test_block_message_lists_permitted_phases(run_hook, tmp_armature):
    """BLOCK stderr lists the phases that permit the blocked file class."""
    _write_phase(tmp_armature, "Review")
    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    # implementation-code is only permitted in Implementation
    assert "Implementation" in result.stderr


# ---------------------------------------------------------------------------
# SHOULD 20: Phase file with trailing newline parses correctly
# ---------------------------------------------------------------------------

def test_phase_file_with_trailing_newline_parses_correctly(run_hook, tmp_armature):
    """Phase file containing 'Discovery\\n' is stripped and parsed as Discovery."""
    _write_phase(tmp_armature, "Discovery\n")
    result = run_hook(
        "phase-gate.sh",
        edit_event("DOMAIN.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# SHOULD 21: Discovery allows editing DOMAIN.md (tier0-doc special case)
# ---------------------------------------------------------------------------

def test_discovery_allows_editing_domain_md(run_hook, tmp_armature):
    """phase=Discovery, file=DOMAIN.md → exit 0 (tier0-doc, permitted in Discovery)."""
    _write_phase(tmp_armature, "Discovery")
    result = run_hook(
        "phase-gate.sh",
        edit_event("DOMAIN.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# SHOULD 22: Discovery allows editing the phase file itself (governance class)
# ---------------------------------------------------------------------------

def test_discovery_allows_editing_phase_file(run_hook, tmp_armature):
    """phase=Discovery, file=.armature/session/phase → exit 0 (governance, permitted)."""
    _write_phase(tmp_armature, "Discovery")
    result = run_hook(
        "phase-gate.sh",
        edit_event(".armature/session/phase"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# SHOULD 23: Design allows config-file
# ---------------------------------------------------------------------------

def test_design_allows_config_file(run_hook, tmp_armature):
    """phase=Design, file=.armature/config.yaml → exit 0 (config-file, permitted in Design)."""
    _write_phase(tmp_armature, "Design")
    result = run_hook(
        "phase-gate.sh",
        edit_event(".armature/config.yaml"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# SHOULD 24: Review blocks test-file
# ---------------------------------------------------------------------------

def test_review_blocks_test_file(run_hook, tmp_armature):
    """phase=Review, file=tests/test_foo.py → exit 2 (test-file not permitted in Review)."""
    _write_phase(tmp_armature, "Review")
    result = run_hook(
        "phase-gate.sh",
        edit_event("tests/test_foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "PHASE-001" in result.stderr


# ---------------------------------------------------------------------------
# SHOULD 25: Unknown phase string → WARN + default Implementation
# ---------------------------------------------------------------------------

def test_unknown_phase_string_warns_and_defaults(run_hook, tmp_armature):
    """Phase file containing 'FooBar' → WARN on stderr + default Implementation (fail-open)."""
    _write_phase(tmp_armature, "FooBar")
    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0  # Implementation permits implementation-code
    assert "WARN" in result.stderr


# ---------------------------------------------------------------------------
# SHOULD 26: 'other' class is allowed in every non-Hotfix phase
# ---------------------------------------------------------------------------

def test_other_class_allowed_in_all_non_hotfix_phases(run_hook, tmp_armature):
    """phase=Discovery, file=Makefile (no extension → 'other') → exit 0."""
    _write_phase(tmp_armature, "Discovery")
    result = run_hook(
        "phase-gate.sh",
        edit_event("Makefile"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ===========================================================================
# Carry-forward from CP1+CP2: control-character and null file_path
# ===========================================================================

# ---------------------------------------------------------------------------
# Test 27 (CP1 carry-forward): control characters in file_path → exit 2
# ---------------------------------------------------------------------------

def test_block_control_chars_in_file_path(run_hook, tmp_armature):
    """file_path with embedded newline → exit 2 + BLOCK + 'control characters'.

    A JSON string containing a \\n escape decodes to a real newline character
    (ord < 32).  The hook must reject this before phase or classification logic
    fires, so a crafted path like '.armature/session\\nsrc/foo.py' cannot
    bypass the gate by prefix-matching '.armature/'.
    """
    payload = '{"tool_input":{"file_path":".armature/session\\nsrc/foo.py"}}'
    result = run_hook(
        "phase-gate.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "PHASE-001" in result.stderr
    assert "control characters" in result.stderr


# ---------------------------------------------------------------------------
# Test 28 (CP1 carry-forward): JSON null for file_path → exit 0 (fail-open)
# ---------------------------------------------------------------------------

def test_fail_open_null_file_path(run_hook, tmp_armature):
    """JSON null for file_path → exit 0 (treated as absent; fail-open).

    When file_path is JSON null the Python extractor must treat it identically
    to a missing key, not print the string 'None' and create a spurious path.
    """
    payload = '{"tool_input":{"file_path":null}}'
    result = run_hook(
        "phase-gate.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ===========================================================================
# Cycle-2 (m3-cp3) fixes: NUL-byte phase bypass + classifier gaps
# ===========================================================================

# ---------------------------------------------------------------------------
# Test 29: HIGH — NUL byte in phase file must not alias to "Hotfix"
# ---------------------------------------------------------------------------

def test_block_nul_byte_phase_file_phase_gate(run_hook, tmp_armature):
    """Phase file containing 'Hot\\x00fix' must NOT trigger Hotfix bypass.

    bash command-substitution strips NUL bytes, so 'Hot\\x00fix' would
    be captured as 'Hotfix' and bypass the gate.  The cycle-2 Python-based
    phase reader rejects files containing control bytes (NUL = 0x00 < 32 and
    not tab/LF/CR), so the phase is treated as unknown → default Implementation
    → source file edit is still allowed (fail-open), but NO bypass occurs.
    """
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.parent.mkdir(parents=True, exist_ok=True)
    phase_file.write_bytes(b"Hot\x00fix")

    # In Implementation phase, src/foo.py is allowed (exit 0), but crucially
    # we must NOT see an ADVISORY Hotfix bypass in stderr.
    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    # No bypass — the gate runs normally (Implementation allows implementation-code)
    assert result.returncode == 0
    assert "ADVISORY" not in result.stderr

    # Verify that a blocked file is also actually blocked, not bypassed.
    # In Implementation (the default after NUL rejection), hook-script IS allowed,
    # so use Design-equivalent by resetting phase to Review which blocks impl-code.
    # Simpler: use a file class not permitted in any default → verify exit 2.
    # Write NUL phase and edit a tier0-doc with a phase that should block it:
    # Actually, the cleanest check is: write NUL phase, edit a config-file in
    # what would be "Hotfix" (bypass) — verify it is blocked as Implementation.
    # We already confirmed ADVISORY absent. The test is sufficient.


# ---------------------------------------------------------------------------
# Test 30: MEDIUM-1 — uppercase extension must be classified as implementation-code
# ---------------------------------------------------------------------------

def test_block_uppercase_extension_in_design(run_hook, tmp_armature):
    """phase=Design, file=src/foo.PY → exit 2 (classified as implementation-code).

    Before the cycle-2 fix, 'src/foo.PY' had extension '.PY' which did not
    match '.py' in the endswith() check, so it fell through to 'other' and was
    permitted in Design.  The fix lowercases the path for extension checks.
    """
    _write_phase(tmp_armature, "Design")
    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.PY"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "PHASE-001" in result.stderr


# ---------------------------------------------------------------------------
# Test 31: MEDIUM-2 — .sh.bak under .armature/hooks/ must be hook-script class
# ---------------------------------------------------------------------------

def test_block_sh_bak_in_hooks_dir_in_discovery(run_hook, tmp_armature):
    """phase=Discovery, file=.armature/hooks/foo.sh.bak → exit 2 (hook-script).

    Before the cycle-2 fix, the hook-script classifier required the path to
    end with '.sh'.  A file ending in '.sh.bak' fell through to the governance
    class, which is permitted in Discovery, creating a staging vector.
    The fix classifies ANY file under .armature/hooks/ as hook-script.
    """
    _write_phase(tmp_armature, "Discovery")
    result = run_hook(
        "phase-gate.sh",
        edit_event(".armature/hooks/foo.sh.bak"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "PHASE-001" in result.stderr


# ---------------------------------------------------------------------------
# Test 32: MEDIUM-3 — __tests__/ at repo root must classify as test-file
# ---------------------------------------------------------------------------

def test_classify_double_underscore_tests_path_at_root(run_hook, tmp_armature):
    """phase=Review, file=__tests__/foo.py → exit 2 (classified as test-file).

    Before the cycle-2 fix, the test-file check looked for '/__tests__/' (with
    a leading slash), which did not match '__tests__/foo.py' at repo root.
    The fix uses '__tests__/' (no leading slash) which matches both root and
    nested paths.  test-file is not permitted in Review → exit 2.
    """
    _write_phase(tmp_armature, "Review")
    result = run_hook(
        "phase-gate.sh",
        edit_event("__tests__/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "PHASE-001" in result.stderr


# ---------------------------------------------------------------------------
# Test 33: MEDIUM-1 + MEDIUM-2 — uppercase .armature/HOOKS/ prefix via lowercase
# ---------------------------------------------------------------------------

def test_block_uppercase_hooks_dir_path(run_hook, tmp_armature):
    """phase=Discovery, file=.armature/HOOKS/foo.sh → exit 2 (hook-script via lowercase).

    The classifier lowercases the path before the .armature/hooks/ prefix check,
    so '.armature/HOOKS/foo.sh' is treated as hook-script and blocked in Discovery.
    """
    _write_phase(tmp_armature, "Discovery")
    result = run_hook(
        "phase-gate.sh",
        edit_event(".armature/HOOKS/foo.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "PHASE-001" in result.stderr


# ===========================================================================
# Cycle-3 (m3-cp3) fixes: Unicode whitespace bypass + composition gap
# ===========================================================================

# ---------------------------------------------------------------------------
# Test 34: MEDIUM-1 (cycle-3) — Unicode NBSP wrapping 'Hotfix' must not bypass
# ---------------------------------------------------------------------------

def test_block_unicode_nbsp_phase_file_phase_gate(run_hook, tmp_armature):
    """Phase file containing NBSP+Hotfix+NBSP must NOT trigger Hotfix bypass.

    Python's str.strip() (without arguments) strips Unicode whitespace including
    U+00A0 NO-BREAK SPACE (\\xc2\\xa0 in UTF-8).  The cycle-2 reader used .strip()
    which allowed '\\xc2\\xa0Hotfix\\xc2\\xa0' to decode to 'Hotfix' and bypass.
    The cycle-3 fix uses .strip(' \\t\\n\\r') which only strips ASCII whitespace,
    so the NBSP-wrapped value is not in VALID → treated as unknown phase →
    defaults to Implementation.

    The gate must run normally (no ADVISORY) and must NOT emit a bypass.
    With phase defaulting to Implementation, src/foo.py is allowed (exit 0),
    but ADVISORY must be absent from stderr.
    """
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.parent.mkdir(parents=True, exist_ok=True)
    # NBSP (U+00A0) = \\xc2\\xa0 in UTF-8; wrap Hotfix on both sides
    phase_file.write_bytes(b"\xc2\xa0Hotfix\xc2\xa0")

    result = run_hook(
        "phase-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    # No bypass: gate runs normally, no ADVISORY
    assert "ADVISORY" not in result.stderr
    # Implementation (default) permits implementation-code → exit 0; no BLOCK
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 35: MEDIUM-2 (cycle-3) — .armature/hooks/__tests__/foo.sh → hook-script class
# ---------------------------------------------------------------------------

def test_classify_armature_hooks_double_underscore_tests_as_hook_script(run_hook, tmp_armature):
    """phase=Discovery, file=.armature/hooks/__tests__/foo.sh → exit 2 (hook-script).

    Before the cycle-3 fix, the __tests__/ test-file check ran BEFORE the
    .armature/hooks/ hook-script check.  So .armature/hooks/__tests__/foo.sh
    was classified as test-file (not hook-script).  In Discovery, test-file is
    NOT permitted, so it still exited 2 in practice — but for the wrong reason.

    After the cycle-3 fix, hook-script check runs first, so the file is
    correctly classified as hook-script.  hook-script is not permitted in
    Discovery → exit 2 + BLOCK + PHASE-001.
    """
    _write_phase(tmp_armature, "Discovery")
    result = run_hook(
        "phase-gate.sh",
        edit_event(".armature/hooks/__tests__/foo.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "PHASE-001" in result.stderr
    # The block message must name the hook-script class, not test-file
    assert "hook-script" in result.stderr


# ---------------------------------------------------------------------------
# Test 36: MEDIUM-2 (cycle-3) — any file under .armature/hooks/ is hook-script
# ---------------------------------------------------------------------------

def test_classify_armature_hooks_random_file_as_hook_script(run_hook, tmp_armature):
    """phase=Discovery, file=.armature/hooks/some_data.txt → exit 2 (hook-script).

    Confirms that the .armature/hooks/ prefix rule catches ALL files in that
    directory regardless of extension or name, and that hook-script is correctly
    blocked in Discovery.
    """
    _write_phase(tmp_armature, "Discovery")
    result = run_hook(
        "phase-gate.sh",
        edit_event(".armature/hooks/some_data.txt"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "PHASE-001" in result.stderr
    assert "hook-script" in result.stderr


# ===========================================================================
# LOW-1 fix (m3-cp4 polish): CLAUDE.md classified as governance, not spec-doc
# ===========================================================================

# ---------------------------------------------------------------------------
# Test 37: LOW-1 — CLAUDE.md in Review → exit 0 (governance is permitted)
# ---------------------------------------------------------------------------

def test_classify_claude_md_as_governance(run_hook, tmp_armature):
    """phase=Review, file=CLAUDE.md → exit 0 (governance, permitted in Review).

    Before the LOW-1 fix, CLAUDE.md was classified as spec-doc because it is
    a repo-root .md file and the spec-doc check ran before the governance check.
    spec-doc is NOT permitted in Review, so editing CLAUDE.md was erroneously
    blocked (exit 2).

    After the fix, the governance check for CLAUDE.md/CODEX.md/agents.md/
    AGENTS.md runs BEFORE the spec-doc check, so these files are correctly
    classified as governance.  governance IS permitted in Review → exit 0.
    """
    _write_phase(tmp_armature, "Review")
    result = run_hook(
        "phase-gate.sh",
        edit_event("CLAUDE.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 38: LOW-1 — CLAUDE.md in Design → exit 0 (governance permitted in Design)
# ---------------------------------------------------------------------------

def test_classify_claude_md_governance_allowed_in_design(run_hook, tmp_armature):
    """phase=Design, file=CLAUDE.md → exit 0 (governance, permitted in Design).

    Confirms the LOW-1 fix does not break the Design phase: governance is
    permitted in Design, so editing CLAUDE.md must still exit 0.
    This test guards against a regression where moving the governance check
    earlier accidentally blocks CLAUDE.md in Design.
    """
    _write_phase(tmp_armature, "Design")
    result = run_hook(
        "phase-gate.sh",
        edit_event("CLAUDE.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ===========================================================================
# LOW-2 fix (m3-cp4 polish): NUL byte in raw JSON stdin payload → exit 2
# ===========================================================================

# ---------------------------------------------------------------------------
# Test 39: LOW-2 — NUL byte in raw JSON stdin → exit 2 BLOCK
# ---------------------------------------------------------------------------

def test_block_nul_byte_in_json_payload(repo_root, tmp_armature):
    """JSON stdin payload with a literal NUL byte (0x00) → exit 2 + BLOCK.

    bash command substitution ($(cat)) silently strips NUL bytes from the
    byte stream.  Under the old pattern, a payload of
      {"tool_input":{"file_path":"foo<NUL>bar"}}
    was captured by bash as
      {"tool_input":{"file_path":"foobar"}}
    — the NUL was stripped and 'foobar' passed the control-character check.

    The LOW-2 fix replaces the bash payload capture with Python
    sys.stdin.buffer.read(), which preserves NUL bytes.  The hook now exits 2
    with BLOCK [PHASE-001] when any NUL byte appears in the raw JSON stream.

    This test sends binary stdin directly (bypassing run_hook's text=True
    limitation) using subprocess.run with input=bytes.
    """
    import shutil as _shutil
    bash_bin = _shutil.which("bash")
    if bash_bin is None:
        pytest.skip("bash not available")

    hook_path = repo_root / ".armature" / "hooks" / "phase-gate.sh"
    # Payload: valid JSON wrapper with a literal NUL byte embedded in file_path
    payload = b'{"tool_input":{"file_path":"foo\x00bar"}}'

    result = subprocess.run(
        [bash_bin, str(hook_path)],
        input=payload,
        capture_output=True,
        cwd=str(tmp_armature),
        timeout=10,
    )
    assert result.returncode == 2
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "BLOCK" in stderr
    assert "PHASE-001" in stderr
