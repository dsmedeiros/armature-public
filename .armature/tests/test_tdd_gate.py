"""
Tests for tdd-gate.sh (TDD-001).

Hook behaviour (verified from source):
  - Reads tool_input.file_path from stdin JSON.
  - Rejects NUL bytes in raw JSON stdin → exit 2 + "BLOCK [TDD-001]".
  - Normalizes to absolute path (prepends REPO_ROOT for relative paths).
  - Hotfix bypass: if .armature/session/phase contains "Hotfix" → advisory + exit 0.
  - Is-itself-a-test check: basename starts test_ or path contains /tests/ or
    /__tests__/ → exit 0 (no test-for-tests requirement).
  - Exempt extensions: .md .txt .rst .yaml .yml .toml .json .ini .cfg .env
    and files with no extension at all → exit 0.
  - Exempt path prefixes: .armature/ .claude/ docs/ adr/ → exit 0.
  - Hook script convention: .armature/hooks/<name>.sh →
      .armature/tests/test_<name_dashes_to_underscores>.py
  - Python source convention: <dir>/<stem>.py →
      tests/test_<stem>.py  OR  tests/<dir>/test_<stem>.py
  - JS/TS source convention: <dir>/<stem>.{ts,js,tsx,jsx} →
      <dir>/<stem>.test.<ext>  OR  <dir>/<stem>.spec.<ext>  OR
      __tests__/<stem>.test.<ext>
  - Unknown extension → exit 0 (fail-open).
  - Fail-open conditions: not a git repo, Python unavailable, invalid JSON,
    missing/empty file_path.
  - Control characters in file_path → exit 2 + "BLOCK [TDD-001]" (MEDIUM-1 fix).
  - JSON null for file_path → exit 0 (treated as absent; LOW-1 fix).

All filesystem tests use tmp_armature so the real repo is never mutated.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from .helpers import edit_event


# ---------------------------------------------------------------------------
# MUST 1: hook script with matching test → exit 0
# ---------------------------------------------------------------------------

def test_allow_hook_script_with_matching_test(run_hook, tmp_armature):
    """tdd-gate.sh with .armature/tests/test_tdd_gate.py present → exit 0."""
    tests_dir = tmp_armature / ".armature" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_tdd_gate.py").write_text("# test\n")

    result = run_hook(
        "tdd-gate.sh",
        edit_event(".armature/hooks/tdd-gate.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 2: hook script without matching test → exit 2 + BLOCK + TDD-001
# ---------------------------------------------------------------------------

def test_block_hook_script_without_test(run_hook, tmp_armature):
    """tdd-gate.sh with NO .armature/tests/test_tdd_gate.py → exit 2 + BLOCK + TDD-001."""
    # Ensure tests dir exists but does NOT contain test_tdd_gate.py
    tests_dir = tmp_armature / ".armature" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    result = run_hook(
        "tdd-gate.sh",
        edit_event(".armature/hooks/tdd-gate.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TDD-001" in result.stderr


# ---------------------------------------------------------------------------
# MUST 3: markdown file → exit 0
# ---------------------------------------------------------------------------

def test_allow_markdown_file(run_hook, tmp_armature):
    """Editing a .md file → exit 0 (exempt extension)."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event("docs/README.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 4: yaml file → exit 0
# ---------------------------------------------------------------------------

def test_allow_yaml_file(run_hook, tmp_armature):
    """Editing a .yaml file → exit 0 (exempt extension)."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event("config/settings.yaml"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 5: governance path (.armature/session/state.md) → exit 0
# ---------------------------------------------------------------------------

def test_allow_governance_path(run_hook, tmp_armature):
    """Editing .armature/session/state.md → exit 0 (governance prefix exempt)."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event(".armature/session/state.md"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 6: test file itself → exit 0
# ---------------------------------------------------------------------------

def test_allow_test_file_itself(run_hook, tmp_armature):
    """Editing a file whose basename starts with test_ → exit 0 (is itself a test)."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/test_helpers.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 7: Python source with matching test at tests root → exit 0
# ---------------------------------------------------------------------------

def test_allow_python_source_with_tests_root_match(run_hook, tmp_armature):
    """src/foo.py with tests/test_foo.py present → exit 0."""
    tests_dir = tmp_armature / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_foo.py").write_text("# test\n")

    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 8: Python source without test → exit 2
# ---------------------------------------------------------------------------

def test_block_python_source_without_test(run_hook, tmp_armature):
    """src/foo.py without any matching test → exit 2."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TDD-001" in result.stderr


# ---------------------------------------------------------------------------
# MUST 9: JS/TS source with .test.<ext> sibling → exit 0
# ---------------------------------------------------------------------------

def test_allow_js_source_with_dot_test_match(run_hook, tmp_armature):
    """src/foo.ts with src/foo.test.ts present → exit 0."""
    src_dir = tmp_armature / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "foo.test.ts").write_text("// test\n")

    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/foo.ts"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 10: JS/TS source without test → exit 2
# ---------------------------------------------------------------------------

def test_block_js_source_without_test(run_hook, tmp_armature):
    """src/foo.ts without any matching test → exit 2."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/foo.ts"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TDD-001" in result.stderr


# ---------------------------------------------------------------------------
# MUST 11: invalid JSON → exit 0 (fail-open)
# ---------------------------------------------------------------------------

def test_fail_open_invalid_json(run_hook, tmp_armature):
    """Invalid JSON stdin → exit 0 (fail-open, cannot parse file_path)."""
    result = run_hook(
        "tdd-gate.sh",
        "{{not json at all",
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 12: no file_path → exit 0 (fail-open)
# ---------------------------------------------------------------------------

def test_fail_open_no_file_path(run_hook, tmp_armature):
    """JSON missing file_path → exit 0 (fail-open)."""
    payload = json.dumps({"tool_input": {"command": "echo hi"}})
    result = run_hook(
        "tdd-gate.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MUST 13: Hotfix bypass → exit 0 + ADVISORY
# ---------------------------------------------------------------------------

def test_hotfix_bypass(run_hook, tmp_armature):
    """Hotfix phase active → exit 0 + 'ADVISORY' on stderr, even with missing test."""
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.write_text("Hotfix")

    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/main.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0
    assert "ADVISORY" in result.stderr


# ---------------------------------------------------------------------------
# MUST 14: unknown extension → exit 0 (fail-open)
# ---------------------------------------------------------------------------

def test_fail_open_unknown_extension(run_hook, tmp_armature):
    """src/foo.rs with no test → exit 0 (unknown extension, fail-open)."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/foo.rs"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# SHOULD 15: BLOCK message names the expected test path
# ---------------------------------------------------------------------------

def test_block_message_names_expected_test_path(run_hook, tmp_armature):
    """BLOCK message for a hook script names the expected test path."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event(".armature/hooks/tdd-gate.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "test_tdd_gate.py" in result.stderr


# ---------------------------------------------------------------------------
# SHOULD 16: BLOCK message references TDD-001
# ---------------------------------------------------------------------------

def test_block_message_references_tdd_001(run_hook, tmp_armature):
    """BLOCK message contains the invariant ID 'TDD-001'."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/bar.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "TDD-001" in result.stderr


# ---------------------------------------------------------------------------
# SHOULD 17: relative path is resolved correctly
# ---------------------------------------------------------------------------

def test_relative_path_normalized(run_hook, tmp_armature):
    """Relative file_path → resolved to absolute and blocked correctly."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event("app/utils.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr


# ---------------------------------------------------------------------------
# SHOULD 18: Python source with nested tests/<dir>/test_<stem>.py match
# ---------------------------------------------------------------------------

def test_python_source_with_nested_tests_dir_match(run_hook, tmp_armature):
    """src/foo.py with tests/src/test_foo.py → exit 0 (nested dir match)."""
    nested_tests_dir = tmp_armature / "tests" / "src"
    nested_tests_dir.mkdir(parents=True, exist_ok=True)
    (nested_tests_dir / "test_foo.py").write_text("# test\n")

    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# SHOULD 19: dash-to-underscore rename for hook script convention
# ---------------------------------------------------------------------------

def test_hook_script_dash_to_underscore_rename(run_hook, tmp_armature):
    """block-dangerous-commands.sh → expects test_block_dangerous_commands.py."""
    tests_dir = tmp_armature / ".armature" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_block_dangerous_commands.py").write_text("# test\n")

    result = run_hook(
        "tdd-gate.sh",
        edit_event(".armature/hooks/block-dangerous-commands.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# SHOULD 20: JS source with __tests__/ convention → exit 0
# ---------------------------------------------------------------------------

def test_js_source_with_underscores_tests_dir_match(run_hook, tmp_armature):
    """src/foo.js with __tests__/foo.test.js → exit 0."""
    tests_dir = tmp_armature / "__tests__"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "foo.test.js").write_text("// test\n")

    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/foo.js"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# SHOULD 21: .armature/tests/test_foo.py is itself a test → exit 0
# ---------------------------------------------------------------------------

def test_allow_armature_tests_test_file(run_hook, tmp_armature):
    """.armature/tests/test_foo.py → exit 0 (basename starts with test_)."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event(".armature/tests/test_foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# SHOULD 22: shell script outside .armature/hooks/ → fail-open (unknown convention)
# ---------------------------------------------------------------------------

def test_fail_open_shell_script_outside_armature_hooks(run_hook, tmp_armature):
    """scripts/deploy.sh → exit 0 (unknown convention; fail-open)."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event("scripts/deploy.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# CP1 carry-forward: control-char rejection (MEDIUM-1 fix)
# ---------------------------------------------------------------------------

def test_block_control_chars_in_file_path(run_hook, tmp_armature):
    """file_path with embedded newline → exit 2 with BLOCK and 'control characters'.

    A JSON string containing a \\n escape decodes to a real newline character
    (ord < 32).  The hook must reject this before exempt-path or test-lookup
    logic fires, so a crafted path like '.armature/tests\\nsrc/foo.py' cannot
    bypass the gate by prefix-matching '.armature/'.
    """
    payload = '{"tool_input":{"file_path":".armature/tests\\nsrc/foo.py"}}'
    result = run_hook(
        "tdd-gate.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TDD-001" in result.stderr
    assert "control characters" in result.stderr


# ---------------------------------------------------------------------------
# CP1 carry-forward: JSON null treated as missing file_path → exit 0 (LOW-1 fix)
# ---------------------------------------------------------------------------

def test_fail_open_null_file_path(run_hook, tmp_armature):
    """JSON null for file_path → exit 0 (treated as absent; fail-open).

    When file_path is JSON null the Python extractor must treat it identically
    to a missing key, not print the string 'None' and create a spurious path.
    """
    payload = '{"tool_input":{"file_path":null}}'
    result = run_hook(
        "tdd-gate.sh",
        payload,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# MEDIUM-1 fix: case-insensitive filesystem bypass
# Test 25
# ---------------------------------------------------------------------------

def test_block_hook_script_with_uppercase_path(run_hook, tmp_armature):
    """.armature/HOOKS/foo.sh (uppercase HOOKS) without test → exit 2 (case-insensitive match).

    On case-insensitive filesystems the path .armature/HOOKS/foo.sh resolves
    to the same on-disk location as .armature/hooks/foo.sh.  The gate must
    normalise to lowercase for the prefix comparison so the hook-script
    convention fires and blocks when no test exists.
    """
    # Ensure .armature/tests/ dir exists but NOT test_foo.py
    tests_dir = tmp_armature / ".armature" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    result = run_hook(
        "tdd-gate.sh",
        edit_event(".armature/HOOKS/foo.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TDD-001" in result.stderr


# ---------------------------------------------------------------------------
# Cycle-3 MEDIUM-2 fix: subdirectory hook scripts are BLOCKED (non-canonical)
# Test 26 (updated from cycle-2: was exit 0 fall-through, now exit 2 block)
# ---------------------------------------------------------------------------

def test_block_hook_script_in_subdirectory(run_hook, tmp_armature):
    """.armature/hooks/sub/foo.sh → exit 2 (non-canonical subdir in hooks/ is blocked).

    Previously this path fell through to the .armature/* path-prefix exemption
    (exit 0).  The cycle-3 fix closes the composition gap: any .sh file under
    a subdirectory of .armature/hooks/ is blocked with an explanatory message
    so that .armature/hooks/__tests__/foo.sh cannot evade TDD discipline by
    being exempt as a test-file.
    """
    result = run_hook(
        "tdd-gate.sh",
        edit_event(".armature/hooks/sub/foo.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TDD-001" in result.stderr
    assert "subdirectory" in result.stderr


# ---------------------------------------------------------------------------
# MEDIUM-3 fix: hook script with test_ prefix is still gated
# Test 27
# ---------------------------------------------------------------------------

def test_block_hook_script_with_test_prefix_subject_to_tdd(run_hook, tmp_armature):
    """.armature/hooks/test_foo.sh without matching test → exit 2.

    The hook-script convention check runs BEFORE the test-file exemption.
    A hook named test_foo.sh must still satisfy the TDD convention
    (.armature/tests/test_test_foo.py) — the test_ prefix does NOT exempt it.
    """
    # Ensure .armature/tests/ dir exists but NOT test_test_foo.py
    tests_dir = tmp_armature / ".armature" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    result = run_hook(
        "tdd-gate.sh",
        edit_event(".armature/hooks/test_foo.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TDD-001" in result.stderr


# ---------------------------------------------------------------------------
# MEDIUM-3 fix: test_ prefix exemption still fires for non-hook-script paths
# Test 28
# ---------------------------------------------------------------------------

def test_allow_test_helper_outside_hooks(run_hook, tmp_armature):
    """tests/test_helper.py → exit 0 (test-file exemption fires for non-hook-script path).

    Confirms that moving the hook-script convention check to first position has
    not broken the test-file exemption for ordinary test helpers.
    """
    result = run_hook(
        "tdd-gate.sh",
        edit_event("tests/test_helper.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# LOW-1 fix: .mts extension gated
# Test 29
# ---------------------------------------------------------------------------

def test_allow_mts_with_matching_test(run_hook, tmp_armature):
    """src/foo.mts with src/foo.test.mts present → exit 0 (mts extension covered)."""
    src_dir = tmp_armature / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "foo.test.mts").write_text("// test\n")

    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/foo.mts"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# LOW-1 fix: .cts extension gated
# Test 30
# ---------------------------------------------------------------------------

def test_block_cts_without_test(run_hook, tmp_armature):
    """src/foo.cts without any matching test → exit 2 (cts extension covered)."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/foo.cts"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TDD-001" in result.stderr


# ---------------------------------------------------------------------------
# LOW-1 fix: .mjs extension gated
# Test 31
# ---------------------------------------------------------------------------

def test_block_mjs_without_test(run_hook, tmp_armature):
    """src/foo.mjs without any matching test → exit 2 (mjs extension covered)."""
    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/foo.mjs"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TDD-001" in result.stderr


# ---------------------------------------------------------------------------
# Test 32 (cycle-2 / m3-cp3 HIGH fix): NUL byte in phase file must not bypass
# ---------------------------------------------------------------------------

def test_block_nul_byte_phase_file_tdd_gate(run_hook, tmp_armature):
    """Phase file containing 'Hot\\x00fix' must NOT trigger Hotfix bypass.

    bash command-substitution strips NUL bytes, so 'Hot\\x00fix' would be
    captured as 'Hotfix' and bypass tdd-gate.  The cycle-2 Python-based
    phase reader rejects files containing control bytes, so the phase is treated
    as unknown → no bypass → the TDD gate fires normally.

    With src/foo.py and no matching test file, exit 2 (BLOCK) must be
    returned — confirming the gate was NOT bypassed.
    """
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.parent.mkdir(parents=True, exist_ok=True)
    phase_file.write_bytes(b"Hot\x00fix")

    # No tests/test_foo.py → TDD gate fires
    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TDD-001" in result.stderr
    assert "ADVISORY" not in result.stderr


# ---------------------------------------------------------------------------
# Test 33 (cycle-3 / m3-cp3 MEDIUM-1 fix): Unicode NBSP in phase file must not bypass
# ---------------------------------------------------------------------------

def test_block_unicode_nbsp_phase_file_tdd_gate(run_hook, tmp_armature):
    """Phase file containing NBSP+Hotfix+NBSP must NOT trigger Hotfix bypass.

    Python's str.strip() (without arguments) strips Unicode whitespace including
    U+00A0 NO-BREAK SPACE (\\xc2\\xa0 in UTF-8).  The cycle-2 reader used .strip()
    which allowed '\\xc2\\xa0Hotfix\\xc2\\xa0' to decode to 'Hotfix' and bypass.
    The cycle-3 fix uses .strip(' \\t\\n\\r') which only strips ASCII whitespace,
    so the NBSP-wrapped value is not in VALID → treated as unknown phase →
    no bypass occurs → TDD gate fires normally.

    With src/foo.py and no matching test file, exit 2 (BLOCK) must be
    returned — confirming the gate was NOT bypassed.
    """
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.parent.mkdir(parents=True, exist_ok=True)
    # NBSP (U+00A0) = \\xc2\\xa0 in UTF-8; wrap Hotfix on both sides
    phase_file.write_bytes(b"\xc2\xa0Hotfix\xc2\xa0")

    # No tests/test_foo.py → TDD gate fires
    result = run_hook(
        "tdd-gate.sh",
        edit_event("src/foo.py"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TDD-001" in result.stderr
    assert "ADVISORY" not in result.stderr


# ---------------------------------------------------------------------------
# Test 34 (cycle-3 / m3-cp3 MEDIUM-2 fix): .armature/hooks/__tests__/foo.sh → BLOCK
# ---------------------------------------------------------------------------

def test_block_armature_hooks_double_underscore_tests_path(run_hook, tmp_armature):
    """.armature/hooks/__tests__/foo.sh → exit 2 (BLOCK, not exempted as test-file).

    Previously the tdd-gate Check 1 (hook-script convention) only caught
    top-level .sh files; a subdir path fell through to Check 2 (test-file
    exemption) which matched '__tests__/' → exit 0 (no TDD required).

    The cycle-3 fix changes Check 1 to BLOCK any .sh file under a subdirectory
    of .armature/hooks/ with a clear message.  This closes the composition gap
    where the __tests__/ exemption was silently eating paths in the hooks dir.
    """
    # Ensure .armature/tests/ dir exists but no test file for the hook
    tests_dir = tmp_armature / ".armature" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    result = run_hook(
        "tdd-gate.sh",
        edit_event(".armature/hooks/__tests__/foo.sh"),
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2
    assert "BLOCK" in result.stderr
    assert "TDD-001" in result.stderr
    assert "subdirectory" in result.stderr


# ===========================================================================
# LOW-2 fix (m3-cp4 polish): NUL byte in raw JSON stdin payload → exit 2
# ===========================================================================

# ---------------------------------------------------------------------------
# Test 35: LOW-2 — NUL byte in raw JSON stdin → exit 2 BLOCK
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
    with BLOCK [TDD-001] when any NUL byte appears in the raw JSON stream.

    This test sends binary stdin directly (bypassing run_hook's text=True
    limitation) using subprocess.run with input=bytes.
    """
    bash_bin = shutil.which("bash")
    if bash_bin is None:
        pytest.skip("bash not available")

    hook_path = repo_root / ".armature" / "hooks" / "tdd-gate.sh"
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
    assert "TDD-001" in stderr
