---
id: abstraction-rules
severity: standard
composition-mode: advisory
---

# Abstraction Rules

## When to apply

Apply to architecture and design decisions, particularly when introducing new base classes,
interfaces, mixins, or utility modules. Triggered by code review (see `code-review.md`).

## Standards

1. **No abstraction without at least 3 concrete uses (rule of three).** Before extracting a
   helper, base class, or interface, count the number of distinct call sites. Two similar
   blocks of code are a coincidence; three are a pattern. Example: extract `parse_yaml_file`
   only after the third distinct caller appears, not after the second.

2. **Naming reflects the abstraction level.** Layer-appropriate names:
   - `Repository` — storage abstraction (read/write, no business logic)
   - `Service` — orchestration (coordinates repositories, applies business rules)
   - `Handler` — request/event entry point (thin, delegates to Service)
   - `Adapter` — boundary translation (external protocol ↔ internal model)
   Mixing levels in a name (`RepositoryService`) signals a design smell.

3. **Prefer duplication until the pattern crystallizes (AHA over DRY).** "Avoid Hasty
   Abstractions" (AHA): early abstraction locks in the wrong shape. Let three real use cases
   exist before abstracting. Wrong abstractions cost more to unwind than duplicated code.

4. **Abstract over data shape, not behavior, by default.** A shared data structure
   (`ConfigEntry`, `HookResult`) is a safe abstraction at any point. A shared behavior
   (base class with overridable methods) requires the rule-of-three because behavior
   abstractions are harder to change.

5. **Abstractions must have tests independent of their implementations.** If you extract
   an interface, the interface's contract must be tested against at least one concrete
   implementation. Tests that only test the concrete class do not validate the abstraction.

## Cross-references

- ARMATURE.md §3 (agent behavioral rules)
- `layer-boundaries.md` (valid dependency directions between abstraction layers)
- `clean-code.md` (naming conventions)
- `typing.md` (TypeAlias rule-of-three)
