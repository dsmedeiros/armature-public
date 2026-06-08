---
id: tdd-workflow
severity: high
composition-mode: strict
---

# TDD Workflow

## When to apply

Apply during Implementation phase to all non-spike source code. Enforced by TDD-001.
Triggered by changes to `src/`, `lib/`, application code paths.

## Standards

1. **Red-Green-Refactor cycle — in this order, no exceptions.**
   - Red: Write a failing test that specifies the new behavior. Run pytest and confirm it
     fails with the expected failure message (not an import error or syntax error).
   - Green: Write the smallest code change that makes the test pass. Do not add behavior
     not yet covered by a test.
   - Refactor: With tests green, improve structure without changing behavior. Re-run tests
     after every refactoring step.

2. **No source code without a corresponding failing test first.** A commit that adds a
   function, class, or module without a prior or co-committed failing test violates TDD-001.
   The tdd-gate hook enforces this: if `.code-dirty` is set and no test file was modified
   in the same session, the gate emits a WARN.

3. **Coverage intent: cover behavior, not lines.** The goal is a test per behavior, not 100%
   line coverage. "Behavior" means: a distinct input scenario, a distinct error path, or a
   distinct state transition. A function with 3 behaviors needs 3 tests, even if one test
   achieves 90% line coverage.

4. **Spike code is explicitly marked.** Exploratory code written without tests must be in
   a branch or file prefixed `spike_` and must not be merged to `main`. Spike code is
   throw-away: if the approach is adopted, it is reimplemented test-first from the spike's
   findings. Never promote spike code to production by removing the prefix.

5. **Test file is the specification.** The test file for a module is the executable
   specification of that module's behavior. Test descriptions (via naming — see
   `test-naming.md`) must be readable as a behavior inventory without reading source code.
   Example: `test_config_loader_missing_key_returns_default` is a complete behavioral statement.

6. **Defer tests only for genuinely throw-away exploration.** Deferred tests are not
   "write later" — they are "this code will be deleted." If the code survives, tests are
   required before the next commit to `main`.

## Cross-references

- ARMATURE.md §5.6 (Implementation phase — tdd-strict trait)
- Invariant: TDD-001
- `test-naming.md` (test naming conventions)
- `testing-standards.md` (AAA structure, isolation rules)
