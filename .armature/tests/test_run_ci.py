"""
Tests for run-ci.sh (CI-001).

Hook behaviour (verified from source):
  - Event: Stop
  - Reads .armature/ci.yaml; executes steps in order:
    invariants -> test -> types -> lint
  - Advisory mode by default (exit 0 even on failure)
  - ARMATURE_CI_BLOCK=1 -> exit 2 on any step failure
  - Skip conditions (checked in order):
    1. Phase == "Hotfix" -> exit 0 + ADVISORY
    2. .armature/.code-dirty absent -> exit 0 + ADVISORY
    3. .armature/session/skip-ci present -> exit 0 + ADVISORY
    4. .armature/ci.yaml absent -> exit 0 + ADVISORY
    5. Python unavailable -> exit 0 + ADVISORY
  - Dirty marker removed on full pipeline success; preserved on failure
  - NUL bytes in ci.yaml -> fail-open (ADVISORY), exit 0
  - ci.yaml command as YAML list -> WARN + skip (not execute)
  - Trust model: commands run via bash -c with no secondary sanitization

Test isolation: each test uses tmp_armature fixture for an isolated repo.

Helper functions used across tests:
  _write_ci_yaml(tmp_armature, content) -> writes .armature/ci.yaml
  _set_dirty(tmp_armature)              -> touches .armature/.code-dirty
  _set_phase(tmp_armature, value)       -> writes .armature/session/phase
"""

import os
import subprocess

import pytest

from .helpers import stop_event


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

def _write_ci_yaml(tmp_armature, content: str):
    """Write .armature/ci.yaml in the temp repo and return its path."""
    ci_yaml = tmp_armature / ".armature" / "ci.yaml"
    ci_yaml.write_text(content, encoding="utf-8")
    return ci_yaml


def _set_dirty(tmp_armature):
    """Touch the dirty marker at .armature/.code-dirty."""
    marker = tmp_armature / ".armature" / ".code-dirty"
    marker.touch()
    return marker


def _set_phase(tmp_armature, value: str):
    """Write .armature/session/phase with the given value."""
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.write_text(value, encoding="utf-8")
    return phase_file


# ---------------------------------------------------------------------------
# MUST 1: run-ci.sh exists at .armature/hooks/run-ci.sh
# ---------------------------------------------------------------------------

def test_run_ci_script_exists(repo_root):
    """run-ci.sh must exist at .armature/hooks/run-ci.sh."""
    hook = repo_root / ".armature" / "hooks" / "run-ci.sh"
    assert hook.exists(), "run-ci.sh must exist at .armature/hooks/run-ci.sh"


# ---------------------------------------------------------------------------
# MUST 2: No dirty marker -> exit 0 + ADVISORY (SKIP)
# ---------------------------------------------------------------------------

def test_no_dirty_marker_exits_zero(run_hook, tmp_armature):
    """When .code-dirty is absent, hook must exit 0."""
    dirty = tmp_armature / ".armature" / ".code-dirty"
    if dirty.exists():
        dirty.unlink()

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 when dirty marker is absent (advisory mode)"
    )


def test_no_dirty_marker_emits_advisory(run_hook, tmp_armature):
    """When .code-dirty is absent, hook must emit ADVISORY to stderr."""
    dirty = tmp_armature / ".armature" / ".code-dirty"
    if dirty.exists():
        dirty.unlink()

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert "ADVISORY" in result.stderr, (
        "run-ci.sh must emit ADVISORY when dirty marker is absent"
    )


# ---------------------------------------------------------------------------
# MUST 3: Dirty marker + ci.yaml absent -> exit 0 + ADVISORY
# ---------------------------------------------------------------------------

def test_dirty_marker_no_ci_yaml_exits_zero(run_hook, tmp_armature):
    """When dirty marker present but ci.yaml absent, hook must exit 0."""
    _set_dirty(tmp_armature)
    ci_yaml = tmp_armature / ".armature" / "ci.yaml"
    if ci_yaml.exists():
        ci_yaml.unlink()

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 when ci.yaml is absent (advisory mode)"
    )


def test_dirty_marker_no_ci_yaml_emits_advisory(run_hook, tmp_armature):
    """When dirty marker present but ci.yaml absent, hook must emit ADVISORY."""
    _set_dirty(tmp_armature)
    ci_yaml = tmp_armature / ".armature" / "ci.yaml"
    if ci_yaml.exists():
        ci_yaml.unlink()

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert "ADVISORY" in result.stderr, (
        "run-ci.sh must emit ADVISORY when ci.yaml is absent"
    )


# ---------------------------------------------------------------------------
# MUST 4: ci.yaml with test.command: null -> step skipped, exit 0
# ---------------------------------------------------------------------------

def test_null_command_step_skipped(run_hook, tmp_armature):
    """A step with command: null must be skipped (SKIP emitted), hook exits 0."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, "test:\n  command: null\n")

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 when all steps are null"
    )
    assert "SKIP" in result.stdout, (
        "run-ci.sh must emit SKIP when command is null"
    )


# ---------------------------------------------------------------------------
# MUST 5: ci.yaml with passing test command (true) -> exit 0, dirty removed
# ---------------------------------------------------------------------------

def test_passing_command_exits_zero(run_hook, tmp_armature):
    """A passing step command must cause exit 0."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "true"\n')

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 when all steps pass"
    )


def test_passing_command_emits_pass(run_hook, tmp_armature):
    """A passing step command must emit PASS in output."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "true"\n')

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert "PASS" in result.stdout, (
        "run-ci.sh must emit PASS when step exits 0"
    )


def test_passing_command_removes_dirty_marker(run_hook, tmp_armature):
    """When all steps pass, dirty marker must be removed."""
    marker = _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "true"\n')

    run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert not marker.exists(), (
        "Dirty marker must be removed after all steps pass"
    )


# ---------------------------------------------------------------------------
# MUST 6: ci.yaml with failing test command (false) -> exit 0, FAIL in stderr
# ---------------------------------------------------------------------------

def test_failing_command_advisory_mode_exits_zero(run_hook, tmp_armature):
    """A failing step must still exit 0 in advisory mode (default)."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "false"\n')

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 in advisory mode even when a step fails"
    )


def test_failing_command_emits_fail(run_hook, tmp_armature):
    """A failing step must emit FAIL in stderr."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "false"\n')

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert "FAIL" in result.stderr, (
        "run-ci.sh must emit FAIL when a step exits non-zero"
    )


# ---------------------------------------------------------------------------
# MUST 7: ARMATURE_CI_BLOCK=1 + failing -> exit 2
# ---------------------------------------------------------------------------

def test_block_mode_failing_exits_two(run_hook, tmp_armature):
    """ARMATURE_CI_BLOCK=1 with a failing step must exit 2."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "false"\n')

    env = os.environ.copy()
    env["ARMATURE_CI_BLOCK"] = "1"
    result = run_hook(
        "run-ci.sh",
        stop_event(),
        env_overrides={"ARMATURE_CI_BLOCK": "1"},
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2, (
        "run-ci.sh must exit 2 when ARMATURE_CI_BLOCK=1 and a step fails"
    )


# ---------------------------------------------------------------------------
# MUST 8: ARMATURE_CI_BLOCK=1 + passing -> exit 0
# ---------------------------------------------------------------------------

def test_block_mode_passing_exits_zero(run_hook, tmp_armature):
    """ARMATURE_CI_BLOCK=1 with all passing steps must still exit 0."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "true"\n')

    result = run_hook(
        "run-ci.sh",
        stop_event(),
        env_overrides={"ARMATURE_CI_BLOCK": "1"},
        cwd=str(tmp_armature),
    )
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 when ARMATURE_CI_BLOCK=1 and all steps pass"
    )


# ---------------------------------------------------------------------------
# Cycle-21: block mode must also propagate infrastructure-level failures
# ---------------------------------------------------------------------------

def test_block_mode_unhandled_driver_exception_propagates_to_exit_2(
    run_hook, tmp_armature, tmp_path
):
    """When the inner Python driver exits 1 (not the documented 0 or 2),
    in block mode (ARMATURE_CI_BLOCK=1) the outer wrapper must propagate
    as exit 2. The cycle-21 fix targets this exact path: pre-PR-25 the
    wrapper only handled MAIN_RC==2 explicitly, silently dropping non-2
    nonzero codes (any unhandled exception -> exit 1) to exit 0 — the
    fail-closed contract was violated.

    Originally this test triggered MAIN_RC=1 via `import yaml` raising
    ModuleNotFoundError on hosts without PyYAML. That path is now
    explicitly handled by an `except ImportError` branch at the top of
    the driver that emits a stderr advisory and exits 0 (graceful skip
    in both advisory and block modes; covered by the dedicated test
    `test_pyyaml_missing_exits_zero_advisory_in_both_modes` below).

    To preserve cycle-21 regression coverage for OTHER infrastructure
    failures, this test now triggers an unhandled exception inside the
    yaml.safe_load call: inject a fake `yaml` module via PYTHONPATH
    that imports successfully but raises RuntimeError from safe_load.
    The driver catches yaml.YAMLError; RuntimeError escapes the except
    clause and propagates up, producing exit 1 from the Python child.
    MAIN_RC=$? captures 1, and the cycle-21 wrapper propagates as
    exit 2.
    """
    import os
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'invariants:\n  command: "true"\n')

    fake_yaml_dir = tmp_path / "fake_pylib"
    fake_yaml_dir.mkdir()
    # Fake yaml module that imports OK but raises an unhandled exception
    # from safe_load — escapes the `except yaml.YAMLError` clause, producing
    # MAIN_RC=1 via Python's default uncaught-exception exit behavior.
    (fake_yaml_dir / "yaml.py").write_text(
        "class YAMLError(Exception):\n"
        "    pass\n"
        "\n"
        "def safe_load(text):\n"
        "    raise RuntimeError(\n"
        "        'test-injected: unhandled driver exception for cycle-21'\n"
        "    )\n",
        encoding="utf-8",
    )
    env_overrides = {
        "ARMATURE_CI_BLOCK": "1",
        "PYTHONPATH": str(fake_yaml_dir) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }

    result = run_hook(
        "run-ci.sh",
        stop_event(),
        env_overrides=env_overrides,
        cwd=str(tmp_armature),
    )
    assert result.returncode == 2, (
        f"block mode must propagate MAIN_RC=1 as exit 2 (cycle-21 contract); "
        f"got {result.returncode}; stderr={result.stderr[-500:]!r}"
    )


# ---------------------------------------------------------------------------
# PyYAML missing — explicit advisory-skip contract (new in this PR)
# ---------------------------------------------------------------------------

def test_pyyaml_missing_exits_zero_advisory_in_both_modes(
    run_hook, tmp_armature, tmp_path
):
    """When PyYAML is unavailable (`import yaml` raises ImportError), the
    driver must emit a stderr advisory and exit 0 in BOTH advisory and
    block modes — distinct from other infrastructure failures, which
    still hit the cycle-21 wrapper. This is the explicit fail-open
    contract added in this PR (the previous behavior was to let the
    uncaught ImportError propagate as exit 1, which cycle-21 then turned
    into exit 2 in block mode — a hard infrastructure failure that broke
    fail-open-on-environmental-flakiness expectations).
    """
    import os
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'invariants:\n  command: "true"\n')

    fake_yaml_dir = tmp_path / "fake_pylib"
    fake_yaml_dir.mkdir()
    (fake_yaml_dir / "yaml.py").write_text(
        "raise ImportError('test-injected: simulating PyYAML missing')\n",
        encoding="utf-8",
    )

    # Both modes must exit 0 with the documented advisory string.
    for block_mode in ("0", "1"):
        env_overrides = {
            "ARMATURE_CI_BLOCK": block_mode,
            "PYTHONPATH": str(fake_yaml_dir) + os.pathsep + os.environ.get("PYTHONPATH", ""),
        }
        result = run_hook(
            "run-ci.sh",
            stop_event(),
            env_overrides=env_overrides,
            cwd=str(tmp_armature),
        )
        assert result.returncode == 0, (
            f"PyYAML missing must exit 0 in ARMATURE_CI_BLOCK={block_mode}; "
            f"got {result.returncode}; stderr={result.stderr[-500:]!r}"
        )
        assert "PyYAML not available" in result.stderr, (
            f"PyYAML missing must emit advisory in stderr (mode={block_mode}); "
            f"stderr={result.stderr[-500:]!r}"
        )


# ---------------------------------------------------------------------------
# MUST 9: Hotfix phase -> exit 0, ADVISORY in stderr mentioning Hotfix
# ---------------------------------------------------------------------------

def test_hotfix_phase_exits_zero(run_hook, tmp_armature):
    """When phase is Hotfix, hook must exit 0."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "false"\n')
    _set_phase(tmp_armature, "Hotfix")

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 when Hotfix phase is active"
    )


def test_hotfix_phase_emits_advisory_with_hotfix(run_hook, tmp_armature):
    """When phase is Hotfix, stderr must contain ADVISORY and 'Hotfix'."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "false"\n')
    _set_phase(tmp_armature, "Hotfix")

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert "ADVISORY" in result.stderr, (
        "run-ci.sh must emit ADVISORY when Hotfix phase is active"
    )
    assert "Hotfix" in result.stderr, (
        "run-ci.sh ADVISORY message must mention 'Hotfix'"
    )


# ---------------------------------------------------------------------------
# MUST 10: skip-ci marker present -> exit 0 + ADVISORY
# ---------------------------------------------------------------------------

def test_skip_ci_marker_exits_zero(run_hook, tmp_armature):
    """When skip-ci marker is present, hook must exit 0."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "false"\n')
    skip_ci = tmp_armature / ".armature" / "session" / "skip-ci"
    skip_ci.touch()

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 when skip-ci marker is present"
    )


def test_skip_ci_marker_emits_advisory(run_hook, tmp_armature):
    """When skip-ci marker is present, hook must emit ADVISORY."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "false"\n')
    skip_ci = tmp_armature / ".armature" / "session" / "skip-ci"
    skip_ci.touch()

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert "ADVISORY" in result.stderr, (
        "run-ci.sh must emit ADVISORY when skip-ci marker is present"
    )


# ---------------------------------------------------------------------------
# MUST 11: NUL byte in ci.yaml -> exit 0 (fail-open, ADVISORY)
# ---------------------------------------------------------------------------

def test_nul_byte_in_ci_yaml_exits_zero(run_hook, tmp_armature):
    """ci.yaml with NUL bytes must cause fail-open exit 0."""
    _set_dirty(tmp_armature)
    ci_yaml = tmp_armature / ".armature" / "ci.yaml"
    ci_yaml.write_bytes(b"test:\n  command: \x00null\n")

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 (fail-open) when ci.yaml contains NUL bytes"
    )


def test_nul_byte_in_ci_yaml_emits_advisory(run_hook, tmp_armature):
    """ci.yaml with NUL bytes must emit ADVISORY."""
    _set_dirty(tmp_armature)
    ci_yaml = tmp_armature / ".armature" / "ci.yaml"
    ci_yaml.write_bytes(b"test:\n  command: \x00null\n")

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert "ADVISORY" in result.stderr, (
        "run-ci.sh must emit ADVISORY when ci.yaml contains NUL bytes"
    )


# ---------------------------------------------------------------------------
# MUST 12: command as YAML list -> step skipped with WARN
# ---------------------------------------------------------------------------

def test_list_command_emits_warn(run_hook, tmp_armature):
    """A YAML-list command must be skipped with a WARN message."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, "test:\n  command:\n    - echo\n    - hello\n")

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert "WARN" in result.stderr, (
        "run-ci.sh must emit WARN when command is a YAML list (not string)"
    )


def test_list_command_exits_zero(run_hook, tmp_armature):
    """A YAML-list command must cause exit 0 (not a block)."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, "test:\n  command:\n    - echo\n    - hello\n")

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 when command is a YAML list (graceful skip)"
    )


def test_list_command_not_executed(run_hook, tmp_armature):
    """A YAML-list command must not be executed (no PASS line)."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, "test:\n  command:\n    - echo\n    - hello\n")

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert "PASS: test" not in result.stdout, (
        "run-ci.sh must not execute a YAML-list command"
    )


# ---------------------------------------------------------------------------
# MUST 13: Shell metacharacters execute via bash -c (documented trust model)
# This test VERIFIES the trust model: ci.yaml commands are executed as-is
# without secondary sanitization. This is INTENDED behavior per D13/R1.
# ---------------------------------------------------------------------------

def test_shell_metacharacters_execute(run_hook, tmp_armature):
    """Commands with shell metacharacters must execute via bash -c (trust model).

    This test verifies the documented trust model: commands from ci.yaml are
    executed via 'bash -c <command>' with no secondary sanitization. This is
    INTENDED behavior equivalent to package.json scripts. The attacker must
    already have repo write access (the trust boundary) to inject commands.

    Strategy: use a failing command that emits output so the hook surfaces
    the captured stdout. A passing echo would not surface its stdout (the
    hook only prints captured output on failure).
    """
    _set_dirty(tmp_armature)
    # Command uses $() subshell — must be executed by bash -c.
    # The command fails (exit 1) so captured stdout is emitted by the hook.
    _write_ci_yaml(
        tmp_armature,
        'test:\n  command: "echo $(echo injected); exit 1"\n',
    )

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    combined = result.stdout + result.stderr
    assert "injected" in combined, (
        "run-ci.sh must execute commands via bash -c (trust model): "
        "shell metacharacters in ci.yaml commands are intentionally executed"
    )


# ---------------------------------------------------------------------------
# MUST 14: Missing timeout_seconds -> uses default, no crash
# ---------------------------------------------------------------------------

def test_missing_timeout_uses_default(run_hook, tmp_armature):
    """A step without timeout_seconds must use the default and not crash."""
    _set_dirty(tmp_armature)
    # No timeout_seconds field
    _write_ci_yaml(tmp_armature, 'test:\n  command: "true"\n')

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must not crash when timeout_seconds is missing"
    )
    assert "PASS" in result.stdout, (
        "run-ci.sh must pass the step when command succeeds and timeout is default"
    )


# ---------------------------------------------------------------------------
# MUST 15: Step order — invariants runs before test
# ---------------------------------------------------------------------------

def test_step_order_invariants_before_test(run_hook, tmp_armature):
    """invariants step must run before test step (CI-001 execution order).

    Strategy: use failing commands that emit identifiable output so the hook
    surfaces captured stdout. PASS lines in stdout also give ordering info.
    """
    _set_dirty(tmp_armature)
    # Use failing commands so the hook emits captured output (only emitted on failure)
    # The FAIL lines in stderr carry step names and appear in order
    _write_ci_yaml(
        tmp_armature,
        'invariants:\n  command: "echo step-invariants; exit 1"\ntest:\n  command: "echo step-test; exit 1"\n',
    )

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    combined = result.stdout + result.stderr
    inv_pos = combined.find("step-invariants")
    test_pos = combined.find("step-test")
    assert inv_pos != -1, "invariants step output must appear in hook output"
    assert test_pos != -1, "test step output must appear in hook output"
    assert inv_pos < test_pos, (
        "invariants step must execute before test step"
    )


# ---------------------------------------------------------------------------
# MUST 16: Dirty marker removed after all steps pass
# ---------------------------------------------------------------------------

def test_dirty_marker_removed_after_pass(run_hook, tmp_armature):
    """Dirty marker must be removed when all steps pass."""
    marker = _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "true"\n')

    run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert not marker.exists(), (
        "Dirty marker must be removed after all steps pass"
    )


# ---------------------------------------------------------------------------
# MUST 17: Dirty marker preserved if any step fails (advisory mode, exit 0)
# ---------------------------------------------------------------------------

def test_dirty_marker_preserved_on_failure(run_hook, tmp_armature):
    """Dirty marker must be preserved when any step fails (advisory mode)."""
    marker = _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "false"\n')

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, "advisory mode must exit 0 even on failure"
    assert marker.exists(), (
        "Dirty marker must be preserved when a step fails"
    )


# ---------------------------------------------------------------------------
# MUST 18: Empty ci.yaml -> SKIP with ADVISORY
# ---------------------------------------------------------------------------

def test_empty_ci_yaml_exits_zero(run_hook, tmp_armature):
    """An empty ci.yaml must cause exit 0 (ADVISORY skip)."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, "")

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 when ci.yaml is empty"
    )


def test_empty_ci_yaml_emits_advisory(run_hook, tmp_armature):
    """An empty ci.yaml must emit ADVISORY to stderr."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, "")

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert "ADVISORY" in result.stderr, (
        "run-ci.sh must emit ADVISORY when ci.yaml is empty"
    )


# ---------------------------------------------------------------------------
# SHOULD 19: timeout_seconds: "notanumber" -> fallback to default, no crash
# ---------------------------------------------------------------------------

def test_invalid_timeout_falls_back_to_default(run_hook, tmp_armature):
    """An invalid timeout_seconds value must fall back to default without crash."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "true"\n  timeout_seconds: "notanumber"\n')

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must not crash when timeout_seconds is not a number"
    )


# ---------------------------------------------------------------------------
# SHOULD 20: Invalid YAML in ci.yaml -> exit 0 + ADVISORY (fail-open)
# ---------------------------------------------------------------------------

def test_invalid_yaml_exits_zero(run_hook, tmp_armature):
    """Malformed YAML in ci.yaml must cause fail-open exit 0."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, "test: [unclosed bracket\n  command: true\n")

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 (fail-open) on invalid YAML in ci.yaml"
    )


def test_invalid_yaml_emits_advisory(run_hook, tmp_armature):
    """Malformed YAML in ci.yaml must emit ADVISORY."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, "test: [unclosed bracket\n  command: true\n")

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert "ADVISORY" in result.stderr, (
        "run-ci.sh must emit ADVISORY when ci.yaml is invalid YAML"
    )


# ---------------------------------------------------------------------------
# SHOULD 21: Multiple steps all run in order
# ---------------------------------------------------------------------------

def test_multiple_steps_all_run(run_hook, tmp_armature):
    """Multiple configured steps must all run (invariants + test + types).

    Strategy: use failing commands so the hook emits captured stdout.
    Verify all three step names appear in FAIL output.
    """
    _set_dirty(tmp_armature)
    _write_ci_yaml(
        tmp_armature,
        (
            "invariants:\n  command: \"echo inv-ran; exit 1\"\n"
            "test:\n  command: \"echo test-ran; exit 1\"\n"
            "types:\n  command: \"echo types-ran; exit 1\"\n"
            "lint:\n  command: null\n"
        ),
    )

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    combined = result.stdout + result.stderr
    assert "inv-ran" in combined, "invariants step must have run"
    assert "test-ran" in combined, "test step must have run"
    assert "types-ran" in combined, "types step must have run"


# ---------------------------------------------------------------------------
# SHOULD 22: Step output visible in hook output
# ---------------------------------------------------------------------------

def test_step_stdout_is_visible(run_hook, tmp_armature):
    """Captured command output must be visible in hook output on failure."""
    _set_dirty(tmp_armature)
    # Failing command that emits identifiable output
    _write_ci_yaml(
        tmp_armature,
        'test:\n  command: "echo distinctive-failure-output; exit 1"\n',
    )

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    combined = result.stdout + result.stderr
    assert "distinctive-failure-output" in combined, (
        "run-ci.sh must surface command stdout in hook output on failure"
    )


# ---------------------------------------------------------------------------
# SHOULD 23: Very long command (>500 chars) -> no crash
# ---------------------------------------------------------------------------

def test_very_long_command_no_crash(run_hook, tmp_armature):
    """A very long command string (>500 chars) must not crash the hook."""
    _set_dirty(tmp_armature)
    # Build a long but valid command
    long_cmd = "echo " + ("x" * 500)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "{}"\n'.format(long_cmd))

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must not crash on a very long command string"
    )


# ---------------------------------------------------------------------------
# SHOULD 24: Phase file with CRLF -> Hotfix parsed correctly
# ---------------------------------------------------------------------------

def test_crlf_phase_hotfix_bypass(run_hook, tmp_armature):
    """Phase file with CRLF line endings must still trigger Hotfix bypass."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "false"\n')
    # Write Hotfix with CRLF
    phase_file = tmp_armature / ".armature" / "session" / "phase"
    phase_file.write_bytes(b"Hotfix\r\n")

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 when phase is 'Hotfix' (CRLF line endings)"
    )
    assert "Hotfix" in result.stderr, (
        "run-ci.sh must mention Hotfix in ADVISORY when CRLF phase file is used"
    )


# ---------------------------------------------------------------------------
# SHOULD 25: python fallback — this test is skipped if python3 is absent
# since the hook itself needs Python to run. We test that the hook
# works correctly in a CI environment that has at least one Python binary.
# We verify this by checking the hook produces expected output (which requires
# Python to have parsed ci.yaml).
# ---------------------------------------------------------------------------

def test_python_available_hook_parses_yaml(run_hook, tmp_armature):
    """Hook must parse ci.yaml using Python (either python3 or python).

    This test verifies that the Python fallback path is exercised correctly:
    the hook must have successfully parsed ci.yaml and emitted step-level
    output (not just an early ADVISORY from a skip condition).
    """
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "true"\n')

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    # If Python parsed ci.yaml, we get PASS/SKIP/FAIL output, not just ADVISORY
    combined = result.stdout + result.stderr
    assert any(tok in combined for tok in ("PASS", "SKIP", "FAIL", "Summary")), (
        "run-ci.sh must have parsed ci.yaml via Python (python3 or python fallback)"
    )


# ---------------------------------------------------------------------------
# SHOULD 26: All steps null/absent -> exit 0 + Summary
# ---------------------------------------------------------------------------

def test_all_steps_null_exits_zero(run_hook, tmp_armature):
    """ci.yaml with all steps null must exit 0."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(
        tmp_armature,
        "invariants:\n  command: null\ntest:\n  command: null\ntypes:\n  command: null\nlint:\n  command: null\n",
    )

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert result.returncode == 0, (
        "run-ci.sh must exit 0 when all steps are null"
    )


def test_all_steps_null_emits_summary(run_hook, tmp_armature):
    """ci.yaml with all steps null must emit a Summary line."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(
        tmp_armature,
        "invariants:\n  command: null\ntest:\n  command: null\ntypes:\n  command: null\nlint:\n  command: null\n",
    )

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert "Summary" in result.stdout, (
        "run-ci.sh must emit Summary line even when all steps are null"
    )


# ---------------------------------------------------------------------------
# SHOULD 27: PASS summary emitted when all steps succeed
# ---------------------------------------------------------------------------

def test_summary_emitted_on_success(run_hook, tmp_armature):
    """Summary line must be emitted when all steps pass."""
    _set_dirty(tmp_armature)
    _write_ci_yaml(tmp_armature, 'test:\n  command: "true"\n')

    result = run_hook("run-ci.sh", stop_event(), cwd=str(tmp_armature))
    assert "Summary:" in result.stdout, (
        "run-ci.sh must emit Summary: line after all steps succeed"
    )
    assert "passed=1" in result.stdout, (
        "Summary must reflect 1 passed step when 'true' command succeeds"
    )


# ---------------------------------------------------------------------------
# SHOULD 28: Hook header contains CI-001 reference
# ---------------------------------------------------------------------------

def test_hook_header_contains_ci001_reference(repo_root):
    """run-ci.sh source must contain a CI-001 reference in its header."""
    hook_path = repo_root / ".armature" / "hooks" / "run-ci.sh"
    content = hook_path.read_text(encoding="utf-8")
    assert "CI-001" in content, (
        "run-ci.sh must reference CI-001 in its header comment"
    )


# ---------------------------------------------------------------------------
# SHOULD 29: Non-UTF8 binary output from a step is decoded gracefully
# ---------------------------------------------------------------------------

def test_should_29_non_utf8_step_output_handled_gracefully(run_hook, tmp_armature):
    """Non-UTF8 binary output from a CI step must be decoded with
    errors='replace' rather than crashing the subprocess reader thread.

    Red team A5b: previous implementation used text=True which decoded
    with the platform locale codec (cp1252 on Windows, ascii on Linux
    with LANG=C). Non-decodable bytes triggered UnicodeDecodeError in
    the reader thread, polluted stderr with a traceback, and silently
    dropped captured output.
    """
    _set_dirty(tmp_armature)
    # Emit 50 bytes of high-bit binary then exit 1 so the hook surfaces
    # captured output (passing steps don't echo captured output).
    _write_ci_yaml(
        tmp_armature,
        'test:\n'
        '  command: "head -c 50 /dev/urandom; exit 1"\n'
        '  timeout_seconds: 30\n',
    )
    result = run_hook(
        "run-ci.sh",
        stop_event(),
        cwd=str(tmp_armature),
    )
    # Hook exits 0 (advisory mode) regardless of step failure.
    assert result.returncode == 0, (
        f"Hook should exit 0 in advisory mode, got {result.returncode}"
    )
    # The fix: no UnicodeDecodeError traceback in stderr.
    combined = (result.stdout or "") + (result.stderr or "")
    assert "UnicodeDecodeError" not in combined, (
        "Found UnicodeDecodeError traceback in hook output — "
        "subprocess output decoding regressed"
    )
    assert "Traceback" not in combined, (
        "Found Python Traceback in hook output — "
        "an exception leaked from the subprocess reader"
    )
    # FAIL message should still be present (advisory still emitted).
    assert "FAIL" in combined, (
        f"Expected FAIL marker in hook output; got: {combined[:500]!r}"
    )
