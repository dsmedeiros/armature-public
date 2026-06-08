---
id: testing-standards
severity: high
composition-mode: advisory
---

# Testing Standards

## When to apply

Apply to test files (`**/test_*.py`, `**/*_test.py`). Always-on for test paths. Triggered
by TDD-001.

## Standards

1. **Arrange-Act-Assert structure, separated by blank lines.** Each section should be
   visually distinct. Add comments when the arrangement is non-trivial:
   ```python
   def test_config_loader_missing_file_raises():
       # Arrange
       path = Path("/nonexistent/config.yaml")

       # Act / Assert
       with pytest.raises(ConfigError, match="not found"):
           load_config(path)
   ```

2. **One conceptual check per test.** Multiple `assert` statements are acceptable only when
   they verify different facets of the same outcome (e.g., status code AND response body).
   Never assert two independent behaviors in one test — split into two tests.

3. **Test isolation: no shared mutable state.** Fixtures that produce mutable objects
   (dicts, lists, file paths) must have `scope="function"` (the default) unless explicitly
   justified. Session-scoped fixtures must be read-only (e.g., `repo_root`, binary paths).

4. **Test through the public API.** Do not import and call private functions (`_internal`).
   If you cannot test a behavior through the public API, the design needs refactoring, not
   the test. Exception: pure internal utility functions with complex logic may be tested
   directly if isolated in their own module.

5. **No `time.sleep` in tests.** Sleeping makes test suites slow and flaky. Use mocking
   (`unittest.mock.patch`) or event-based synchronization. If a test requires real I/O
   timing, mark it `@pytest.mark.slow` and exclude from the default run.

6. **Assert messages explain the failure.** For non-obvious assertions, add a message:
   `assert result.exit_code == 0, f"Hook failed: {result.stderr}"`. This prevents
   "AssertionError" with no context in CI output.

## Cross-references

- ARMATURE.md §5 (testing phase)
- `test-naming.md` (naming conventions)
- `tdd-workflow.md` (Red-Green-Refactor cycle)
- Invariant: TDD-001
