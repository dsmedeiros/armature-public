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
| ADAPTER-001 | Tool-specific adapter files must route to the same governance sources and must not redefine or contradict root/scoped governance, ADRs, or the invariant registry. | Manual review |
| REF-003 | All agents.md paths referenced in CODEX.md routing table must exist as files | `post-stop.sh`, CI |
| HOOK-001 | The block-dangerous-commands.sh hook must block destructive shell commands on PreToolUse(Bash) events. | `block-dangerous-commands.sh` |
| HOOK-002 | The block-config-changes.sh hook must block agent-initiated configuration changes on ConfigChange events. | `block-config-changes.sh` |
| HOOK-003 | Application code changes must be tracked for conditional test verification | `mark-dirty.sh`, `post-stop.sh` |
| HOOK-004 | Subagents must receive governance context at spawn time | `inject-context.sh` |
| HOOK-005 | Session state must be re-injected after context compaction | `reinject-context.sh` |
| HOOK-006 | Agents should be advised of required reading before editing governed files | `check-required-reading.sh` |
| HOOK-007 | gh pr create must be gated when a red-team trigger fired but no valid red-team marker exists | `pre-pr-create.sh` |
| TDD-001 | Source file edits require a matching test file to exist | `tdd-gate.sh` |
| PHASE-001 | Edits must be permitted by the current SDLC phase | `phase-gate.sh` |
| TIER0-001 | DOMAIN.md and PROJECT.md must exist at repo root | `tier0-preflight.sh` |
| TASK-001 | Tasks must have acceptance criteria before delegation | `task-readiness.sh` |
| TASK-002 | Deliverables must be auto-verified against acceptance criteria | `task-completion.sh` |
| TASK-003 | Reviewer and (when triggered) red team must auto-fire on SubagentStop | `auto-reviewer.sh` |
| CI-001 | Full CI pipeline (tests + types + lint + invariants) must run on Stop when code is dirty | `run-ci.sh` |
| HOTFIX-001 | Hotfix bypass must produce an audit record and block subsequent normal-phase work until postmortem lands | `hotfix-audit.sh` (planned M8) |
| DISCIPLINE-001 | Persona discipline tags declared in agents.md frontmatter must be defined in the standards corpus | orchestrator protocol (no script) |
| DRIFT-001 | Invariant-shaped tokens in governed markdown must resolve against the registry or match the universal allowlist | `post-stop.sh` |
| DRIFT-002 | Cascade rule companions must be co-staged with their trigger files (atomic landing of coupled artifacts) | `check-cascade.sh`, `precommit-cascade-gate.sh` |

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
