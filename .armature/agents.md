---
scope: ".armature"
governs: "Core specification, persona definitions, invariant registry, templates, and validation hooks"
inherits: "agents.md"
adrs: [ADR-0001, ADR-0002]
invariants: [SPEC-001, SPEC-002, SCHEMA-001, SCHEMA-002, REF-001, REF-002, REF-003, ADAPTER-001, HOOK-001, HOOK-002, HOOK-003, HOOK-004, HOOK-005, HOOK-006, HOOK-007, TDD-001, PHASE-001, TIER0-001, TASK-001, TASK-002, TASK-003, CI-001, HOTFIX-001, DISCIPLINE-001, DRIFT-001, DRIFT-002]
discipline-tags: [adr-process, definition-of-done]
enforced-by:
  - ".armature/hooks/post-stop.sh"
  - ".armature/hooks/block-dangerous-commands.sh"
  - ".armature/hooks/block-config-changes.sh"
  - ".armature/hooks/mark-dirty.sh"
  - ".armature/hooks/inject-context.sh"
  - ".armature/hooks/reinject-context.sh"
  - ".armature/hooks/check-required-reading.sh"
  - ".armature/hooks/tier0-preflight.sh"
  - ".armature/hooks/tdd-gate.sh"
  - ".armature/hooks/phase-gate.sh"
  - ".github/workflows/governance.yml"
  - ".armature/hooks/task-readiness.sh"
  - ".armature/hooks/task-completion.sh"
  - ".armature/hooks/auto-reviewer.sh"
  - ".armature/hooks/run-ci.sh"
  - ".armature/hooks/harness-feedback.sh"
  - ".armature/hooks/check-cascade.sh"
  - ".armature/hooks/precommit-cascade-gate.sh"
  - ".armature/hooks/cascade-ci.sh"
  - ".armature/hooks/pre-pr-create.sh"
persona: implementer
authority: [read, write, test]
restricted: [cross-cutting-changes]
test-scope: ".armature/tests/"
---

# Specification Scope

## Overview

This scope governs the Armature specification (ARMATURE.md), all persona definitions, the invariant registry and its human-readable companion, templates for project scaffolding, and the post-stop validation hook.

## Behavioral Directives

- **Must:** Maintain internal consistency within ARMATURE.md — section numbering, cross-references, schema definitions must all agree
- **Must:** Update invariants.md whenever registry.yaml changes
- **Must:** Update the schema section (section 8) whenever config.yaml or registry.yaml schema changes
- **Must:** Keep tool adapter artifacts thin — `CLAUDE.md`, `CODEX.md`, and related templates route to shared governance; they do not redefine it
- **Must not:** Modify persona files in ways that contradict the spec
- **Never:** Remove or renumber sections without updating all internal references

## Change Expectations

- Preserve all existing section numbers unless explicitly renumbering (requires full cross-reference audit)
- Preserve backward compatibility of config.yaml and registry.yaml schemas
- Preserve the separation between framework-generic and project-specific files
- Preserve the single-source-of-truth model across tool adapters

## Cross-Links

- **Parent directives:** agents.md
- **Governing ADRs:** ADR-0001 (governance as files), ADR-0002 (tool adapters and Codex support)
- **Related components:** `.claude/commands/agents.md`, `.claude/agents/agents.md`, `CODEX.md`
- **Invariants:** See `.armature/invariants/registry.yaml` for entries: SPEC-001, SPEC-002, SCHEMA-001, SCHEMA-002, REF-001, REF-002, REF-003, ADAPTER-001, HOOK-001 through HOOK-007
