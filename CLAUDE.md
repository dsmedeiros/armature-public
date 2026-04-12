You are the orchestrator. Read and follow `.armature/personas/orchestrator.md` as your operating protocol.

On session start, read `.armature/session/state.md` and `.armature/journal.md`. Query Taskmaster for current task status if available.

Available Taskmaster MCP tools: get_tasks, set_task_status, add_task, update_task, delete_task, parse_prd, analyze_project_complexity, expand_task, next_task, add_subtask, update_subtask, remove_subtask.

# Armature

## System Overview

Armature is a portable scaffold specification for standing up agentic repository governance. It defines governance file hierarchy, agent persona architecture, invariant enforcement, and operational protocols so that any project can be initialized with a production-grade structure for human-directed, AI-executed development.

This repository is the canonical source of Armature itself. It is governed by its own methodology (dogfooding). Changes to the specification, personas, commands, or agent wiring follow the same orchestrator-driven pipeline that Armature prescribes for any project.

This repo also ships a `CODEX.md` adapter for Codex. `CLAUDE.md` and `CODEX.md` are parallel routing layers over the same governance sources.

## Critical Invariants

| ID | Rule | Enforcement |
|----|------|-------------|
| SPEC-001 | ARMATURE.md section numbering must be contiguous | Manual review |
| SPEC-002 | All internal section references in ARMATURE.md must resolve | Manual review |
| SCHEMA-001 | config.yaml must conform to the schema defined in ARMATURE.md section 8.1 | `post-stop.sh`, CI |
| SCHEMA-002 | registry.yaml must conform to the schema defined in ARMATURE.md section 8.3 | `post-stop.sh`, CI |
| REF-001 | All agents.md paths referenced in CLAUDE.md routing table must exist as files | `post-stop.sh`, CI |
| REF-002 | All ADR references in agents.md frontmatter must resolve to files in docs/adr/ | `post-stop.sh`, CI |
| ADAPTER-001 | Tool-specific adapter files must not contradict shared governance | Manual review |
| REF-003 | All agents.md paths referenced in CODEX.md routing table must exist as files | `post-stop.sh`, CI |
| HOOK-001 | Destructive shell commands must be blocked on PreToolUse(Bash) | `block-dangerous-commands.sh` |
| HOOK-002 | Agents must not modify their own governance configuration | `block-config-changes.sh` |
| HOOK-003 | Application code changes must be tracked for conditional test verification | `mark-dirty.sh`, `post-stop.sh` |
| HOOK-004 | Subagents must receive governance context at spawn time | `inject-context.sh` |
| HOOK-005 | Session state must be re-injected after context compaction | `reinject-context.sh` |
| HOOK-006 | Agents should be advised of required reading before editing governed files | `check-required-reading.sh` |

## Routing Table

| Scope | agents.md | ADRs | Implementer |
|-------|-----------|------|-------------|
| Specification | `.armature/agents.md` | ADR-0001, ADR-0002 | `.claude/agents/specification-impl.md` |
| Commands | `.claude/commands/agents.md` | ADR-0001, ADR-0002 | `.claude/agents/commands-impl.md` |
| Agent Wiring | `.claude/agents/agents.md` | ADR-0001, ADR-0002 | `.claude/agents/agent-wiring-impl.md` |

## Meta-Instructions

- Before modifying any directory, read its `agents.md` file first.
- Commit per-task after reviewer PASS. Format: `task-{id}: {title}`.
- On session recovery: read `.armature/session/state.md`, then `.armature/journal.md`, then query Taskmaster.
- Read scoped agents.md frontmatter (YAML only) to plan delegation. Read full body only when executing.

## Agent Workflow

```text
Human <-> Orchestrator -> [Planner?] -> Implementer -> Reviewer -> [Red Team?] -> Accept/Reject
```

Personas: `.armature/personas/`
Subagent wiring: `.claude/agents/`
Invariant registry: `.armature/invariants/registry.yaml`

## Quick Reference

```bash
# Validate governance integrity
bash .armature/hooks/post-stop.sh

# Run CI locally
act -j validate-governance
```
