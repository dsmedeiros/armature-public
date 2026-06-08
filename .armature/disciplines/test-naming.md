---
id: test-naming
severity: standard
composition-mode: advisory
---

# Test Naming

## When to apply

Apply to test files (`**/test_*.py`, `**/*_test.py`). Triggered by TDD-001 and test-path
changes.

## Standards

1. **Test function names follow `test_{what}_{condition}_{expected}`.** All three segments
   are required when the condition is non-trivial. Examples:
   ```
   test_parser_empty_input_raises_value_error
   test_config_loader_missing_key_returns_default
   test_schema_validator_valid_document_passes
   ```
   One-clause test names (`test_parse`) are only acceptable for trivial smoke tests.

2. **Fixture names are nouns describing the produced thing, not the action.**
   Name the object, not the setup procedure:
   - Good: `mock_database`, `valid_config`, `temp_repo`, `authenticated_user`
   - Bad: `setup_database`, `create_config`, `initialize_repo`, `login_user`

3. **Parametrize labels via `ids=` when parameters are non-obvious.** Default pytest IDs
   for complex objects are unreadable. Provide explicit string labels:
   ```python
   @pytest.mark.parametrize("value,expected", [
       (0, False), (1, True), (-1, False),
   ], ids=["zero", "one", "negative"])
   ```

4. **Test class names (if used) follow `Test{SystemUnderTest}`.** Class grouping is
   appropriate when testing a single class with many scenarios: `TestConfigLoader`,
   `TestSchemaValidator`. Do not use classes just for namespace separation — use modules.

5. **No `test_1`, `test_a`, or numbered sequences.** Every test name must be descriptive
   enough that a failing test name in CI output identifies the failure without reading the
   body. Numbers indicate the author did not think about what is being tested.

## Cross-references

- ARMATURE.md §5 (SDLC phases — testing phase)
- `testing-standards.md` (Arrange-Act-Assert, one-assertion rule)
- `tdd-workflow.md` (TDD-001 invariant)
- Invariant: TDD-001
