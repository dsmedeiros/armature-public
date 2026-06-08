---
id: adr-process
severity: high
composition-mode: strict
---

# ADR Process

## When to apply

Apply when making persistent architectural choices, selecting technologies, or introducing
cross-cutting design decisions. Required before implementation begins (see PHASE-001).
Triggered by changes to `docs/adr/`, or explicit `discipline-tags: [adr-process]`.

## Standards

1. **ADRs are required for these decision categories:**
   - Persistent architectural choices (e.g., "we use event sourcing")
   - Technology selections (e.g., choosing a database, message broker, or LLM provider)
   - Cross-cutting design decisions affecting ≥2 scopes (e.g., authentication strategy)
   - Decisions that would be expensive to reverse without this record

2. **Required ADR sections (in order):**
   ```markdown
   ## Status
   ## Context
   ## Decision
   ## Consequences
   ```
   Status must be one of: `Proposed`, `Accepted`, `Deprecated`, `Superseded by ADR-NNNN`.

3. **ADR filename convention:** `NNNN-short-slug.md` where NNNN is zero-padded to 4 digits,
   sequential from 0001. Example: `docs/adr/0003-use-yaml-for-config.md`.

4. **Status lifecycle — never delete an ADR.** When a decision changes:
   - Mark the old ADR `Superseded by ADR-NNNN`.
   - Create a new ADR with status `Accepted` that references the superseded one in Context.
   - Deprecated ADRs are decisions no longer applicable (feature removed, not replaced).

5. **Cross-reference: every ADR-influenced invariant cites the ADR.** In
   `.armature/invariants/registry.yaml`, the `adrs:` field on each invariant must include
   every ADR whose decision motivated that invariant. This satisfies invariant REF-002.

6. **ADR scope — Context section must name what triggered the decision.** A vague context
   ("we wanted a better approach") is a review failure. Context must cite a specific problem,
   constraint, or event: "The existing flat-file config caused merge conflicts when teams
   worked in parallel on separate features (observed in sprint 4)."

## Cross-references

- ARMATURE.md §4 (ADR governance)
- Invariant: REF-002 (ADR references in agents.md frontmatter must resolve)
- `docs/adr/0001-governance-as-files.md`, `docs/adr/0002-tool-adapters.md`
