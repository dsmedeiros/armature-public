---
scope: ".claude/commands"
governs: "Operational protocol definitions for init, extend, update, backport, and checkpoint"
inherits: "agents.md"
adrs: [ADR-0001, ADR-0002]
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

These files are also the written protocol source for Codex and other environments without slash commands. In those tools, the agent executes the same workflow conversationally by reading these files directly.

## Behavioral Directives

- **Must:** Follow the YAML frontmatter convention (description field) for all command files
- **Must:** Reference ARMATURE.md section numbers when defining protocol steps
- **Must:** Describe runtime-specific behavior accurately when a protocol differs between Claude Code and Codex
- **Must not:** Duplicate normative content from ARMATURE.md — reference it instead
- **Never:** Define new governance concepts in commands that aren't in the spec

## Change Expectations

- Preserve the command naming convention: `armature-{verb}.md`
- Preserve YAML frontmatter structure (description, argument-hint fields)
- Preserve the step-by-step protocol structure within each command
- Preserve the distinction between Claude-specific command invocation and tool-agnostic protocol content

## Cross-Links

- **Parent directives:** agents.md
- **Governing ADRs:** ADR-0001 (governance as files), ADR-0002 (tool adapters and Codex support)
- **Related components:** `.armature/agents.md` (spec that commands implement), `CODEX.md` (Codex adapter that references these protocols)
- **Invariants:** See `.armature/invariants/registry.yaml` for entries: SPEC-002
