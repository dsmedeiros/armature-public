---
scope: ".claude/commands"
governs: "Operational protocol definitions for init, extend, update, backport, and checkpoint"
inherits: "agents.md"
adrs: [ADR-0001]
invariants: [SPEC-002]
enforced-by:
  - ".armature/hooks/post-stop.sh"
persona: implementer
authority: [read, write, test]
restricted: [cross-cutting-changes]
test-scope: "none"
---

# Commands Scope

## Overview

This scope governs the Claude Code slash commands that implement Armature operational protocols: `/armature-init`, `/armature-extend`, `/armature-update`, `/armature-backport`, and `/checkpoint`.

## Behavioral Directives

- **Must:** Follow the YAML frontmatter convention (description field) for all command files
- **Must:** Reference ARMATURE.md section numbers when defining protocol steps
- **Must not:** Duplicate normative content from ARMATURE.md — reference it instead
- **Never:** Define new governance concepts in commands that aren't in the spec

## Change Expectations

- Preserve the command naming convention: `armature-{verb}.md`
- Preserve YAML frontmatter structure (description, argument-hint fields)
- Preserve the step-by-step protocol structure within each command

## Cross-Links

- **Parent directives:** agents.md
- **Governing ADRs:** ADR-0001 (governance as files)
- **Related components:** `.armature/agents.md` (spec that commands implement)
- **Invariants:** See `.armature/invariants/registry.yaml` for entries: SPEC-002
