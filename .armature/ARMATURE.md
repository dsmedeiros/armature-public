# Armature — Agentic Repository Management Architecture

**Version:** 1.1.0
**Status:** Active
**Author:** Dave Medeiros / Panoptic Systems

---

## 1. Purpose

Armature is a portable scaffold specification for standing up agentic repository governance. It defines the complete system — governance file hierarchy, agent persona architecture, invariant enforcement, and operational protocols — so that any new project can be initialized with a production-grade structure for human-directed, AI-executed development.

The methodology assumes AI coding agents are primary contributors. Every design choice optimizes for a world where agents must be steered with precision, constrained by explicit authority boundaries, and held accountable through auditable enforcement mechanisms.

Armature is not a framework or a library. It is a structural methodology encoded as files, conventions, and protocols. It degrades gracefully to human-readable documentation when agentic tooling is not active.

---

## 2. Design Principles

**P1 — Governance as Structure, Not Convention.**
Rules are encoded in files at the locations they govern. An agent working in `src/ledger/` reads `src/ledger/agents.md` — it does not rely on remembering a conversation or a monolithic config.

**P2 — Progressive Disclosure.**
An agent reads only what its current scope requires at the detail level it needs. The orchestrator reads frontmatter to plan. Implementers read their local scope to execute. The reviewer reads the registry to verify. Nobody reads everything. This preserves context for the work that matters.

**P3 — Authority Boundaries Over Skill Gradients.**
Agent personas are defined by what they can decide, not how smart they are. The orchestrator plans. Implementers execute within scope. The reviewer enforces invariants. Nobody has unchecked authority.

**P4 — Externalized Working Memory.**
Session state, review verdicts, escalation packages, and the governance journal live on disk, not in conversation context. The agentic workflow survives compaction, restarts, and context window limits.

**P5 — Defense in Depth.**
Critical invariants are stated in governance files, enforced by CI tests, validated by the reviewer persona, and checked by mechanical hooks. No single layer is trusted alone. Behavioral enforcement (persona directives) is the primary layer; mechanical enforcement (hooks, CI) is the backstop. Hooks can prevent a bad write, but they cannot reclaim the context spent reasoning about it.

**P6 — Inside/Outside Separation.**
The orchestrator sees the outside: topology, task graph, verdicts, governance. Implementers see the inside: code, tests, local constraints. The reviewer sees both through a compliance lens. These boundaries are never crossed. The orchestrator does not read source code. Implementers do not read peer scopes.

**P7 — Machine-Readable Governance.**
AGENTS.md frontmatter, the invariant registry, and session state files use structured formats. Agents parse them programmatically rather than extracting meaning from prose.

**P8 — Degraded Mode as Documentation.**
Every governance file is human-readable. When no agentic workflow is active, the scaffold serves as project documentation. No mechanism depends exclusively on agent tooling.

**P9 — YAGNI.**
The scaffold supports a single developer directing an agentic workflow. Multi-user, multi-session, and commercial distribution concerns are deferred until they are real.

---

## 3. Governance Layer

### 3.1 File Hierarchy

```
project-root/
├── CLAUDE.md                              ← Claude Code entry point / lean router
├── CODEX.md                               ← Codex entry point / lean router
├── agents.md                              ← Root governance directives (cross-tool)
├── .armature/
│   ├── ARMATURE.md                        ← This specification
│   ├── agents.md                          ← Scoped governance directives for .armature/
│   ├── config.yaml                        ← Project metadata and topology
│   ├── .gitignore                         ← Gitignore for ephemeral session artefacts
│   ├── personas/
│   │   ├── orchestrator.md                ← Orchestrator persona
│   │   ├── reviewer.md                    ← Reviewer persona (compliance)
│   │   ├── reviewer-redteam.md            ← Red team reviewer persona (adversarial)
│   │   ├── planner.md                     ← Opt-in planner persona
│   │   └── implementers/
│   │       └── {component}.md             ← Per-component implementer personas
│   ├── invariants/
│   │   ├── registry.yaml                  ← Machine-readable invariant index
│   │   └── invariants.md                  ← Human-readable constraint list
│   ├── templates/
│   │   ├── agents.md.tmpl                 ← AGENTS.md skeleton
│   │   ├── adr.md.tmpl                    ← ADR template
│   │   ├── CODEX.md.tmpl                  ← Codex adapter template
│   │   ├── persona.md.tmpl               ← Implementer persona template
│   │   ├── settings-hooks.json.tmpl       ← Claude Code hook wiring template
│   │   └── codex-hooks.json.tmpl          ← Codex hook wiring template (experimental)
│   ├── journal.md                         ← Governance journal (committed, append-only)
│   ├── session/
│   │   ├── state.md                       ← Living session state
│   │   └── logs/                          ← Completed session logs
│   ├── reviews/                           ← Reviewer verdict artifacts
│   ├── escalations/                       ← Circuit breaker handoff packages
│   └── hooks/
│       ├── post-stop.sh                   ← On-stop governance validation + conditional test runner
│       ├── block-dangerous-commands.sh    ← PreToolUse(Bash) destructive command guard
│       ├── block-config-changes.sh        ← ConfigChange self-governance prevention
│       ├── mark-dirty.sh                  ← PostToolUse(Edit|Write) code change tracker
│       ├── inject-context.sh              ← SubagentStart governance context injection
│       ├── reinject-context.sh            ← SessionStart(compact) post-compaction recovery
│       └── check-required-reading.sh      ← PreToolUse(Edit|Write) required reading advisory
├── .claude/
│   ├── agents/
│   │   ├── agents.md                      ← Scoped governance directives for .claude/agents/
│   │   ├── reviewer.md                    ← Claude Code subagent → .armature/personas/reviewer.md
│   │   ├── reviewer-redteam.md            ← Claude Code subagent → .armature/personas/reviewer-redteam.md
│   │   ├── planner.md                     ← Claude Code subagent → .armature/personas/planner.md
│   │   └── {component}-impl.md            ← Claude Code subagent → .armature/personas/implementers/{component}.md
│   └── commands/
│       ├── agents.md                      ← Scoped governance directives for .claude/commands/
│       ├── armature-init.md               ← Instantiation protocol
│       ├── armature-extend.md             ← Component onboarding
│       ├── armature-update.md              ← Specification update protocol
│       ├── armature-backport.md            ← Framework upgrade from canonical source
│       └── checkpoint.md                  ← Pre-compaction state save
├── docs/
│   └── adr/                               ← Architecture decision records
└── {project source tree}/
    ├── agents.md                          ← Scoped directives per directory
    └── ...
```

### 3.2 What Gets Committed vs. Gitignored

**Committed:**
- `CLAUDE.md`, `CODEX.md`, root `agents.md`
- `.armature/ARMATURE.md`, `config.yaml`
- `.armature/personas/` (all persona files)
- `.armature/invariants/` (registry and invariants.md)
- `.armature/templates/`
- `.armature/hooks/`
- `.armature/journal.md` (governance journal — append-only institutional memory)
- `.armature/reviews/` (reviewer verdict artifacts — audit trail)
- `.claude/agents/` (reviewer, planner, implementer subagents — not orchestrator)
- `.claude/commands/`
- `docs/adr/`
- All scoped `agents.md` files in the source tree
- `.taskmaster/tasks/` and `.taskmaster/config.json` (Taskmaster persistence)

**Gitignored:**
- `.armature/session/` (ephemeral working state)
- `.armature/escalations/` (ephemeral escalation packages)

### 3.3 CLAUDE.md — Orchestrator Entry Point and Lean Router

CLAUDE.md serves a dual role: it is the Claude Code entry point that survives compaction, and it establishes the main agent as the orchestrator by directive.

**The first lines of CLAUDE.md must:**
1. Direct the main agent to operate as the orchestrator: "You are the orchestrator. Read and follow `.armature/personas/orchestrator.md` as your operating protocol."
2. Instruct session recovery: "On session start, read `.armature/session/state.md` and `.armature/journal.md`. Query Taskmaster for current task status."
3. Explicitly list available Taskmaster MCP tools by name, ensuring tool access is scoped rather than inherited carte blanche.

**The remainder of CLAUDE.md serves as the lean router (constrained to ~200 lines):**

1. **System overview** — What this project is, in 2–3 paragraphs.
2. **Critical invariants** — The top 5–10 hardest constraints, pulled from the invariant registry.
3. **Routing table** — A map from task type to which files to read.
4. **Meta-instruction** — Directive to read scoped `agents.md` files before modifying directories. Commit protocol summary. Journal recovery directive.
5. **Agent workflow topology** — Brief description of the pipeline and personas with pointers to `.armature/personas/`.
6. **Quick reference** — Build, test, deploy commands.

**Why the orchestrator is the main agent, not a subagent:**
If the orchestrator were a subagent, the main agent would need to know to spawn it for every interaction — an unreliable routing step. More critically, subagents spawning subagents creates a three-level nesting problem where context gets summarized at each return boundary. With the orchestrator as the main agent, implementers, reviewers, and planners are one level deep — clean context boundaries, reliable delegation.

**CLAUDE.md must not:**
- Aggregate or summarize the contents of scoped `agents.md` files
- Duplicate ADR content
- Exceed ~200 lines (excluding the orchestrator directives at the top)
- Contain implementation details

CLAUDE.md fully survives compaction. After `/compact`, Claude Code re-reads it from disk. This is why it serves as both the orchestrator's identity anchor and the routing layer — it is the one document guaranteed to persist.

### 3.4 Root agents.md — Cross-Tool Governance

Projects may also ship a sibling `CODEX.md` adapter for Codex. `CODEX.md` is not a second source of truth; it is a runtime-specific routing layer over the same governance sources. It should point Codex at shared `agents.md` files, ADRs, the invariant registry, and persona files, while describing Codex-accurate equivalents for Claude-only mechanics such as slash commands, lifecycle hooks, and subagent wiring.

Note: Codex does not auto-discover `CODEX.md`. Projects using Codex must set `project_doc_fallback_filenames = ["CODEX.md"]` in `.codex/config.toml` so that Codex reads this adapter file on session start.

Root `agents.md` holds global directives applicable to any AI coding tool (Claude Code, Codex, future tooling). It defines:

- Repository-wide coding standards
- Cross-cutting architectural invariants
- ADR governance protocol (review ADRs before implementation)
- Testing expectations
- Documentation requirements
- Package management rules
- PR/commit conventions

Root `agents.md` does not reference Claude Code-specific features, personas, or Armature internals. It is tool-agnostic. Tool adapters such as `CLAUDE.md` and `CODEX.md` derive from it; they must not contradict it.

### 3.5 Scoped agents.md — The Cascading Hierarchy

**Filename casing:** The governance filename may be either `agents.md` or `AGENTS.md`. Projects choose one convention and use it consistently. All Armature tooling, hooks, and CI must match case-insensitively. This specification uses `agents.md` in examples; uppercase `AGENTS.md` is equally valid.

Each major component directory contains its own `agents.md` (or `AGENTS.md`) using a consistent structure with machine-readable YAML frontmatter.

**Frontmatter Schema:**

```yaml
---
scope: src/ledger                          # Directory path this file governs
governs: "Brief description of responsibility"
inherits: src/agents.md                    # Parent agents.md (explicit chain)
adrs: [ADR-0002, ADR-0006]                # Governing ADRs for this scope
invariants: [SEQ-001, DIGEST-002]          # Invariant IDs from the registry
enforced-by:                               # CI/runtime enforcement for this scope
  - tests/ledger_sequence_test.go
  - src/ledger/failfast.go
persona: implementer                       # Agent persona type for this scope
authority: [read, write, test]             # Permitted actions
restricted: [cross-cutting-changes, schema-migration]  # Prohibited actions
test-scope: unit                              # Test boundary: unit | integration | e2e | none
---
```

**Body Structure (4 sections):**

1. **Overview** — What this component does, in 2–3 sentences.
2. **Behavioral Directives** — Non-negotiable rules for this scope. Use imperative language: "must," "must not," "always," "never."
3. **Change Expectations** — What must not change when modifying this component. Preservation rules.
4. **Cross-Links** — References to related ADRs, invariants, and other `agents.md` files.

**Test scope convention:**
Test files are considered part of the scope of the code they test, even if they reside in a separate directory tree (e.g., `tests/integration/ledger_test.go` is in-scope for the `src/ledger/` component). The `test-scope` frontmatter field declares the expected test boundary. The reviewer uses this to determine whether test file modifications outside the component directory are in-scope or out-of-scope.

**Inheritance Model:**

Scoped files inherit from their declared parent. The resolution order when an agent works in `src/ledger/`:

1. Read `CLAUDE.md` (always loaded)
2. Read root `agents.md` (global directives)
3. Read `src/agents.md` (source-level directives)
4. Read `src/ledger/agents.md` (component-level directives)

More specific files take precedence on implementation details. Invariants propagate downward unconditionally — a leaf `agents.md` can add constraints but cannot relax them. See §7.4 Conflict Resolution.

### 3.6 Architecture Decision Records (ADRs)

ADRs live in `docs/adr/` and function as behavioral specifications, not historical decision logs. Each ADR defines what was decided and the invariants that decision implies.

**Required ADR Sections:**

- Context — Why this decision was needed
- Decision — What was decided
- Consequences — What follows from the decision
- Invariants — Hard rules that implementation must follow (structured with IDs matching the registry)
- Non-Goals — What this ADR explicitly does not cover
- Acceptance Criteria — Objective checks that prove the decision is implemented

**ADR Governance Protocol (encoded in root agents.md):**

- Core architectural decisions must be captured as ADRs before implementation
- Contributors must review applicable ADRs at the start of every implementation effort
- PRs and commits must reference governing ADRs
- If no ADR exists for a core decision, create one first

### 3.7 Invariant Registry

`.armature/invariants/registry.yaml` is the machine-readable index of all hard constraints. Each entry maps an invariant to its definition source, enforcement mechanisms, and governance file references.

**Registry Entry Schema:**

```yaml
invariants:
  SEQ-001:
    name: "Sequence contiguity"
    severity: critical                     # critical | high | standard
    status: active                         # active | deprecated
    superseded-by: null                    # Invariant ID of replacement, or null
    description: "Event sequences must be zero-based and contiguous per tenant"
    rule: "Event sequences must be zero-based and contiguous per tenant."
    defined-in: docs/adr/0002-event-schema.md
    enforced-by:
      ci:
        - tests/ledger_sequence_test.go
      startup:
        - src/ledger/failfast.go
      runtime:
        - src/events/sequence_guard.go
    referenced-in:
      - agents.md
      - src/ledger/agents.md
      - src/binder/agents.md
      - src/events/agents.md
    exceptions: []                         # Any approved exceptions with rationale
```

**Registry Rules:**

- Every invariant must have a unique ID using the pattern `{CATEGORY}-{NNN}`
- Every invariant should trace to at least one ADR (`defined-in`). For pre-1.0 projects where formal ADRs have not yet been written, invariants may reference `invariants.md` as their `defined-in` source. This is a bootstrap accommodation — once the project stabilizes, invariants should be backfilled with proper ADR references. The registry entry's `defined-in` field must never be empty.
- Every critical-severity invariant must have at least one CI enforcement (`enforced-by.ci`)
- Exceptions must include a rationale and reference a justifying ADR
- The registry is the source of truth for which invariants exist; `invariants.md` is the human-readable rendering
- Registry entries carry a `status` field (`active` or `deprecated`) and an optional `superseded-by` field pointing to a replacement invariant ID. See §7.4 for the full invariant lifecycle management protocol. Deprecated invariants remain in the registry for traceability but are not enforced by the reviewer.

`.armature/invariants/invariants.md` is the human-readable companion — prose descriptions of each invariant grouped by category. It is generated from or manually kept in sync with the registry. In degraded mode (no agentic tooling), this is what a human reads.

---

## 4. Persona Architecture

### 4.1 Overview

Armature defines five agent personas organized by decision authority, not skill level:

| Persona | Authority | Scope | Writes Code? | Agent Level |
|---|---|---|---|---|
| Orchestrator | Planning, delegation, acceptance | Global | No | Primary agent |
| Implementer | Execution within declared scope | Per-component | Yes | Auxiliary role |
| Reviewer | Invariant compliance, veto | Global (read-only) | No | Auxiliary role |
| Red Team Reviewer | Adversarial engineering quality, veto | Global (read-only) | No | Auxiliary role |
| Planner | Step-by-step decomposition | Per-task (opt-in) | No | Auxiliary role |

The orchestrator runs as the primary agent in the active tool runtime. In Claude Code, that identity is established by `CLAUDE.md`. In Codex, it is established by `CODEX.md`. Implementers, reviewers, and planners run as explicit subagents when the tool supports them. In Claude Code, subagents are spawned via the Agent tool. In Codex, parallel subagent spawning is available when the user explicitly requests it. When subagent support is unavailable or not requested, the workflow preserves those same role boundaries through sequential role passes.

Persona definitions live in `.armature/personas/`. Subagent wiring lives in `.claude/agents/` (for implementers, reviewers, and planners only — the orchestrator is not a subagent).

In Codex, the same persona boundaries still apply, but the runtime adapter is `CODEX.md` and scope routing points directly at shared persona files rather than `.claude/agents/` wiring.

### 4.2 Orchestrator

**File:** `.armature/personas/orchestrator.md`
**Claude Code agent level:** Primary agent (established by `CLAUDE.md`)
**Codex agent level:** Primary agent (established by `CODEX.md`)

The orchestrator is the single point of contact between the human and the agentic workflow. The human talks to the orchestrator. The orchestrator handles everything else. The human should never need to write PRD files, run Taskmaster commands, invoke implementers, or interact with any other agent.

**The orchestrator's full pipeline:**

```
Conversation → PRD → Task Graph → Delegation → Review → Acceptance
```

**Phase A — Discovery and Requirements:**
- Conducts a requirements conversation with the human
- Asks clarifying questions to surface scope, constraints, dependencies, and acceptance criteria
- Generates the PRD and saves it to `.taskmaster/docs/` (the human never writes PRDs)
- Confirms the PRD with the human before proceeding

**Phase B — Milestone and Task Decomposition:**
- Decomposes the PRD into 5–10 milestones, each producing a working verifiable increment
- Parses the current milestone into Taskmaster tasks (not the whole PRD at once)
- Runs complexity analysis; flags tasks scoring > 7 or exceeding `changeset-budget.planner-trigger-loc` for planner involvement
- Expands complex tasks into subtasks
- Annotates each task with its target agents.md scope
- Presents the milestone list and current milestone's task graph for confirmation
- Each milestone gets its own build candidate tag on completion

**Phase C — Execution:**
- Reads CLAUDE.md and AGENTS.md frontmatter for topology
- In Codex, reads `CODEX.md` and AGENTS.md frontmatter for topology, then routes directly to shared persona files
- Queries Taskmaster for the next task respecting dependency order
- Writes delegation intent to session state before spawning implementers (auto-compaction safety)
- Delegates to scoped implementers based on AGENTS.md scoping
- Spawns the reviewer after each implementer completes
- On reviewer PASS: commits changes with structured message, updates Taskmaster
- On reviewer FAIL: re-delegates with verdict reference (max 3 cycles)
- On 3 failures: escalates to human, writes to journal
- Tags build candidates at milestone completion
- Maintains session state, governance journal, and Taskmaster state

**Mid-flight adaptation:** When the human changes direction, the orchestrator updates the PRD, revises affected Taskmaster tasks, updates governance files if needed, and confirms the revised plan before resuming.

**The orchestrator must not:**
- Write application code
- Bypass the reviewer
- Delegate cross-cutting changes to a single implementer
- Delegate two tasks to the same scope simultaneously
- Delegate a task expected to exceed `changeset-budget.warn-loc` without decomposing it first
- Continue past the circuit breaker threshold (3 rejection cycles per checkpoint → escalate)

**Authority over governance files:**
- Can update CLAUDE.md (routing table, critical invariants)
- Can update CODEX.md (routing table, critical invariants)
- Can update root agents.md (global directives)
- Can update the invariant registry (new invariants, new references)
- Can create new scoped agents.md files (component onboarding)
- Can generate and update PRDs in `.taskmaster/docs/`
- Can update ARMATURE.md (specification amendments, protocol additions) via the /armature-update protocol
- In tools without slash commands, follows `.claude/commands/armature-update.md` conversationally instead of invoking `/armature-update`
- Can log exceptions to invariants with rationale
- Can write to the governance journal
- Can commit accepted changes and tag build candidates

**Token and session discipline:**
- Read AGENTS.md frontmatter (YAML headers only) to build delegation plans
- Delegate minimum necessary context per implementer — reference specific ADRs listed in frontmatter, not "read all ADRs"
- Point each implementer at only the files listed in its scoped AGENTS.md frontmatter
- Do not read application source code — delegate exploration tasks instead
- Checkpoint proactively at milestone boundaries; prefer fresh sessions over extended runs

In tools without persistent subagent wiring, the orchestrator still performs planner, implementer, reviewer, and red-team phases as distinct role passes. The runtime changes; the authority boundaries do not.

**Subagent spawning protocol:**

Claude Code's Agent tool does not automatically load `.claude/agents/` files. The orchestrator must explicitly construct each delegation. The canonical pattern:

1. **Read the subagent definition:** Read `.claude/agents/{name}.md` to get the subagent's instructions.
2. **Read the scoped agents.md frontmatter:** Read the YAML frontmatter of the target scope's `agents.md` to identify invariants, ADRs, authority, and restrictions.
3. **Compose the delegation prompt:** Combine the subagent instructions, scope context, and task-specific details into a single prompt for the Agent tool.
4. **Spawn:** Use the Agent tool with `subagent_type: "general-purpose"` and the composed prompt.

**Implementer delegation template:**
```
You are the {component} implementer. Read and follow your instructions:

[paste content of .claude/agents/{component}-impl.md]

Your task: {task description}

Scope: {agents.md path}
Invariants to respect: {invariant IDs from frontmatter}
Files you may modify: {file list}

When done, report: files changed, invariants touched, any discovered context.
```

**Reviewer delegation template:**
```
You are the reviewer. Read and follow your instructions:

[paste content of .claude/agents/reviewer.md]

Review this changeset:
- Files modified: {list}
- Declared scope: {scope}
- Invariants touched: {list}

Write your verdict to .armature/reviews/{task-id}.md
```

This explicit construction is intentional — it forces the orchestrator to think about scope and context before each delegation, preventing accidental scope creep.

### 4.3 Implementer

**Template:** `.armature/personas/implementers/{component}.md`
**Claude Code subagent:** `.claude/agents/{component}-impl.md`

Implementer personas are created per-component during onboarding. Each is scoped to a single AGENTS.md boundary. An implementer:

- Reads its local AGENTS.md (frontmatter + body) and referenced ADRs
- Reads its persona file for behavioral characteristics
- Writes code, tests, and configs within its declared scope
- Cannot make cross-cutting changes or modify files outside its scope
- Cannot modify governance files (AGENTS.md, ADRs, registry)
- Reports back to the orchestrator: what changed, which files, which invariants were touched

**Dynamic scoping:**
The implementer's authority is defined by the `authority` and `restricted` fields in its scoped AGENTS.md frontmatter. The persona file provides the behavioral baseline (communication style, decision-making approach, error handling philosophy). The frontmatter provides the scope-specific boundaries.

**Checkpoint-bounded execution:**
When working from a planner checkpoint plan, the implementer completes work up to the next review gate and stops. It reports the partial changeset for that checkpoint only. The orchestrator invokes the reviewer before the implementer proceeds to the next checkpoint. This keeps each review pass within the changeset budget.

**Circuit breaker awareness:**
If rejected by the reviewer, the implementer on re-delegation reads the structured verdict file at `.armature/reviews/{task-id}.md` before starting. It does not rely on conversational context from previous attempts. After 3 rejection cycles per checkpoint, the orchestrator escalates rather than re-delegating.

### 4.4 Reviewer

**File:** `.armature/personas/reviewer.md`
**Claude Code subagent:** `.claude/agents/reviewer.md`

The reviewer is an independent compliance checker with veto authority. It:

- Reads `.armature/invariants/registry.yaml` (the machine-readable constraint index)
- Reads `.armature/invariants/invariants.md` (human-readable context for ambiguous cases)
- Receives a changeset from the orchestrator (list of modified files, declared scope, invariants touched)
- Checks each claimed invariant against its enforcement mechanisms
- Validates that the changeset does not modify files outside the declared scope
- Validates that no invariant was relaxed without an approved exception
- Produces a structured verdict at `.armature/reviews/{task-id}.md`

**Verdict Format:**

```markdown
# Review Verdict: {task-id}

## Scope Compliance
- Declared scope: {scope from AGENTS.md frontmatter}
- Files modified: {list}
- Out-of-scope modifications: {list or "none"}

## Invariant Compliance
| Invariant | Status | Notes |
|---|---|---|
| SEQ-001 | PASS | Sequence contiguity preserved |
| DIGEST-002 | FAIL | Digest computation modified without updating canonical helper |

## Verdict: PASS | FAIL | CONDITIONAL
## Required Changes (if FAIL/CONDITIONAL):
- {specific remediation instructions}
```

**The reviewer must not:**
- Write or modify code
- Suggest implementation approaches (only identify violations)
- Override its own verdict
- Trigger rollback (it recommends; the orchestrator decides)

**Verdict persistence:** Reviewer verdicts at `.armature/reviews/{task-id}.md` are committed to version control, creating an audit trail of review decisions. This enables post-hoc analysis of review patterns and allows the orchestrator to reference historical verdicts when similar changes arise. Verdicts for rolled-back work remain in the git history even after rollback.

### 4.5 Red Team Reviewer

**File:** `.armature/personas/reviewer-redteam.md`
**Claude Code subagent:** `.claude/agents/reviewer-redteam.md`

The red team reviewer is an adversarial engineering quality checker with veto authority. It operates after the standard reviewer passes, taking an aggressive posture toward code changes to hunt for subtle bugs, silent regressions, semantic drift, edge-case failures, and breaking changes that pass compliance review.

**Invocation criteria (evaluated by the orchestrator after standard reviewer PASS):**
- **Required:** Changes touch a critical-severity invariant (from registry.yaml), changes are cross-cutting (span multiple agents.md boundaries), or the human explicitly requests deep review
- **Recommended:** Complex logic changes (complexity > 5), test infrastructure modifications, or implementer-reported uncertainty about edge cases
- **Skippable:** All fast-path criteria hold (complexity ≤ 3, single scope, LOC ≤ target), no critical invariants at risk, and the human has not requested deep review

A PASS_WITH_ADVISORIES verdict means: commit proceeds, but advisories are logged in the governance journal for tracking. Advisories do not block the commit.

Where the standard reviewer checks governance compliance (invariants, scope boundaries, exceptions), the red team reviewer checks engineering correctness:

- Reads every line of changed code (not just frontmatter and registries)
- Traces data flow through inputs, dependencies, and consumers
- Attacks test quality — looking for tautological tests, missing negative tests, and false greens
- Stresses interfaces for schema/reality mismatches and forward/backward compatibility
- Runs tests independently and feeds edge-case inputs to verify behavior
- Produces a structured verdict at `.armature/reviews/{task-id}-redteam.md`

**Verdict outcomes:** PASS, FAIL, or PASS_WITH_ADVISORIES. A FAIL blocks the commit even if the standard reviewer passed. PASS_WITH_ADVISORIES tracks non-blocking issues.

**Severity calibration:**
- CRITICAL: Silent wrong output, data corruption, security issue — always blocks
- HIGH: Crash on valid input, regression, nondeterminism — blocks unless explicitly accepted
- MEDIUM: Missing edge-case handling, test gap — tracked but does not block
- LOW: Style, naming — never blocks

**The red team reviewer must not:**
- Write or modify application code
- Write or modify governance files (except its verdict file)
- Suggest implementation approaches (only identify what is wrong and why)
- Override its own verdict

### 4.6 Planner (Opt-In)

**File:** `.armature/personas/planner.md`
**Claude Code subagent:** `.claude/agents/planner.md`

The planner is activated by the orchestrator when a task within a single scope is too complex for a single implementer pass OR when the estimated LOC exceeds `changeset-budget.planner-trigger-loc`. It:

- Reads the local AGENTS.md and referenced ADRs for the target scope
- Produces a numbered implementation plan with invariant checkpoints and LOC estimates per step
- Identifies dependencies between steps
- Marks review checkpoints between groups of steps — mandatory for plans with more than 3 steps (at least one intermediate checkpoint required)
- Ensures each checkpoint stays within the changeset budget (`target-loc`)
- Hands the plan to the orchestrator for checkpoint-bounded delegation

The orchestrator invokes the planner when: (a) task complexity > 7, OR (b) estimated LOC > `changeset-budget.planner-trigger-loc`. Simple, small, well-scoped changes go directly to an implementer without planning.

#### 4.6.1 Complexity Scoring Rubric

Complexity is scored on a 1–10 scale. The orchestrator assigns a score during Phase B decomposition. When Taskmaster is available, its `analyze_project_complexity` tool provides a starting estimate that the orchestrator may adjust.

| Score | Label | Characteristics | Routing |
|---|---|---|---|
| 1–2 | Trivial | Single-file, no logic changes, config/docs only | Fast path |
| 3 | Simple | Single-scope, clear intent, < 100 LOC, no new invariants | Fast path ceiling |
| 4–5 | Moderate | Single-scope, some logic, 100–300 LOC, may touch existing invariants | Direct to implementer |
| 6 | Involved | Multi-file within scope, 200–400 LOC, new tests required | Planner recommended |
| 7 | Complex | Approaching scope boundary, 300–500 LOC, invariant interaction | Planner required |
| 8–9 | High | Near-scope-boundary, 500+ LOC estimated, may need new invariants or ADRs | Planner required; consider further decomposition |
| 10 | Architectural | Cross-cutting, new ADR likely, fundamental design change | Must decompose before planning; likely needs human design input |

**Scoring inputs:** LOC estimate, file count, invariants at risk, cross-scope dependencies, test requirements, novelty (is this a pattern the codebase has done before?).

**Tie-breaking rule:** When in doubt, score higher. Over-planning wastes less time than under-planning followed by rejection cycles.

---

## 5. Enforcement Model

### 5.1 In-Session Pipeline (Agentic)

```
Human ←→ Orchestrator → PRD → Taskmaster → [Planner?] → Implementer → Reviewer → [Red Team?] → Orchestrator
              ↑                                                                        ↓
              └──────────────────────── Accept / Reject / Escalate ────────────────────┘
```

**Fast path (complexity ≤ 3):**

Not every change warrants the full pipeline. For small, well-scoped work — bug fixes, config tweaks, single-file changes with clear scope — the orchestrator uses a streamlined flow:

```
Human → Orchestrator → Implementer → Reviewer → Accept
```

**Fast path criteria (all must hold):**
- Change touches a single component scope (one `agents.md` boundary)
- No new invariants or ADRs are involved
- The human's intent is unambiguous — no discovery conversation needed
- Estimated complexity ≤ 3 (trivial to straightforward)
- Estimated LOC ≤ `changeset-budget.target-loc` (default 300)

**Fast path skips:**
- PRD generation
- Taskmaster task creation (uses TodoWrite or inline tracking instead)
- Planner involvement
- Milestone decomposition

**Fast path preserves:**
- Scoped delegation (implementer reads its `agents.md`)
- Reviewer check (never skipped) — reviewer still writes a structured verdict to `.armature/reviews/{task-id}.md`, not just an inline report. This keeps the governance journal consistent regardless of which path was used.
- Structured commit message
- Session state update
- Journal entry if governance-relevant

The orchestrator decides which path to use. When in doubt, use the full pipeline. The fast path is an optimization, not an escape hatch.

**Phase A — Requirements:**
1. Human describes intent conversationally to the orchestrator
2. Orchestrator asks clarifying questions, confirms understanding
3. Orchestrator generates PRD, saves to `.taskmaster/docs/`, confirms with human

**Phase B — Planning (per milestone):**
4. Orchestrator decomposes PRD into milestones (5–10 working increments)
5. Orchestrator parses current milestone into Taskmaster tasks (via MCP `parse_prd` or `add_task`)
6. Orchestrator runs complexity analysis, expands complex tasks, annotates with scope
7. Orchestrator estimates LOC for each task. Tasks exceeding `changeset-budget.planner-trigger-loc` must route through the planner regardless of complexity score. Tasks exceeding `changeset-budget.warn-loc` must be decomposed into smaller subtasks before delegation.
8. Orchestrator presents the plan to human for confirmation

**Phase C — Execution (per task):**
7. Orchestrator queries Taskmaster for next task
8. Orchestrator annotates task with target agents.md scope
9. **Pre-flight estimation:** Orchestrator estimates files to be touched, expected net LOC, invariants at risk, and cross-scope dependencies. If estimated LOC > `changeset-budget.target-loc`, return to Phase B for further decomposition or planner invocation. Log the estimate in session state.
10. If complexity > 7 OR estimated LOC > `changeset-budget.planner-trigger-loc`, orchestrator invokes planner first
11. Orchestrator writes delegation intent to session state (auto-compaction safety)
12. Orchestrator delegates to scoped implementer (or to first checkpoint if planner produced a checkpoint plan — see incremental review below)
13. Implementer executes, reports changeset
12a. **Post-implementation LOC check:** Compare actual LOC from implementer report against pre-flight estimate (step 9). Log variance in session state. If actual > warn-loc, log in governance journal (diagnostic only — review proceeds).
14. Orchestrator spawns reviewer against the changeset
15. Reviewer writes structured verdict to `.armature/reviews/{task-id}.md`
16. On reviewer PASS, orchestrator evaluates red team invocation criteria (see §4.5):
    - **Required:** critical-severity invariant touched, cross-cutting change, or human-requested deep review
    - **Recommended:** complex logic (complexity > 5), test infrastructure changes, implementer uncertainty
    - **Skippable:** fast-path criteria met, no critical invariants, no human request
17. Red team reviewer writes verdict to `.armature/reviews/{task-id}-redteam.md` (if spawned)
18. Orchestrator evaluates:
   - **PASS** (both reviewers) → Commit with structured message, update Taskmaster, tag build candidate if milestone, write to journal if governance-relevant
   - **FAIL** (either reviewer) → Re-delegate to implementer with verdict file reference (max 3 cycles per checkpoint)
   - **ESCALATE** → Write to `.armature/escalations/` and `.armature/journal.md`, surface to human

**Incremental review (checkpoint-bounded execution):**

When the planner produces a plan with review checkpoints, execution follows a chunked pipeline instead of the single-pass flow above:

```
For each checkpoint in the plan:
  Orchestrator → Implementer (steps up to checkpoint) → Reviewer → [Red Team?] → Commit checkpoint
```

1. Orchestrator delegates the steps up to the first review checkpoint
2. Implementer executes those steps only, stops, and reports the partial changeset
3. Orchestrator spawns the reviewer on the partial changeset (optionally red team)
4. On PASS: commit the checkpoint immediately with message `task-{id}/checkpoint-{n}: {description}`
5. On FAIL: re-delegate the current checkpoint only (max 3 cycles — circuit breaker is per-checkpoint)
6. On checkpoint PASS: proceed to next checkpoint, delegating the next batch of steps
7. Completed checkpoints are committed and preserved regardless of failures in later checkpoints

This ensures that review surface area per pass stays within the changeset budget. A task estimated at 900 LOC becomes three ~300 LOC review passes instead of one monolithic review.

### 5.2 Mechanical Enforcement Hooks

**Hooks are the backstop, not the primary enforcement.** The primary enforcement layer is the persona directive — "you do not write application code" — which prevents bad reasoning from happening in the first place. Hooks catch what slips past the behavioral layer. All hooks are bash scripts, deterministic, and execute without LLM involvement. Guards exit 2 to block operations; observers exit 0 always. Hooks receive context via JSON on stdin.

In tools that cannot wire these hooks natively, the same scripts still serve as manual validation and CI enforcement artifacts.

#### 5.2.1 On-Stop Validation (Stop, SubagentStop)

Wired to Claude Code's `Stop` and `SubagentStop` lifecycle events. Runs `post-stop.sh`, which performs:

- CLAUDE.md routing table references resolve to existing files
- CODEX.md routing table references resolve to existing files when CODEX.md is present
- YAML governance files conform to their schemas (SCHEMA-001, SCHEMA-002)
- No uncommitted governance file changes exist without session log entries
- All ADR references in `agents.md` frontmatter resolve to files in `docs/adr/`
- Conditional application test run: if `.armature/.code-dirty` marker exists, runs the project test suite and removes the marker on pass

In Codex and other tools without lifecycle wiring, `post-stop.sh` is run manually before handoff or via CI.

This is the only hook that may exceed one second of execution time, due to the conditional test suite invocation triggered by the `mark-dirty` integration.

#### 5.2.2 Pre-Tool-Use Guards (PreToolUse)

Two hooks gate destructive or under-informed tool use before it occurs:

- `block-dangerous-commands.sh` — Bash tool guard. Blocks destructive operations including: `rm -rf` on broad targets, `git push --force`, `git reset --hard`, `git clean -f`, `DROP TABLE` / `TRUNCATE`, `chmod -R 777`, `--no-verify` / `--skip-hooks`, bulk staging commands (`git add -A`, `git add -u`, `git add .`), `git checkout -- .`, `git restore .`, `git branch -D`, `git stash drop` / `git stash clear`, `dd if=`, `mkfs`, and fork bomb patterns. Allows `rm -rf` on safe targets such as `node_modules` and `__pycache__`. Prevents agent self-harm by catching commands that would bypass governance, destroy working state, or cause irreversible data loss.

- `check-required-reading.sh` — Edit/Write tool advisory. Walks the directory hierarchy from the target file upward to find the governing `agents.md`, parses its frontmatter ADR references, and prints the required reading list to stderr. Advisory in the current version (exit 0 always); future versions may enforce compliance via read-receipt tracking before allowing the write to proceed.

#### 5.2.3 Post-Tool-Use Observers (PostToolUse)

- `mark-dirty.sh` — Edit/Write observer. Touches `.armature/.code-dirty` when application code (non-governance files) is modified. Enables staged verification: the expensive test suite runs only when code actually changed. The marker is removed by post-stop validation after the conditional test run passes. This decouples the cost of test execution from governance-only sessions.

#### 5.2.4 Configuration Guards (ConfigChange)

- `block-config-changes.sh` — Prevents agents from modifying their own governance configuration. Blocks changes originating from `user_settings`, `project_settings`, `local_settings`, and `skills`. Allows changes to `policy_settings`, which remain under human control. Enforces principle P3 (Authority Boundaries): agents operate within their configuration envelope; they do not rewrite it.

#### 5.2.5 Context Injection (SubagentStart, SessionStart)

Two hooks maintain ambient context across subagent boundaries and context compaction events:

- `inject-context.sh` — SubagentStart hook. Injects the active invariants from the registry, current session state, and scope-specific governance context into the subagent system prompt before it begins work. Data-driven and not opinionated about the subagent's task.

- `reinject-context.sh` — SessionStart hook with compact matcher. After context compaction, re-injects session state, recent journal entries, recent git history, and dirty marker warnings into the restored session. Implements principle P4 (Externalized Working Memory): the agent's working context survives compaction because it is stored externally and reloaded, not reconstructed from inference.

#### 5.2.6 Hook Wiring

Hooks are wired to Claude Code lifecycle events via `settings.json`. A template is provided at `.armature/templates/settings-hooks.json.tmpl`. Projects copy and adapt this template during `/armature-init`. The template documents the assumed Claude Code hook API contract and serves as the authoritative mapping between hook scripts and the lifecycle events they handle.

Codex has an experimental `hooks.json` system (`.codex/hooks.json`) that supports the same lifecycle events (`PreToolUse`, `PostToolUse`, `SessionStart`, `Stop`). When available, projects can wire Armature hook scripts to Codex lifecycle events via `.codex/hooks.json`. A template mapping is provided at `.armature/templates/codex-hooks.json.tmpl`. When hooks.json is unavailable or not desired, the same scripts serve as shared manual/CI enforcement.

### 5.3 Scaffold Integrity Tests (CI)

A test suite that validates the governance structure itself:

- Every governance file (`agents.md` or `AGENTS.md`) referenced in CLAUDE.md's routing table exists
- Every governance file (`agents.md` or `AGENTS.md`) referenced in CODEX.md's routing table exists when CODEX.md is present
- Every ADR referenced in any governance file frontmatter exists
- Every invariant ID in any governance file frontmatter exists in the registry
- Every `enforced-by` entry in the registry points to a file that exists
- Every `referenced-in` entry in the registry points to a file that references that invariant
- CLAUDE.md routing table covers every governance file in the repo
- CODEX.md routing table covers every governance file in the repo when CODEX.md is present
- No governance file references a parent in `inherits` that doesn't exist
- No invariant has severity `critical` without at least one CI enforcement

### 5.4 CI Review Pipeline (Optional)

Armature provides an optional automated PR review-fix pipeline that integrates with external code review bots (e.g., Greptile, Codex). When enabled, the pipeline:

1. **Detects** review comments from configured bots
2. **Batches** all unaddressed comments into a single fix request (60-second collection window by default)
3. **Runs** Claude Code Action to fix all issues in one atomic commit
4. **Marks** each addressed review thread with "Fixed in {sha}"
5. **Requests re-review** from the score-gated bot (if configured)
6. **Graduates** to a final reviewer once the score threshold is met

**Configuration** is in `governance.ci-review-pipeline` in `config.yaml`. The pipeline is disabled by default and enabled during `/armature-init` based on user preferences.

**Two auth methods:**
- `api-key` — Uses `ANTHROPIC_API_KEY` repository secret with Claude Code Action. Supports model selection.
- `github-app` — Uses the Claude GitHub App. No API key needed, but no model control.

**Review bot types:**
- `score-gated` — Bot produces a score (e.g., 3/5). Pipeline waits until score meets threshold before graduating to the next reviewer. Score pattern is configurable via regex.
- `direct` — Bot posts review comments directly. Fixes are applied and the bot is re-invoked. Supports acknowledgment detection via emoji reaction with configurable timeout and retries.

**Template:** `.armature/templates/claude-pr-fix.yml.tmpl` contains the parameterized GitHub Actions workflow. During `/armature-init` or `/armature-backport`, the orchestrator substitutes config values to generate `.github/workflows/claude-pr-fix.yml`.

**Loop prevention:** Each fixed thread receives a "Fixed in {sha}" reply. The batching step skips threads that already have this marker. The mark-fixed-threads job only runs on pushes that modify source files (`.py`, `.json`, etc.) and only marks threads whose referenced file was touched.

### 5.5 CI Contract Tests (Project-Specific)

Implemented per-project in the test suite. These validate that architectural invariants are actually enforced at runtime:

- Schema validation tests (if applicable)
- Referential integrity tests (configs reference real entities)
- Startup fail-fast validation (services reject invalid configuration)
- Domain-specific invariant checks

---

## 6. Resilience Mechanisms

### 6.1 Session State Protocol

The orchestrator maintains a living state file at `.armature/session/state.md` updated at every state transition — not after every message, but at every meaningful checkpoint.

**State transitions that trigger an update:**
- Task decomposed / Taskmaster updated
- Implementer delegated
- Implementer completed
- Reviewer verdict received
- Accept/reject/escalate decision made
- Build candidate tagged
- Rollback initiated
- New invariant or constraint discovered mid-session

**State File Structure:**

```markdown
# Armature Session State

## Current Objective
{high-level task from human}

## Build Candidate
{current build candidate tag, or "none"}

## Task Status
{Taskmaster task IDs with status: pending / delegated / complete / rejected / escalated}

## Active Delegation
{currently delegated task, implementer scope, start time}

## Pending Reviews
{tasks awaiting reviewer pass}

## Invariants Touched
{which invariants were relevant, any ambiguities found}

---
<!-- APPEND-ONLY BELOW THIS LINE -->

## Decisions Log
- {timestamp} — {decision with rationale, especially rejected approaches}
- {timestamp} — {decision}

## Discovered Context
- {timestamp} — {anything learned that isn't in agents.md or ADRs}
```

Sections above the append line are overwritten each update. Sections below are append-only — history matters for decisions and discoveries.

### 6.2 Checkpointing

The `/checkpoint` slash command is invoked before compaction or when the human wants to save state explicitly.

**Checkpoint protocol:**
1. Orchestrator updates `.armature/session/state.md` with full current status
2. Orchestrator syncs with Taskmaster (all task statuses current)
3. Orchestrator confirms the current build candidate tag
4. Human may safely run `/compact`

**Post-compaction recovery:**
CLAUDE.md is re-injected automatically by Claude Code. CLAUDE.md contains the directive: "At the start of any resumed or compacted session, read `.armature/session/state.md` if it exists. Resume from the recorded state."

### 6.3 Commit Protocol

After each reviewer PASS, the orchestrator commits the accepted changes immediately. Commits are per-task — do not batch across tasks.

**Commit message format:**
```
task-{id}: {task title}

Scope: {agents.md path}
Invariants: {invariant IDs touched}
Reviewer: PASS
```

Per-task commits ensure: work is preserved if auto-compaction kills the session, git history maps cleanly to the Taskmaster task graph, and rollback granularity is at the task level.

**Collision avoidance:** The orchestrator must never delegate two tasks to the same scope simultaneously. Parallel implementers must work on disjoint scopes (enforced by the reviewer's scope compliance check).

### 6.4 Build Candidates

A build candidate is a git tag representing a known-good milestone. Tags go on top of already-committed task work. The orchestrator tags a build candidate when:

- A milestone in the Taskmaster task graph completes (multiple accepted tasks)
- The human explicitly requests a snapshot

**Tag format:** `bc/{date}/{sequence}` — e.g., `bc/2026-03-13/001`

**Build candidate protocol:**
1. Orchestrator confirms all milestone tasks are committed and reviewer-PASS
2. Orchestrator runs `git tag bc/{date}/{sequence}`
3. Orchestrator records the tag in session state and the governance journal

**Rollback protocol:**
If a subsequent task introduces a regression or the reviewer recommends rollback:
1. Orchestrator writes rollback decision and rationale to the governance journal
2. Orchestrator executes `git reset --hard {build-candidate-tag}`
3. Orchestrator updates session state and Taskmaster
4. Orchestrator reads governance journal to identify any governance changes lost in the rollback
5. If governance changes need re-application (e.g., a component was onboarded as part of the rolled-back work but the architectural decision still stands), orchestrator re-applies them

**Rollback is an orchestrator-only action.** The reviewer can recommend it. Implementers cannot trigger it.

**Governance file rollback:** Committed governance files (agents.md, ADRs, registry entries) roll back with the code — this is correct for code-coupled governance. The governance journal is committed and rolls back with the code. Before executing a rollback, the orchestrator reads the journal to identify governance decisions that will be lost, recording them in session state so they can be re-applied if appropriate.

### 6.5 Governance Journal

`.armature/journal.md` is an append-only, **committed** log of governance-relevant events. It provides institutional memory that survives session boundaries and compaction. Because the journal is version-controlled, it rolls back with the code on `git reset`. To preserve governance memory across rollbacks, the orchestrator must read the journal *before* executing a rollback and note any governance decisions that will be lost (recording them in session state or as a separate pre-rollback journal snapshot).

**The orchestrator writes to the journal when:**
- An invariant exception is approved (with rationale and ADR reference)
- An escalation is created or resolved
- An invariant ambiguity is discovered or resolved
- An ADR is created or amended
- An agents.md is created or modified
- A component is onboarded
- A build candidate is tagged
- A rollback is executed (from what tag, to what tag, what was lost)

**Journal entry format:**
```markdown
### {YYYY-MM-DD HH:MM} — {category}
{Description of what happened and why.}
```

**On cold start,** the orchestrator reads the journal to understand governance history. If a rollback occurred since the last session, the journal identifies what governance changes were lost and whether they need re-application.

The journal is not a replacement for session state (which tracks in-flight work) or the invariant registry (which tracks active constraints). It is the historical record that gives context to decisions.

### 6.6 Circuit Breaker

If an implementer is rejected 3 times on the same task, the orchestrator stops and escalates:

1. Writes accumulated review verdicts and implementation state to `.armature/escalations/{task-id}/`
2. Writes the escalation to `.armature/journal.md`
3. Updates Taskmaster task status to "escalated"
4. Updates session state
5. Surfaces the escalation to the human with a structured handoff:
   - What was attempted
   - Why it was rejected each time
   - What the unresolved tension is
   - Suggested resolution paths

**Three cycles is the hard limit.** More spinning almost never helps. Either the invariants are ambiguous, the decomposition was wrong, or there's a design tension requiring human judgment.

**Circuit breaker with incremental review:** When using checkpoint-bounded incremental review (see §5.1), the 3-cycle counter applies per checkpoint, not per task. Each checkpoint is an independent review unit. Completed and committed checkpoints are preserved regardless of failures in subsequent checkpoints — their work is already accepted and committed. This means a 5-checkpoint task can tolerate up to 3 rejection cycles per checkpoint without losing any previously accepted work.

**Escalation recovery:** When the human resolves an escalation and tells the orchestrator what was decided, the orchestrator writes the resolution to the journal, clears the escalation directory, applies any governance changes that follow from the resolution, and resumes execution from the resolved task.

### 6.7 Cold Start vs. Warm Start

**Warm start (post-compaction):**
CLAUDE.md reloads (re-establishing orchestrator identity) → orchestrator reads `.armature/session/state.md` → reads `.armature/journal.md` for governance history → queries Taskmaster for task status → resumes from recorded state.

**Cold start (new session):**
1. Orchestrator reads CLAUDE.md (identity + orientation)
2. Reads `.armature/journal.md` for governance history
3. Checks for existing `.armature/session/state.md`:
   - If none exists → fresh session, proceed normally
   - If one exists → check if it's from an abandoned session
4. Checks for unresolved escalations in `.armature/escalations/`
5. Checks that working tree is clean relative to the last build candidate
6. If dirty state detected → surface to human before starting new work
7. Queries Taskmaster for any pending/in-progress tasks

**Checkpoint recovery (mid-task crash):**
When cold start detects a partially completed task (session state shows active delegation with no reviewer verdict and no commit for that task), follow this recovery protocol:
1. Read session state for the in-flight task ID, scope, and LOC estimate
2. Read git log for any `task-{id}/checkpoint-{n}` commits to determine how many checkpoints completed
3. Check `git status` for uncommitted changes in the delegated scope
4. If uncommitted changes exist: spawn the reviewer against the partial changeset. On PASS, commit as a recovery checkpoint and log in the journal. On FAIL, discard uncommitted changes (`git checkout -- {scope}`) and re-delegate from the last committed checkpoint.
5. If no uncommitted changes: re-delegate from the last committed checkpoint (or from scratch if no checkpoints were committed)
6. Update session state to reflect the recovery action

### 6.8 Taskmaster Integration

Taskmaster (npm: `task-master-ai`) serves as the orchestrator's persistent task graph. It runs as an MCP server within Claude Code, giving the orchestrator direct tool access to task management without switching context.

**Setup (one-time per machine + per project):**

Global install:
```bash
npm install -g task-master-ai
```

Register MCP server with Claude Code:
```bash
claude mcp add-json "task-master" '{"command":"npx","args":["-y","task-master-ai"],"env":{"MODEL":"claude-code"}}'
```

Initialize per project:
```bash
task-master init
```

Configure `.taskmaster/config.json` to use Claude Code's built-in models (no external API keys required):
```json
{
  "models": {
    "main": { "provider": "claude-code", "modelId": "sonnet" },
    "research": { "provider": "claude-code", "modelId": "opus" },
    "fallback": { "provider": "claude-code", "modelId": "sonnet" }
  }
}
```

**What Taskmaster provides:**

- Persistent task graph on disk (`.taskmaster/tasks/`) — survives compaction inherently
- Dependency tracking between tasks — the orchestrator queries "next task" respecting dependency order
- Task complexity analysis — tasks scoring above 7 should be routed through the planner persona before delegation
- Subtask decomposition — complex tasks broken into manageable units
- PRD parsing — transforms a product requirements document into a structured task graph during `/armature-init`
- Cold start recovery — a new session reads Taskmaster state to understand what's pending/complete

**What Taskmaster does NOT provide (Armature session state covers these):**

- Which invariants were touched per task
- Reviewer verdicts and accept/reject decisions
- Build candidate tag tracking
- Governance file change log
- Discovered context and decisions rationale
- Conflict resolution and exception logging

**Orchestrator's Taskmaster workflow:**

The human never interacts with Taskmaster directly. The orchestrator manages the full pipeline:

1. Have a requirements conversation with the human
2. Generate the PRD from the conversation, save to `.taskmaster/docs/`
3. Confirm the PRD with the human
4. Parse the PRD into Taskmaster tasks via `parse_prd`
5. Run complexity analysis via `analyze_project_complexity`
6. Expand complex tasks (> 7) via `expand_task`
7. Present the task graph to the human for confirmation
8. Query Taskmaster for the next task via `next_task`
9. If complexity > 7 OR estimated LOC > `changeset-budget.planner-trigger-loc`, invoke the planner persona first
10. Delegate task to scoped implementer (or to first checkpoint if using incremental review)
11. On cycle completion: update Taskmaster via `set_task_status` (complete / blocked / escalated)
12. Tag build candidate on milestone task completion
13. Loop from step 8 until all tasks complete or human redirects
14. On `/checkpoint`, ensure all Taskmaster statuses are current

For small, well-scoped work that doesn't warrant a PRD, the orchestrator can create tasks directly via `add_task` from conversation.

**Fallback: When Taskmaster is unavailable:**

Taskmaster is the preferred task management tool, but the orchestrator must degrade gracefully when it is not installed or its MCP server is not registered. The fallback protocol:

1. **Detection:** At session start, the orchestrator checks whether Taskmaster MCP tools are available. If they are not, it proceeds in lightweight mode.
2. **Lightweight task tracking:** The orchestrator uses its built-in TodoWrite tool (or a markdown task list in `.armature/session/state.md` under a `## Task Status` section) to track tasks, dependencies, and status. Each task entry must use the Taskmaster-compatible schema: `{ id, title, description, status, dependencies[], priority, complexity }`. This ensures tasks can be migrated to Taskmaster without reformatting when it becomes available.
3. **No PRD parsing:** Without Taskmaster, the orchestrator decomposes work conversationally and records tasks directly using the same schema fields.
4. **Complexity assessment:** The orchestrator estimates task complexity using judgment rather than Taskmaster's `analyze_project_complexity`. Tasks the orchestrator judges as complex still route through the planner.
5. **Upgrade path:** When Taskmaster becomes available, the orchestrator can backfill the task graph from session state and resume with full Taskmaster integration. Because fallback tasks use the same schema, migration is a direct import — no reformatting required.

The lightweight mode preserves all other governance guarantees: delegation boundaries, reviewer checks, session state, journal logging, and build candidates. Only persistent task graph management degrades.

When the human changes direction mid-flight, the orchestrator updates affected tasks, adds/removes tasks, and confirms the revised plan — all through Taskmaster's MCP tools.

**Recommended:** Commit `.taskmaster/tasks/` to version control. This provides persistence across sessions and rollback safety via build candidate tags.

---

## 7. Operational Protocols

### 7.1 Instantiation — `/armature-init`

Armature instantiation is a three-phase process that works for both greenfield and existing repositories.

**Phase 0 — Pre-Flight (existing repos):**
The orchestrator scans the codebase before engaging the human:
- Reads directory tree, package manifests, configs, CI files, READMEs, existing tests
- Checks for existing governance artifacts (CLAUDE.md, CODEX.md, agents.md/AGENTS.md, ADRs, .claude/, .taskmaster/)
- Tags the pre-Armature baseline: `git tag armature/pre-init`
- Reports findings to the human: what exists, what will be created, what will be incorporated

For greenfield repos, Phase 0 is minimal — just confirm the repo is initialized and tag the baseline.

**Phase 1 — Project Discovery:**
The orchestrator combines code analysis (from Phase 0) with a conversation with the human. For existing repos, the orchestrator leads with what it observed and asks the human to correct and extend. For greenfield repos, the orchestrator has a natural dialogue to surface requirements.

Discovery produces:
- `.armature/config.yaml` — project metadata and topology
- `.taskmaster/docs/prd.txt` — initial PRD generated from the conversation

Both are confirmed with the human before proceeding.

**Phase 2 — Scaffolding:**
Using discovery output, the system creates (checking for existing artifacts at each step):
1. Seed ADRs in `docs/adr/` — adopting existing ADRs, creating new ones for undocumented decisions
2. Invariant registry — scanning existing tests/guards for enforcement, marking gaps as TODOs
3. Human-readable invariants
4. Scoped governance files (`agents.md` or `AGENTS.md`, matching the project's existing convention) — iterating the topology (not globbing existing files) to update existing governance files and create new ones for components that lack them
5. Implementer persona files
6. Claude Code subagent files (implementers, reviewer, planner — not orchestrator)
7. Tool adapter entrypoints (`CLAUDE.md`, `CODEX.md`) — merge existing content or generate both runtime adapters from shared governance
   `CODEX.md` is created or updated in the same step so both adapters stay aligned.
   When generating `CODEX.md`, include a prerequisite note reminding users that Codex does not auto-discover this file and that `.codex/config.toml` must include `project_doc_fallback_filenames = ["CODEX.md"]`.
8. `.gitignore` entries (appended, not replaced)
9. Taskmaster initialization (skipped if `.taskmaster/` exists)
10. Verification with human, initial build candidate tag, journal entry

**Ordering matters:** ADRs before registry (invariants reference ADRs) → registry before scoped agents.md (frontmatter references invariants) → agents.md before tool adapter entrypoints (routing tables reference agents.md files).

Shared governance files must be created before tool adapter entrypoints so that `CLAUDE.md` and `CODEX.md` only route to already-existing artifacts.

The full step-by-step protocol is defined in `.claude/commands/armature-init.md`.

### 7.2 Component Onboarding — `/armature-extend`

Triggered by the orchestrator when a new component directory is needed.

**Protocol:**
1. Orchestrator determines the new component's path, responsibility, and governing ADRs
2. Creates the directory
3. Creates the governance file (`agents.md` or `AGENTS.md`, matching the project's convention) with frontmatter (inherits, adrs, invariants, persona, authority, restricted)
4. Creates implementer persona file at `.armature/personas/implementers/{component}.md`
5. Creates Claude Code subagent at `.claude/agents/{component}-impl.md`
6. Updates invariant registry if new invariants apply
7. Updates `CLAUDE.md` routing table and `CODEX.md` routing table (when present) with the new entry
8. Logs the onboarding in session state decisions log

**Component onboarding is an orchestrator-only action.** If an implementer discovers that a new component is needed, it reports that finding to the orchestrator.

### 7.3 Agentic Session Logging

Every orchestrator session produces a structured log at `.armature/session/logs/{session-id}.md` upon session completion:

```markdown
# Session Log: {session-id}
**Date:** {date}
**Objective:** {high-level task}
**Build Candidates Tagged:** {list of tags}

## Tasks Executed
| Task | Implementer Scope | Reviewer Verdict | Cycles | Outcome |
|---|---|---|---|---|
| {task} | {scope} | PASS/FAIL | {n} | accepted/escalated |

## Invariants Touched
{list of invariant IDs with any ambiguities noted}

## Decisions Made
{timestamped decisions with rationale}

## Discovered Context
{anything learned that should be considered for governance updates}

## Governance Changes
{any agents.md, ADR, registry, or CLAUDE.md modifications made during session}
```

Session logs are gitignored by default but can be committed if audit trail is desired.

### 7.4 Conflict Resolution

**Inheritance conflicts:**
More specific `agents.md` files take precedence on implementation details. Invariants propagate downward unconditionally.

**Rules:**
- A leaf `agents.md` can add constraints but cannot relax constraints defined in a parent
- A leaf `agents.md` can specify implementation approaches that differ from parent guidance
- If a genuine exception to an invariant is needed:
  1. The exception must be logged by the orchestrator with a rationale
  2. The exception must be recorded in the invariant registry under the `exceptions` field
  3. The exception must reference a justifying ADR
  4. The exception is visible to the reviewer, who validates the justification

**No silent relaxation.** An agent cannot ignore an invariant because a local `agents.md` doesn't mention it. Invariants apply globally unless explicitly excepted.

**Definition — Cross-cutting changes:**
A change is cross-cutting when it modifies files governed by more than one scoped `agents.md` boundary. Examples: shared utility functions imported by multiple components, database schema changes affecting multiple consumers, API contract changes requiring coordinated updates across producer and consumer scopes. A shared utility that lives in its own scope is not cross-cutting if only that scope's files are modified — the scope boundary, not the import graph, is the governing line. Cross-cutting changes must not be delegated to a single implementer; the orchestrator must decompose them into per-scope tasks or coordinate parallel implementers with explicit dependency ordering.

**Invariant lifecycle management:**
Invariants are not permanent. They may be loosened, split, deprecated, or reclassified as the project evolves. All lifecycle transitions require:
1. An ADR documenting the rationale, using the "Supersedes Invariants" section of the ADR template
2. Orchestrator proposal and human approval
3. Registry update: set `status: deprecated` and `superseded-by: {new-ID}` on the old entry (or `superseded-by: null` if deprecated without replacement)
4. Update all `agents.md` files that reference the affected invariant
5. Reviewer notification — the reviewer must be aware that the old invariant is no longer enforced

**Four lifecycle operations:**
- **Loosen:** Create a new invariant with the relaxed rule. Deprecate the old entry and point `superseded-by` to the new ID. Both IDs appear in the governing ADR.
- **Split:** Deprecate the original invariant. Create two or more finer-grained entries. All new IDs trace back to the original via the ADR.
- **Deprecate:** No replacement. Set `status: deprecated`, `superseded-by: null`. ADR explains why the constraint is no longer needed.
- **Reclassify:** Change severity level. Update the registry directly. An ADR is required only when downgrading from critical (because critical invariants have special enforcement requirements).

Deprecated invariants remain in the registry for traceability but are not enforced by the reviewer.

### 7.5 Token Budget and Session Discipline

Encoded in persona definitions, not enforced mechanically:

**Orchestrator:**
- Read AGENTS.md frontmatter (YAML headers only) to build delegation plans — do not read full bodies until needed
- Delegate minimum necessary context per implementer
- Reference specific ADRs from frontmatter, not "all ADRs"
- Do not read application source code — delegate exploration tasks instead
- If reasoning about implementation details instead of delegation strategy, stop and delegate

**Implementer:**
- Read only: local agents.md, referenced ADRs (from frontmatter), persona file
- Do not read peer agents.md files, invariant registry, or session state

**Reviewer:**
- Read only: invariant registry entries for touched invariants, relevant agents.md frontmatter for scope validation
- Do not read ADRs unless an ambiguity in the registry requires rationale lookup

**Planner:**
- Read only: local agents.md, referenced ADRs
- Produce plans, not implementations — keep output concise

**Session management:**
- Checkpoint proactively at every milestone completion, not just when requested
- Extended sessions accumulate invisible state that degrades performance. Prefer fresh sessions at milestone boundaries: checkpoint, compact, and resume.
- Do not run a single orchestrator session through an entire project. Milestone boundaries are natural session boundaries.

### 7.6 Delegation Sizing Discipline

Review cost scales at least linearly with changeset size. A 5,000 LOC changeset can require 30–40 review cycles. The methodology addresses this through a changeset budget — a set of configurable LOC thresholds that govern how aggressively the orchestrator decomposes work before delegating.

**Changeset budget thresholds** (configured in `governance.changeset-budget` in `config.yaml`):

| Threshold | Default | Meaning |
|---|---|---|
| `target-loc` | 300 | Ideal maximum LOC per single implementer delegation. The orchestrator decomposes until each task is at or below this target. |
| `warn-loc` | 500 | Hard ceiling. If a task's estimated LOC exceeds this, the orchestrator **must** decompose further before delegating — no exceptions. |
| `planner-trigger-loc` | 400 | If estimated LOC exceeds this, the planner is invoked regardless of complexity score. |

**These are soft governance guidelines**, not mechanical blocks. The orchestrator enforces them through estimation and decomposition decisions. There is no hook that rejects a commit for being too large — the goal is to prevent large changesets from being produced in the first place.

**Pre-flight estimation protocol:**
Before every implementer delegation, the orchestrator estimates:
1. Files to be touched (count and paths)
2. Expected net LOC (new + modified lines)
3. Invariants at risk
4. Cross-scope dependencies

If estimated LOC > `target-loc`: decompose into smaller subtasks or invoke the planner.
If estimated LOC > `warn-loc`: this is a hard stop — decompose before delegating.
If estimated LOC > `planner-trigger-loc` and the planner was not already invoked: invoke the planner.

The estimate is logged in session state under the active delegation entry.

**Post-implementation LOC comparison:**
After each implementer reports, the orchestrator compares actual LOC against the pre-flight estimate logged in session state. This is diagnostic, not a gate — the review proceeds regardless of variance. Three rules:
1. If actual LOC exceeds `warn-loc`, log the variance in the governance journal.
2. If actual LOC consistently exceeds estimates for a scope (> 2x actual vs. estimated across 3+ tasks), recalibrate future estimates for that scope.
3. Persistent underestimation should trigger a planner review of scope decomposition strategy for that component.

**Why estimation over measurement:** Measuring LOC after the fact (post-implementation) is too late — the context has been spent, the large changeset exists, and review cost is already locked in. Estimation before delegation prevents the problem rather than detecting it.

### 7.7 Specification Update — `/armature-update`

ARMATURE.md is a living document. The orchestrator has authority to propose and apply specification changes through a structured protocol defined in `.claude/commands/armature-update.md`.

**When to use:** Adding new operational protocols, amending existing sections to fix ambiguities or gaps, adding schema fields, deprecating obsolete guidance.

**Key constraints:**
- Orchestrator-only action — implementers and reviewers cannot modify the specification
- Human approval is required before any change is applied
- Impact analysis identifying all downstream files (personas, config, templates, commands) is required
- All specification changes are logged in the governance journal
- After applying changes, section numbering and all cross-references must be verified

See `/armature-update` for the full step-by-step protocol.

### 7.8 Framework Backport — `/armature-backport`

When the canonical Armature repository evolves, projects using Armature need a way to pull in framework improvements without overwriting project-specific content. The `/armature-backport` command handles this.

**What gets updated (framework-generic):** ARMATURE.md, core personas (orchestrator, reviewer, reviewer-redteam, planner), templates, hooks, all commands (including backport itself), and core subagent wiring (reviewer, planner, redteam).

**What is preserved (project-specific):** config.yaml, invariant registry, invariants.md, implementer personas, CLAUDE.md, CODEX.md, root and scoped agents.md files, ADRs, journal, session state, reviews, implementer subagent wiring.

**Protocol summary:**
1. Compare `armature-version` between project and canonical source
2. Diff all framework-generic files and present changes to the human
3. Warn if any framework files have local modifications that will be lost
4. Apply updates with human confirmation
5. Check for schema migrations (new config/frontmatter/registry fields)
6. Update `armature-version` in project config
7. Run `post-stop.sh` to verify governance integrity
8. Log the backport in the governance journal

See `/armature-backport` for the full step-by-step protocol.

---

## 8. Schemas

### 8.1 .armature/config.yaml

```yaml
armature-version: "1.1.0"       # Armature methodology version

project:
  name: ""
  description: ""
  domain: ""

stack:
  languages: []
  frameworks: []
  databases: []
  infrastructure: []
  ci: ""

topology:
  # Component declarations — each becomes a scoped agents.md
  components:
    - path: src/component-a
      responsibility: ""
      adrs: []
    - path: src/component-b
      responsibility: ""
      adrs: []

governance:
  build-candidate-prefix: "bc"
  circuit-breaker-threshold: 3
  reviewer-required: true
  changeset-budget:
    target-loc: 300           # Ideal max LOC per implementer delegation
    warn-loc: 500             # Hard stop — must decompose before delegating
    planner-trigger-loc: 400  # Invoke planner if estimated LOC exceeds this
  ci-review-pipeline:
    enabled: false            # Enable automated PR review-fix cycle
    auth-method: "api-key"    # "api-key" | "github-app"
    model: "claude-sonnet-4-6"  # Claude model ID for CI fixes
    review-bots:              # Bots that trigger fix cycle
      - name: ""              # GitHub bot login (e.g., "greptile-apps[bot]")
        type: ""              # "score-gated" | "direct"
        score-threshold: 4    # For score-gated: minimum passing score
        score-pattern: ""     # Regex to extract score (e.g., "(\\d)\\s*/\\s*5")
        ack-emoji: ""         # For direct: emoji to check for acknowledgment
        ack-timeout: 20       # Seconds to wait for ack
        ack-retries: 5        # Max retry attempts
    final-reviewer: ""        # Bot to invoke after score gate passes
    final-reviewer-trigger: ""  # Comment text (e.g., "@codex review this")
    batch-wait-seconds: 60    # Seconds to collect comments before batching
    test-command: ""          # Test command after fixes (project-specific)
    max-turns: 15             # Max Claude conversation turns per fix
```

### 8.2 AGENTS.md Frontmatter

```yaml
---
scope: ""                    # Directory path this file governs
governs: ""                  # Brief description of responsibility
inherits: ""                 # Parent agents.md path
adrs: []                     # List of governing ADR identifiers
invariants: []               # List of invariant IDs from registry
enforced-by: []              # CI/runtime enforcement files
persona: implementer         # Persona type: implementer
authority: []                # Permitted actions: read, write, test, deploy
restricted: []               # Prohibited actions
test-scope: ""               # unit | integration | e2e | none
---
```

### 8.3 Invariant Registry Entry

```yaml
{CATEGORY}-{NNN}:
  name: ""
  severity: critical | high | standard
  status: active                 # active | deprecated
  superseded-by: null            # Invariant ID of replacement, or null
  description: ""
  rule: ""                   # Short imperative constraint statement
  defined-in: ""             # ADR path
  enforced-by:
    ci: []                   # Test file paths
    hooks: []                # Lifecycle hook script paths (PreToolUse, PostToolUse, Stop, etc.)
    startup: []              # Fail-fast guard paths
    runtime: []              # Runtime guard paths
  referenced-in: []          # agents.md and other governance file paths
  exceptions: []             # Approved exceptions with rationale and ADR reference
```

---

## 9. Degraded Mode

When no agentic workflow is active, the Armature scaffold serves as project documentation:

- `CLAUDE.md` / `CODEX.md` → project overview and navigation guide
- `agents.md` files → scoped development guidelines (YAML frontmatter is metadata; body is readable prose)
- `docs/adr/` → architectural decisions with rationale
- `.armature/invariants/invariants.md` → hard constraints in plain English
- `.armature/personas/` → role descriptions that double as team structure documentation

No governance mechanism depends exclusively on agent tooling. Every file is human-readable and useful without Armature's agentic workflow running.

---

## 10. Scaling Guidance and Future Considerations

### 10.1 Scaling Guidance

Armature is designed for single-developer agentic workflows, but projects vary in size. These guidelines help adapt the scaffold:

**Component count:**
- Up to ~10 components: flat structure in `personas/implementers/` works well
- 10–25 components: group related implementers under subdirectories; consider source-level agents.md files to reduce routing table noise
- Beyond 25: consider multi-repo architecture with per-repo scaffolds sharing a common invariant registry

**Invariant registry:**
- Up to ~50 invariants: single `registry.yaml` file
- 50–200 invariants: split into per-category files (e.g., `registry-schema.yaml`, `registry-runtime.yaml`) with a root index file; invariant IDs must remain globally unique regardless of partitioning
- Beyond 200: re-evaluate whether invariants are at the right abstraction level — many may be redundant or over-specified

**Changeset budget calibration:**
- Small repos (< 10k LOC): defaults work well (target: 300, warn: 500)
- Medium repos (10k–50k LOC): consider reducing target-loc to 200 and warn-loc to 350
- Large repos (> 50k LOC): per-scope budget overrides may be needed; repos with many cross-cutting concerns should increase circuit-breaker-threshold to 4–5

**Tool adapter routing tables:**
- Beyond ~15 entries: group by subsystem with section headings
- Beyond ~30 entries: extract to a separate `routing.yaml` file referenced by `CLAUDE.md` and `CODEX.md`
- Always keep the critical invariants section in tool adapters regardless of routing table size

**ADR numbering:** Use 4-digit IDs from the start (ADR-0001). Add `docs/adr/index.md` when count exceeds ~30.

### 10.2 Future Considerations (Deferred)

The following are explicitly deferred under the YAGNI principle:

- **Multi-user session isolation** — concurrent agentic sessions by different developers
- **Scaffold methodology versioning** — migration paths between Armature versions
- **Visual dependency graph generation** — from frontmatter cross-links
- **Automated tool adapter routing table generation** — from agents.md file discovery
- **Automated invariant registry validation** — contract test that validates registry against reality
- **Commercial distribution** — packaging Armature for other teams/organizations

These are acknowledged as valuable and designed-for (the structured frontmatter enables most of them), but not implemented until the need is real.
