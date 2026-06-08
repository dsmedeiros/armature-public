"""
CP1 smoke test — verifies the pytest framework wires correctly end-to-end:
  pytest discovers .armature/tests/
  conftest.py loads and provides run_hook
  run_hook invokes a real hook with a real payload
  the hook exits as expected
"""

from .helpers import bash_event


def test_smoke_block_dangerous_allows_safe_command(run_hook):
    # safe command should exit 0
    result = run_hook("block-dangerous-commands.sh", bash_event("echo hello"))
    assert result.returncode == 0
