---
id: code-review
severity: high
composition-mode: strict
---

# Code Review

## When to apply

Apply during the Review phase. Triggered by reviewer role assignment and the Implementation →
Review phase transition gate.

## Standards

1. **Review priority order: correctness > security > performance > style.** Find a logic
   error before commenting on variable names. A style comment on code with a security
   vulnerability is a distraction. Reviewers must complete correctness and security passes
   before moving to performance or style.

2. **Structured feedback format: issue → severity → suggested change.**
   Every finding must include all three:
   ```
   Line 47: `user_id` is taken from request body without ownership check.
   Severity: HIGH (security — broken access control, see OWASP A01).
   Suggestion: Verify `request.user.id == resource.owner_id` before proceeding.
   ```
   Findings without a suggested change are not actionable — provide one or explain why
   the fix requires design-level discussion.

3. **Reviewer verdict format: PASS / CONDITIONAL / FAIL with required-changes list.**
   - PASS: No blocking issues. Minor suggestions may be logged but are not required.
   - CONDITIONAL: Specific listed changes required before merge. List each change.
   - FAIL: Fundamental issues requiring redesign or significant rework. List root causes.
   The verdict is recorded in `.armature/reviews/{task-id}-review.md`.

4. **Cite line numbers for every finding.** A finding without a line number cannot be
   acted on efficiently. Format: `Line N:` or `Lines N-M:` at the start of the finding.

5. **Distinguish blocking from non-blocking comments.** Use prefixes:
   - `BLOCK:` — must be resolved before PASS
   - `SUGGEST:` — recommended but not required
   - `NIT:` — minor style, author's discretion
   Only BLOCK items count toward a CONDITIONAL or FAIL verdict.

## Cross-references

- ARMATURE.md §5.6 (Review phase definition)
- `definition-of-done.md` (DoD checklist that precedes reviewer invocation)
- `owasp-checklist.md` (security review checklist)
- Invariant: PHASE-001 (review phase gate)
