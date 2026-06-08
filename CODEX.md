You are the orchestrator for this repository. Read and follow `.armature/personas/orchestrator.md` as the workflow model, adapting execution to Codex capabilities.

On session start, read `.armature/session/state.md` and `.armature/journal.md`. If Taskmaster tools are unavailable, track tasks in `.armature/session/state.md` or an equivalent local plan.

> **Setup Prerequisite:** Codex does not auto-discover `CODEX.md`. Add it to your
> `.codex/config.toml` so Codex reads this file on session start:
>
> ```toml
> project_doc_fallback_filenames = ["CODEX.md"]
> ```
>
> Without this setting, Codex will only read `AGENTS.md` and `AGENTS.override.md`.

# Armature

## System Overview

Armature is a portable scaffold specification for standing up agentic repository governance. It defines governance file hierarchy, agent persona architecture, invariant enforcement, and operational protocols so that any project can be initialized with a production-grade structure for human-directed, AI-executed development.

This repository is the canonical source of Armature itself. It is governed by its own methodology. `CODEX.md` is the Codex adapter for that methodology; `CLAUDE.md` remains the Claude-specific sibling adapter. Both route to the same governance sources.

## Codex Adapter Rules

- Treat root/scoped `agents.md`, ADRs, `.armature/invariants/registry.yaml`, and persona files as authoritative.
- Treat `.claude/commands/*.md` as written protocols to execute conversationally; they are not slash commands in Codex.
- Use Codex-native sandbox and approval controls where Claude Code would rely on lifecycle hooks. Codex also has an experimental `hooks.json` system (`.codex/hooks.json`) that supports `PreToolUse`, `PostToolUse`, `SessionStart`, and `Stop` events. When available, wire Armature hook scripts via `.codex/hooks.json` (see `.armature/templates/codex-hooks.json.tmpl`); otherwise run `bash .armature/hooks/post-stop.sh` manually before reporting completion.
- Use planner, reviewer, and red-team personas as distinct phases. Codex supports parallel subagent spawning when the user explicitly requests it (e.g., "spawn two agents for these scopes"); use this for independent implementer tasks across different scopes. When parallel spawning is not requested or not practical, execute phases sequentially. Authority boundaries apply regardless of execution mode.

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

| Scope | `agents.md` | ADRs | Implementer Persona |
|-------|-------------|------|---------------------|
| Specification | `.armature/agents.md` | ADR-0001, ADR-0002 | `.armature/personas/implementers/specification.md` |
| Commands | `.claude/commands/agents.md` | ADR-0001, ADR-0002 | `.armature/personas/implementers/commands.md` |
| Agent Wiring | `.claude/agents/agents.md` | ADR-0001, ADR-0002 | `.armature/personas/implementers/agent-wiring.md` |

## Meta-Instructions

- Before modifying any directory, read its `agents.md` file first.
- Read scoped `agents.md` frontmatter to plan work; read the full body before execution.
- Preserve the same authority boundaries regardless of whether phases run as parallel subagents or sequentially.
- Treat `CLAUDE.md` as the Claude-specific sibling adapter, not as the Codex runtime contract.

## Workflow

```text
Human <-> Codex Orchestrator -> [Planner Role?] -> Implementer Role -> Reviewer Role -> [Red Team Role?] -> Accept/Reject
```

Personas: `.armature/personas/`
Invariant registry: `.armature/invariants/registry.yaml`

## Quick Reference

```bash
# Validate governance integrity
bash .armature/hooks/post-stop.sh

# Run CI locally
act -j validate-governance
```
