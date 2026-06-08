---
id: layer-boundaries
severity: high
composition-mode: strict
---

# Layer Boundaries

## When to apply

Apply whenever adding imports between modules, creating new directories, or restructuring
package layout. Triggered by changes to `src/`, `lib/`, `domain/`, or `infrastructure/`.

## Standards

1. **Dependency direction: domain → infrastructure, never infrastructure → domain.**
   The domain layer (business logic, entities, use-case interfaces) must not import from
   the infrastructure layer (database adapters, HTTP clients, file systems). Dependencies
   point inward. Infrastructure imports domain, not the reverse.

2. **Forbidden imports are structural violations, not style issues.**
   Example forbidden import (Python):
   ```python
   # In src/domain/order.py — FORBIDDEN
   from src.infrastructure.postgres import connection  # domain must not know postgres exists
   ```
   Example correct pattern: domain defines an interface; infrastructure provides the impl.

3. **Layer crossings via interfaces only.** The domain defines abstract interfaces
   (`OrderRepository`, `EmailService`). Infrastructure provides concrete implementations.
   The dependency injection wiring happens at the application boundary, not inside either layer.

4. **Layer = file directory boundary by convention.** Directory layout is the enforcement
   mechanism. Each top-level package under `src/` defines a layer:
   - `src/domain/` — entities, value objects, use-case interfaces
   - `src/application/` — use-case orchestration, command/query handlers
   - `src/infrastructure/` — adapters (DB, HTTP, filesystem, LLM)
   - `src/api/` — entry points (HTTP handlers, CLI commands)

5. **Detect violations with import-linter or equivalent.** Add import contracts to
   `.importlinter` or equivalent config. CI must fail if a forbidden import is added.
   Manual review is insufficient at scale.

6. **Cross-layer data transfer uses DTOs, not domain objects.** API layer receives a
   request DTO, passes a command to the application layer; application layer returns a
   response DTO. Domain objects do not escape to the API layer.

## Cross-references

- ARMATURE.md §3 (agent behavioral rules)
- `abstraction-rules.md` (naming conventions for layer-appropriate abstractions)
- `adr-process.md` (architectural decisions about layer structure require an ADR)
