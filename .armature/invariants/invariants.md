# Armature Invariants

This document is the human-readable companion to `.armature/invariants/registry.yaml`. It provides prose descriptions of every hard constraint in the system, grouped by category.

**This file is the canonical reference in degraded mode** (when no agentic tooling is active). For machine-readable enforcement data, see the registry.

---

## How to Read This Document

Each invariant has:
- **ID** — Unique identifier matching the registry (`{CATEGORY}-{NNN}`)
- **Severity** — critical / high / standard
- **Rule** — The invariant stated as an absolute constraint
- **Rationale** — Why this invariant exists
- **Enforcement** — How compliance is verified

---

## Specification Integrity

**SPEC-001 — Section Numbering Contiguity** (critical)
Rule: ARMATURE.md section numbering must be contiguous.
Rationale: Sections are referenced by number throughout the system — in persona files, commands, agents.md frontmatter, and this registry. A gap or duplicate in numbering creates ambiguous references.
Enforcement: Manual review, `post-stop.sh`.

**SPEC-002 — Internal Reference Resolution** (critical)
Rule: All internal section references in ARMATURE.md must resolve.
Rationale: Broken section references create governance ambiguity. An agent following a reference to a non-existent section has no guidance.
Enforcement: Manual review, `post-stop.sh`.

## Schema Conformance

**SCHEMA-001 — Config Schema Compliance** (high)
Rule: config.yaml must conform to the schema defined in ARMATURE.md section 8.1.
Rationale: config.yaml is parsed programmatically by the orchestrator during init and by tooling during validation. Schema drift breaks the toolchain.
Enforcement: `post-stop.sh` YAML validation, CI.

**SCHEMA-002 — Registry Schema Compliance** (high)
Rule: registry.yaml must conform to the schema defined in ARMATURE.md section 8.3.
Rationale: The invariant registry is the machine-readable source of truth for constraints. The reviewer parses it programmatically. Invalid YAML or missing fields break the review pipeline.
Enforcement: `post-stop.sh` YAML validation, CI.

## Referential Integrity

**REF-001 — Routing Table Resolution** (critical)
Rule: All agents.md paths referenced in CLAUDE.md routing table must exist as files.
Rationale: The orchestrator uses the routing table to determine which agents.md governs a scope. A broken reference means the orchestrator cannot find governance for a component, leading to ungoverned delegation.
Enforcement: `post-stop.sh` check #1, CI.

**REF-002 — ADR Reference Resolution** (high)
Rule: All ADR references in agents.md frontmatter must resolve to files in docs/adr/.
Rationale: ADR references in frontmatter tell agents which architectural decisions govern their scope. An orphan reference creates a false governance claim — the agent thinks a decision exists when it doesn't.
Enforcement: `post-stop.sh` check #4, CI.

**REF-003 — CODEX.md Routing Table Resolution** (critical)
Rule: All agents.md paths referenced in CODEX.md routing tables must exist as files.
Rationale: CODEX.md is a thin routing adapter over the same governance hierarchy. A broken path creates an ungoverned Codex execution path and defeats the adapter's purpose.
Enforcement: `post-stop.sh` routing check, CI.

## Tool Adapter Integrity

**ADAPTER-001 — Tool Adapter Consistency** (high)
Rule: Tool-specific adapter files must route to the same governance sources and must not redefine or contradict root/scoped governance, ADRs, or the invariant registry.
Rationale: Armature remains single-source-of-truth only if runtime-specific entrypoints stay thin. If `CLAUDE.md` or `CODEX.md` start carrying divergent rules, the framework splits into incompatible governance variants.
Enforcement: Manual review.

## Hook Enforcement

**HOOK-001 — Block Destructive Shell Commands** (high)
Rule: Agents must not execute destructive shell operations — specifically `rm -rf`, force push, hard reset, `DROP TABLE`, or `--no-verify` flag usage.
Rationale: Destructive commands are irreversible and bypass safety nets (hooks, confirmations, audit trails). An agent executing them without human authorization can cause unrecoverable data loss or silently corrupt governance state.
Enforcement: `block-dangerous-commands.sh` intercepts matching patterns at the pre-tool-use hook boundary and halts execution with an explanation.

**HOOK-002 — Block Agent-Initiated Governance Configuration Changes** (critical)
Rule: Agents must not modify governance configuration files (`.armature/config.yaml`, `registry.yaml`, hook scripts, or persona files) without explicit human authorization conveyed through the orchestrator.
Rationale: Governance configuration defines the rules agents operate under. An agent that can silently rewrite its own constraints can neutralize every other invariant in the system.
Enforcement: `block-config-changes.sh` intercepts write operations targeting governance paths and halts with a mandatory escalation to the orchestrator.

**HOOK-003 — Dirty Marker for Conditional Test Verification** (standard)
Rule: Any change to application code must set a dirty marker so that the post-stop hook can require test verification before the session closes.
Rationale: Skipping tests after code changes is a common silent failure mode. The dirty marker makes the obligation explicit and machine-enforceable rather than relying on agent recall.
Enforcement: `mark-dirty.sh` writes the marker on qualifying file writes; `post-stop.sh` checks for the marker and blocks session close if tests have not been run.

**HOOK-004 — Governance Context Injection at Subagent Spawn** (high)
Rule: Every subagent spawned by the orchestrator must receive injected governance context — invariants, current session state, and the scope it is operating in — before it begins work.
Rationale: Subagents are stateless at spawn. Without injected context they may act without awareness of active constraints, in-progress tasks, or which agents.md governs their scope, leading to ungoverned execution.
Enforcement: `inject-context.sh` runs at the pre-agent-use hook boundary and prepends the canonical context block to the subagent's system prompt.

**HOOK-005 — Session State Re-Injection After Context Compaction** (high)
Rule: After a context compaction event the orchestrator must re-inject current session state into the active agent before resuming work.
Rationale: Context compaction silently discards prior conversation, including task assignments, constraints communicated mid-session, and partial-completion state. Resuming without re-injection causes the agent to operate on a false or empty picture of progress.
Enforcement: `reinject-context.sh` detects compaction events and triggers automatic re-injection of `.armature/session/state.md` and the current task context.

**HOOK-006 — Required Reading Advisory Before Scope Edits** (standard)
Rule: Before an agent edits files within any governed scope it must have read the governing agents.md and all ADRs listed in that file's frontmatter.
Rationale: Agents that skip required reading may contradict architectural decisions, violate scope restrictions, or produce work that fails review for reasons that were explicitly documented. The advisory surfaces these obligations at the moment they are actionable.
Enforcement: `check-required-reading.sh` runs at the pre-tool-use hook boundary for write operations and warns — or blocks, depending on configuration — if the required documents have not been read in the current session.
