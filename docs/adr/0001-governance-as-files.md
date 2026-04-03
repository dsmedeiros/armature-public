# ADR-0001: Governance as Files

**Status:** Accepted
**Date:** 2026-04-01
**Supersedes:** N/A

## Context

AI coding agents are primary contributors to modern software projects. They need explicit, machine-readable governance to operate within safe boundaries. Conversational context is ephemeral — it doesn't survive compaction, session restarts, or context window limits. A governance system that depends on conversation is fundamentally fragile.

## Decision

Governance rules are encoded as files at the locations they govern, using a cascading hierarchy of agents.md files with structured YAML frontmatter. The specification (ARMATURE.md) is the single source of truth. Persona files define agent authority boundaries. An invariant registry provides machine-readable constraint enforcement. All governance files are committed to version control.

## Consequences

- Governance survives compaction, restarts, and context window limits
- Rules are auditable through git history
- Progressive disclosure — agents read only what their scope requires
- The methodology is portable across projects and tools
- Every governance file doubles as human-readable documentation when no agent is active

## Invariants

- **SPEC-001:** ARMATURE.md section numbering must be contiguous — sections are referenced by number across the system
- **SPEC-002:** All internal section references in ARMATURE.md must resolve — broken references create governance ambiguity
- **SCHEMA-001:** config.yaml must conform to the schema defined in ARMATURE.md section 8.1 — schema drift breaks tooling
- **SCHEMA-002:** registry.yaml must conform to the schema defined in ARMATURE.md section 8.3 — registry is machine-parsed
- **REF-001:** All agents.md paths referenced in CLAUDE.md routing table must exist — broken routes prevent delegation
- **REF-002:** All ADR references in agents.md frontmatter must resolve to files in docs/adr/ — orphan references create false governance claims

## Supersedes Invariants

None.

## Non-Goals

- Multi-user concurrent governance (deferred per YAGNI)
- Automated migration between Armature versions (manual via /armature-backport)
- Visual tooling for governance exploration

## Observability

- `post-stop.sh` hook validates referential integrity on every session stop
- GitHub Actions CI runs the same validation on every push and PR
- Reviewer persona validates invariant compliance on every changeset

## Security Considerations

No additional security considerations beyond existing baseline. Governance files are committed to version control with the same access controls as application code.

## Acceptance Criteria

- [ ] CLAUDE.md routing table covers all component scopes
- [ ] All agents.md frontmatter ADR references resolve
- [ ] All agents.md frontmatter invariant IDs exist in the registry
- [ ] post-stop.sh passes with exit code 0
- [ ] CI workflow runs and passes on push to main
