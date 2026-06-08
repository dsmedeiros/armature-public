---
id: definition-of-done
severity: high
composition-mode: strict
---

# Definition of Done

## When to apply

Apply before every Implementation → Review phase transition. Triggered by TASK-002.
The orchestrator must verify this checklist before invoking the reviewer.

## DoD Checklist

A task is done when ALL of the following are true:

1. **Tests passing.** `pytest` (or equivalent) exits 0 with no skipped tests that were
   previously passing. New behavior has new tests. Existing tests are not deleted to make
   the suite pass.

2. **Types clean.** No new `Any` type annotations introduced (see `typing.md`). `mypy` or
   `pyright` exits 0 on the changed modules. Existing type errors are not worsened.

3. **Docs updated for public-API changes.** Any function, class, or module added to or
   removed from the public API must have its docstring updated. If the project maintains
   separate API documentation, it is regenerated and the output is committed.

4. **Reviewer PASS recorded.** A review file exists at `.armature/reviews/{task-id}-review.md`
   with verdict `PASS` or `CONDITIONAL` with all BLOCK items resolved.

5. **Journal entry appended for governance changes.** If `.armature/` files were modified
   (hooks, invariants, personas, disciplines), a journal entry exists in `.armature/journal.md`
   describing what changed and why.

6. **No new TODOs without a tracking issue.** `TODO` comments added in this task must each
   cite a tracking issue: `# TODO(#123): remove after migration`. TODOs without issue
   references are merge blockers.

7. **`post-stop.sh` exits 0.** Run `bash .armature/hooks/post-stop.sh` from the repo root.
   Exit code 1 is a hard blocker — do not submit for review until resolved.

## Cross-references

- ARMATURE.md §5.6 (Implementation → Review phase transition condition)
- Invariant: TASK-002 (task completion criteria)
- `code-review.md` (reviewer verdict format)
- `typing.md` (no new Any rule)
