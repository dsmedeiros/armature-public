---
scope: ".claude/agents"
governs: "Claude Code subagent wiring files for reviewer, planner, red team, and implementers"
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

# Agent Wiring Scope

## Overview

This scope governs the Claude Code subagent wiring files that connect Claude Code's Agent tool to Armature persona definitions. Core agent wiring (reviewer, planner, red team) uses thin pointers to `.armature/personas/`. Implementer wiring files reference component-specific personas.

## Behavioral Directives

- **Must:** Keep core agent wiring files (reviewer.md, planner.md, reviewer-redteam.md) as thin pointers — frontmatter + single pointer line
- **Must:** Preserve exact YAML frontmatter (name, description, tools, model) for Claude Code compatibility
- **Must not:** Duplicate persona content in wiring files — point to `.armature/personas/` instead
- **Never:** Create an orchestrator wiring file (the orchestrator is the main agent, not a subagent)

## Change Expectations

- Preserve the thin pointer pattern for core agents
- Preserve the frontmatter schema (name, description, tools, model fields)
- Preserve the naming convention: `{component}-impl.md` for implementers

## Cross-Links

- **Parent directives:** agents.md
- **Governing ADRs:** ADR-0001 (governance as files)
- **Related components:** `.armature/agents.md` (persona definitions these files point to)
- **Invariants:** See `.armature/invariants/registry.yaml` for entries: SPEC-002
