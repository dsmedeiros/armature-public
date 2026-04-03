---
scope: ".armature"
governs: "Core specification, persona definitions, invariant registry, templates, and validation hooks"
inherits: "agents.md"
adrs: [ADR-0001]
invariants: [SPEC-001, SPEC-002, SCHEMA-001, SCHEMA-002, REF-001, REF-002, HOOK-001, HOOK-002, HOOK-003, HOOK-004, HOOK-005, HOOK-006]
enforced-by:
  - ".armature/hooks/post-stop.sh"
  - ".armature/hooks/block-dangerous-commands.sh"
  - ".armature/hooks/block-config-changes.sh"
  - ".armature/hooks/mark-dirty.sh"
  - ".armature/hooks/inject-context.sh"
  - ".armature/hooks/reinject-context.sh"
  - ".armature/hooks/check-required-reading.sh"
  - ".github/workflows/governance.yml"
persona: implementer
authority: [read, write, test]
restricted: [cross-cutting-changes]
test-scope: "none"
---

# Specification Scope

## Overview

This scope governs the Armature specification (ARMATURE.md), all persona definitions, the invariant registry and its human-readable companion, templates for project scaffolding, and the post-stop validation hook.

## Behavioral Directives

- **Must:** Maintain internal consistency within ARMATURE.md — section numbering, cross-references, schema definitions must all agree
- **Must:** Update invariants.md whenever registry.yaml changes
- **Must:** Update the schema section (section 8) whenever config.yaml or registry.yaml schema changes
- **Must not:** Modify persona files in ways that contradict the spec
- **Never:** Remove or renumber sections without updating all internal references

## Change Expectations

- Preserve all existing section numbers unless explicitly renumbering (requires full cross-reference audit)
- Preserve backward compatibility of config.yaml and registry.yaml schemas
- Preserve the separation between framework-generic and project-specific files

## Cross-Links

- **Parent directives:** agents.md
- **Governing ADRs:** ADR-0001 (governance as files)
- **Related components:** `.claude/commands/agents.md`, `.claude/agents/agents.md`
- **Invariants:** See `.armature/invariants/registry.yaml` for entries: SPEC-001, SPEC-002, SCHEMA-001, SCHEMA-002, HOOK-001 through HOOK-006
