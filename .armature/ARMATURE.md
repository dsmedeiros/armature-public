# Armature — Agentic Repository Management Architecture

**Version:** 1.2.0
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
│   ├── disciplines/                       ← Standards and disciplines corpus (§3.8)
│   │   └── triggers.yaml                  ← Machine-readable discipline trigger index (§3.9)
│   ├── antipatterns.md                    ← Antipattern catalog (§7.10)
│   ├── cascade-rules.yaml                  ← Cascade co-staging rules (§5.2.2, DRIFT-002)
│   ├── templates/
│   │   ├── agents.md.tmpl                 ← AGENTS.md skeleton
│   │   ├── adr.md.tmpl                    ← ADR template
│   │   ├── CODEX.md.tmpl                  ← Codex adapter template
│   │   ├── persona.md.tmpl                ← Implementer persona template
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
│       ├── check-required-reading.sh      ← PreToolUse(Edit|Write) required reading advisory
│       ├── check-cascade.sh                ← Cascade-rule evaluator (§5.2.2, DRIFT-002)
│       ├── precommit-cascade-gate.sh       ← PreToolUse(Bash) cascade co-staging gate
│       └── cascade-ci.sh                   ← Authoritative per-commit cascade backstop in CI (§5.3)
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
- For discipline trigger registration, see §3.9.

`.armature/invariants/invariants.md` is the human-readable companion — prose descriptions of each invariant grouped by category. It is generated from or manually kept in sync with the registry. In degraded mode (no agentic tooling), this is what a human reads.

### 3.8 Standards and Disciplines Corpus

`.armature/disciplines/` is an optional directory that holds standards files — named documents describing a body of practice that an agent should apply when working in a relevant context. Examples: `tdd.md` (test-driven development practice), `api-design.md` (REST surface conventions), `security.md` (threat-modeling checklist).

**Discipline definition.** A discipline is a tuple of three elements:

1. **Standards content** — the body of the discipline, declared as a Markdown file in `.armature/disciplines/`.
2. **Trigger conditions** — the rules that determine when the discipline applies to a given delegation, declared in `.armature/disciplines/triggers.yaml` (§3.9).
3. **Behavioral traits** — composable persona modifiers activated when the discipline fires, declared in persona files and composed at delegation time (§4.7, §4.8).

This structure mirrors the §3.7 invariant registry pattern: just as `registry.yaml` is the machine-readable index of governance constraints, `triggers.yaml` is the machine-readable index of discipline activation rules. Standards files are the payload; the trigger registry is the routing table.

**Injection model.** When a discipline trigger fires (see §3.9), `inject-context.sh` includes the corresponding standards file in the governance context delivered to the subagent at spawn time. The subagent receives the discipline as part of its activation context, not as a separate file read step. Standards files must be self-contained — they must not assume any prior state that the subagent did not receive at spawn time.

**When to create a discipline.** A discipline is appropriate when a body of practice:
- Applies conditionally (not always, but reliably under known conditions)
- Is specific enough to guide implementation decisions, not just state intent
- Would otherwise require the orchestrator to remember to mention it at each relevant delegation

If a standard applies to all delegations without exception, encode it in the relevant `agents.md` body instead.

**File naming.** Standards files use lowercase kebab-case with a `.md` extension (`tdd.md`, `api-design.md`). The filename is the discipline ID referenced by `triggers.yaml`. Discipline IDs must be unique within the corpus.

**Relationship to invariants.** Disciplines describe how to work; invariants describe what must always hold. A discipline may reference invariants (e.g., a TDD discipline references TDD-001), but disciplines are not enforced by hooks — they are guidance injected at the right moment, not constraints checked after the fact. Enforcement of discipline-derived invariants remains with the invariant registry.

---

### 3.9 Discipline Trigger Registry

`.armature/disciplines/triggers.yaml` is the machine-readable index mapping discipline IDs to their activation conditions. It governs when and how each discipline is composed into the active persona for a given delegation.

**Trigger types.** Each registry entry declares one or more trigger conditions using a hybrid model:

| Trigger type | Fires when |
|---|---|
| `path` | One or more files in the delegation scope match the declared path pattern (glob or regex) |
| `invariant` | The task annotation references one or more of the listed invariant IDs |
| `content` | A content pattern (regex) matches within the delegated changeset description or task annotation |
| `explicit` | The orchestrator adds the discipline ID directly to the task annotation via `discipline-tags` |

Rules-based triggers (`path`, `invariant`, `content`) fire automatically when the condition is satisfied. The orchestrator may always add disciplines explicitly via `explicit` tags regardless of whether any rule fired. This hybrid model ensures common cases are handled without orchestrator attention while preserving manual override.

**Composition.** Disciplines that fire for a given delegation are composed into the active persona per §4.7 and §4.8. The trigger registry entry carries a `composition-mode` field (`strict` or `advisory`) that controls how the discipline's behavioral traits bind to the persona: `strict` traits are mandatory behavioral constraints; `advisory` traits are recommended practices the agent may adapt. Conflict resolution between simultaneously active disciplines follows the rules in §4.8.

**Orchestrator pre-flight.** The orchestrator consults `triggers.yaml` during Phase C pre-flight (§5.1) when preparing each task delegation. It evaluates all rules-based triggers against the task metadata and annotates the task with the resulting discipline set before spawning the implementer. This evaluation is logged in session state alongside the LOC estimate.

**Schema.** The trigger schema is defined in §8.4. The trigger registry file must conform to that schema. `post-stop.sh` validates structural correctness of `triggers.yaml` when the file is present; an absent or empty triggers file is valid (no disciplines defined).

**Relationship to §3.8.** The trigger registry is the routing layer; the disciplines directory is the content layer. A discipline file in `.armature/disciplines/` with no corresponding entry in `triggers.yaml` is never injected. An entry in `triggers.yaml` referencing a discipline file that does not exist is a configuration error caught by `post-stop.sh`. The SDLC phase dimension of trigger conditions (blocking disciplines to specific phases) is described in §5.7.

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

Any persona in the table above may carry discipline trait decorators at delegation time, per §4.7. Traits modulate reasoning behavior but do not alter decision authority or edit scope.

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

**Marker and pending-advisory discipline (Phase A→Phase B bridge):**

Two session files coordinate the red-team gate across the SDLC phase boundary. Both live under the gitignored `.armature/session/` directory and are not committed governance artifacts.

- **Marker** — `.armature/session/red-team-<branch>.json`. Records the red-team verdict bound to a `content_fingerprint` (a commit-invariant hash of the changeset). Branch scoping is enforced by BOTH the path-derived slug (branch name with `/` replaced by `-`) AND an in-file `branch` field that the gate verifies against the current full branch name. The path alone is lossy under slash→hyphen normalization: `feature/foo-bar` and `feature/foo/bar` both map to `red-team-feature-foo-bar.json`, so the in-file `branch` field is authoritative to prevent cross-branch marker replay. A marker is valid when all three conditions hold: (1) `verdict` ∈ {APPROVED, PASS}, (2) the stored `content_fingerprint` matches the current working tree, and (3) the marker's `branch` field equals the current full branch name (un-normalized). A marker with an absent or mismatched `branch` field does NOT suppress — the gate remains triggered (fail-safe). A valid marker suppresses the HOOK-007 gate. The orchestrator MUST write the `branch` field (full un-normalized branch name) when writing a marker.

- **Pending-advisory** — `.armature/session/pending-red-team-<branch>.json`. The Phase A→Phase B bridge. The auto-reviewer (TASK-003) writes this file at SubagentStop when it determines a red-team trigger has fired for the changeset but the red-team review has not yet completed. The HOOK-007 gate (`pre-pr-create.sh`) reads this file to determine whether a trigger is active. The orchestrator clears it after writing a valid marker.

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

The orchestrator invokes the planner when: (a) task complexity > 7, OR (b) estimated LOC > `changeset-budget.planner-trigger-loc`. Simple, small, well-scoped changes go directly to an implementer without planning. **Exception:** trigger (b) does not apply to documentation-only changesets (prose docs with no governed/structural files); see the documentation-only fast path in §5.1.

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

**Documentation-only note:** prose-only changesets (rows 1–2, when no governed/structural file is touched) are exempt from the LOC-based planner trigger regardless of size — see the documentation-only fast path in §5.1.

---

### 4.7 Discipline Traits

A discipline trait is a composable behavioral modifier that binds to a base persona at delegation time. Traits extend how a persona reasons and acts; they do not alter decision authority, edit scope, or invariant veto power — those remain fixed by the base persona and scope governance. A trait is "composable" in the sense that multiple traits may be applied simultaneously, and their combined effect is predictable under the resolution rules in §4.8.

Traits are derived from disciplines (§3.8). When a discipline fires for a delegation, the traits it declares are activated alongside the standards content injection. A discipline without traits injects content only; a trait without discipline standards content is not valid.

**Canonical traits (M1).** The following traits are introduced by this specification amendment. The full discipline catalog and additional traits land in M4; M1 establishes the trait concept and the four traits that are immediately referenced by the invariants defined in this milestone.

| Trait ID | Composition mode | Severity | Description |
|---|---|---|---|
| `tdd-strict` | strict | high | Agent must write or update tests before writing implementation code; implementation proceeds only when a failing test exists |
| `phase-aware` | strict | high | Agent must check the active SDLC phase (§5.6) and refuse work that is blocked in the current phase |
| `tier0-gated` | strict | high | Agent must not modify tier-0 artifacts without explicit orchestrator authorization recorded in session state |
| `antipattern-aware` | advisory | standard | Agent consults `.armature/antipatterns.md` during planning; flags recognized antipatterns before execution |

**Severity** mirrors the severity vocabulary defined in §8.4 (`critical` | `high` | `standard`) and is inherited from the discipline's `severity` field in `triggers.yaml` (§8.4). The trait does not carry its own severity field; it inherits from the discipline that introduces it. Severity determines conflict resolution priority when multiple traits are simultaneously active (§4.8). `triggers.yaml` is authoritative for severity; the table above reflects canonical M1-era trait severities and may be overridden per-discipline when `triggers.yaml` is populated in M4.

**Declaration — persona files.** A persona file declares its supported composition modes via the `composition-mode` frontmatter field. This field is optional; an absent field means the persona accepts any trait in advisory mode and accepts strict traits only when the orchestrator has explicitly authorized them.

**Declaration — scope governance.** A scoped `agents.md` file declares expected discipline tags via the `discipline-tags` frontmatter field. Entries in this list tell the orchestrator which disciplines are pre-authorized for delegations within that scope. The orchestrator uses this list during Phase C pre-flight evaluation alongside the trigger registry.

**Cross-references.** The standards corpus backing each trait lives in §3.8. The trigger conditions that determine when a trait activates are declared in `triggers.yaml` per §3.9. SDLC-phase-driven trait activation — specifically how `phase-aware` and `tier0-gated` traits interact with the phase gate model — is described in §5.6.

---

### 4.8 Persona Composition

At delegation time, the orchestrator constructs a composed persona for the subagent. The composition formula is:

```
composed_persona = base_persona + scope_governance + N × discipline_traits
```

- **Base persona** provides fixed decision authority, edit scope, and behavioral baseline (§4.2 through §4.6).
- **Scope governance** (the scoped `agents.md`) provides the edit authority for the target directory. Scope owns edit authority; traits cannot expand it. When a strict trait mandates an action that the scope's authority forbids, the orchestrator must reject the delegation at pre-flight — it cannot silently degrade the trait's requirement, and it cannot expand scope to satisfy the trait.
- **Discipline traits** (§4.7) modulate reasoning, sequencing, and gate-checking behavior. Traits may add constraints but cannot remove constraints established by the base persona or scope governance.

**Resolution order.** Layers are applied in this sequence: base persona first, then scope governance, then traits in declaration order. A later layer may add a constraint not present in an earlier layer; it may not remove or weaken a constraint from an earlier layer. "Declaration order" is the sequence in which traits appear in the originating `discipline-tags` list when tags are explicit; when traits are auto-fired by trigger evaluation, declaration order is the sequence returned by sequential evaluation of `triggers.yaml` (top-to-bottom entry order).

**Conflict resolution.** When two active traits impose contradictory behavioral constraints, the more restrictive constraint wins — a constraint A is more restrictive than B when A's permitted set is a strict subset of B's permitted set (i.e., A allows fewer actions than B). The operational mechanism that implements this principle evaluates in the following order: severity comparison is authoritative first; the strict-subset test applies as a tie-breaker reasoning aid only when severity is equal but the constraints are otherwise comparable. When severity differs, the higher-severity trait's constraint takes precedence. When severity is equal, `strict` composition mode takes precedence over `advisory`. When both severity and composition mode are equal, the trait appearing earlier in the declaration order takes precedence.

The conflict resolution rule is stated once here and applies uniformly. There is no case in which a lower-severity trait overrides a higher-severity trait's constraint, and there is no case in which the declaration order alone overrides severity.

**Composition cap.** A delegation MUST carry at most four discipline traits. When the trigger evaluation would produce more than four active traits, the orchestrator MUST:

1. Select the four highest-severity traits (tie-broken by composition mode: `strict` before `advisory`, then declaration order).
2. Log the full evaluated trait set and the selection rationale in session state under "Invariants Touched."
3. Record which traits were deferred and why.

Exceeding four traits in a single delegation is a signal that the task should be decomposed further; the orchestrator should treat it as a decomposition advisory.

**Attribution.** Each delegation records the active trait set in session state for auditability. This attribution requirement is formalized as DISCIPLINE-001. The session state entry must include: the discipline IDs that fired, the composition mode of each, and whether any conflict resolution was applied.

**Cross-references.** Trait definitions: §4.7. Persona overview table: §4.1. The `discipline-id` values that appear in composed personas must be declared in `triggers.yaml`, whose schema is defined in §8.4.

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

**Documentation-only fast path (any size).** A changeset is *documentation-only* when **every** touched file is prose documentation and **none** is a governed/structural file. For such changesets the `planner-trigger-loc` and `target-loc` ceilings do **not** apply — work goes directly to an implementer and the reviewer regardless of size (subject to the `warn-loc` hard stop, which has no exceptions). Prose carries no logic or invariant surface, so decomposition adds little; the reviewer (never skipped) remains the quality gate.

- *Documentation (included):* `README*`, `CHANGELOG*`, `CONTRIBUTING*` and similar top-level narrative; anything under `docs/` **except** `docs/adr/`; `*.txt`, `*.rst`; `.armature/journal.md`.
- *Governed/structural (excluded — always take the normal path):* `.armature/ARMATURE.md` (SPEC-001/002); any `agents.md`/`AGENTS.md` (REF-001/003); `CLAUDE.md`, `CODEX.md` and their templates (ADAPTER-001); `.armature/invariants/registry.yaml` and `invariants.md` (SCHEMA-002, DRIFT-001/002); `.armature/config.yaml` (SCHEMA-001); `docs/adr/**` (REF-002); `.taskmaster/docs/**` (PRDs — they are the inputs that drive task decomposition, so a large PRD rewrite must retain full planning); `.armature/personas/**` and `.armature/disciplines/**`; `.armature/antipatterns.md`, `.armature/lessons.yaml`, `.armature/cascade-rules.yaml`, `.armature/ci.yaml`, and any other `.armature/` governance file not explicitly named in the *Documentation (included)* set above (they carry behavioral/governance surface — e.g. the antipattern catalog is consulted during planning and `lessons.yaml` is machine-read at injection); any code, hook, test, schema, or configuration file.

**Exclusions take precedence over inclusions, and the included set is a closed allowlist:** when a path matches both an inclusion glob (e.g. `*.txt`/`*.rst`/`docs/**`) and an exclusion (e.g. a PRD under `.taskmaster/docs/**`), it is treated as excluded. A changeset is documentation-only only if **every** touched file matches the *Documentation (included)* set above; touching even one excluded file — **or any file not in that included set** (default-deny, regardless of whether its contents happen to read as prose) — makes the changeset **not** documentation-only, and it follows the standard rules. The complexity > 7 trigger still applies (a rare structural documentation reorganization may still be planned at the orchestrator's discretion). This is a soft governance guideline (§7.6) enforced by orchestrator judgment — there is no mechanical hook.

**Phase A — Requirements:**
1. Human describes intent conversationally to the orchestrator
2. Orchestrator asks clarifying questions, confirms understanding
3. Orchestrator generates PRD, saves to `.taskmaster/docs/`, confirms with human

**Phase B — Planning (per milestone):**
4. Orchestrator decomposes PRD into milestones (5–10 working increments)
5. Orchestrator parses current milestone into Taskmaster tasks (via MCP `parse_prd` or `add_task`)
6. Orchestrator runs complexity analysis, expands complex tasks, annotates with scope
7. Orchestrator estimates LOC for each task. Tasks exceeding `changeset-budget.planner-trigger-loc` must route through the planner regardless of complexity score. Tasks exceeding `changeset-budget.warn-loc` must be decomposed into smaller subtasks before delegation. Documentation-only changesets are exempt from the `planner-trigger-loc` and `target-loc` routes (see §5.1); only the `warn-loc` hard stop still applies.
8. Orchestrator presents the plan to human for confirmation

For SDLC phase enforcement during execution, see §5.6.

**Phase C — Execution (per task):**
7. Orchestrator queries Taskmaster for next task
8. Orchestrator annotates task with target agents.md scope
9. **Pre-flight estimation:** Orchestrator estimates files to be touched, expected net LOC, invariants at risk, and cross-scope dependencies. If estimated LOC > `changeset-budget.target-loc` (and the changeset is not documentation-only — see §5.1), return to Phase B for further decomposition or planner invocation. Log the estimate in session state. As part of pre-flight, the orchestrator consults `.armature/disciplines/triggers.yaml` (§3.9) to determine the discipline trait set for the delegation, and the gates registry (§5.7) to identify which lifecycle gates are applicable to the current SDLC phase (§5.6). Both the trait set and the applicable gates are logged in session state alongside the LOC estimate.
10. If complexity > 7, OR (estimated LOC > `changeset-budget.planner-trigger-loc` and the changeset is not documentation-only — see §5.1), orchestrator invokes planner first
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
- Every invariant-shaped token (`[A-Z]{2,}[A-Z0-9]*-\d+`) in governed markdown resolves against the registry or matches the universal allowlist (DRIFT-001) — catches stale renames, typos, and dangling references in prose
- Conditional application test run: if `.armature/.code-dirty` marker exists, runs the project test suite and removes the marker on pass

In Codex and other tools without lifecycle wiring, `post-stop.sh` is run manually before handoff or via CI.

This is the only hook that may exceed one second of execution time, due to the conditional test suite invocation triggered by the `mark-dirty` integration.

#### 5.2.2 Pre-Tool-Use Guards (PreToolUse)

Three hooks gate destructive, under-informed, or inconsistency-producing tool use before it occurs:

- `block-dangerous-commands.sh` — Bash tool guard. Blocks destructive operations including: `rm -rf` on broad targets, `git push --force`, `git reset --hard`, `git clean -f`, `DROP TABLE` / `TRUNCATE`, `chmod -R 777`, `--no-verify` / `--skip-hooks`, bulk staging commands (`git add -A`, `git add -u`, `git add .`), `git checkout -- .`, `git restore .`, `git branch -D`, `git stash drop` / `git stash clear`, `dd if=`, `mkfs`, and fork bomb patterns. Allows `rm -rf` on safe targets such as `node_modules` and `__pycache__`. Prevents agent self-harm by catching commands that would bypass governance, destroy working state, or cause irreversible data loss.

- `precommit-cascade-gate.sh` — Bash tool guard enforcing cascade co-staging (DRIFT-002), the *best-effort first line of defense*. For commit-producing git subcommands (`commit`, `merge`, `cherry-pick`, `rebase`, `revert`, `am`) it determines the exact file set the command will land and delegates to `check-cascade.sh`, which evaluates that set against the rules in `.armature/cascade-rules.yaml`. A cascade rule declares that when a "trigger" file (matched by a `when_touched` glob) is in the changeset, its declared companions (`must_also_touch`, or `must_also_touch_same_dir` when `same_dir_roots` is configured) must be co-staged; a blocking violation exits 2 and stops the commit. The gate pre-flights compound commands (`git add <trigger> && git commit`), subshell scope, and prior `cd`; respects no-commit opt-outs; and bypasses recovery commands (`--abort` / `--quit` / `--skip`) so it never deadlocks the workflow. Because it runs *before* the command executes it cannot observe runtime file edits (e.g. `printf > trigger && git add trigger && git commit`); such forms are caught by the CI backstop below, not here. All non-commit Bash commands pass through (exit 0). Projects with no cascade rules omit the rules file (the checker SKIPs) or remove the gate wiring. The *authoritative* DRIFT-002 layer is `cascade-ci.sh` (§5.3), which evaluates `check-cascade.sh` per-commit against the actual committed changeset in CI, independent of command-string parsing.

- `pre-pr-create.sh` — Bash tool guard enforcing the red-team pre-PR gate (HOOK-007). Intercepts `gh pr create` commands and invokes the shared `red_team_check` lib to determine whether a red-team review was triggered for the current branch (via a pending-advisory file at `.armature/session/pending-red-team-<branch>.json`) and whether a valid marker file at `.armature/session/red-team-<branch>.json` already clears it. Marker validity requires: (1) verdict ∈ {APPROVED, PASS}, (2) the stored `content_fingerprint` matching the current working tree, and (3) the marker's `branch` field equaling the current full branch name — the in-file `branch` field is authoritative over the path slug because the slash→hyphen normalization is lossy (preventing cross-branch marker replay). When a trigger is present and no valid marker exists the hook advises by default (exit 0) or blocks with exit 2 when `ARMATURE_RED_TEAM_ENFORCE` is set to `1` or `true`. This hook is the Phase B enforcement complement to the auto-reviewer's Phase A advisory (TASK-003): auto-reviewer records the pending advisory at SubagentStop; this gate reads it at PR creation time and enforces (or warns) accordingly.

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

**Cascade backstop (DRIFT-002).** CI also runs `cascade-ci.sh`, the authoritative cascade-rule enforcer. It evaluates `check-cascade.sh` per-commit against the actual committed changeset (`base..head`), with no command-string parsing — so a cascade-violating commit fails CI regardless of how it was produced. This is the guarantee layer behind the best-effort `precommit-cascade-gate.sh` (§5.2.2): forms the PreToolUse gate cannot model (edit-before-stage, exotic shell operators) are caught here. Per-commit (not union) matches the atomic-landing semantics — each commit must carry a triggered rule's companions itself, so a violation cannot survive a later cherry-pick/revert of that single commit. Wired in `.github/workflows/governance.yml` (job `cascade-backstop`); downstream projects wire it during `/armature-init`.

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

### 5.6 SDLC Phases

Armature structures project work into six named SDLC phases. The active phase constrains which activities are permitted, which discipline traits auto-activate, and which lifecycle gates apply. Phase state is stored as a single-line file at `.armature/session/phase`, written by the phase-gate hook landing in M3. Phase transitions are logged in `.armature/journal.md` (§6.5) using the standard journal entry format.

**Phase definitions.**

| Phase | Permitted activities | Blocked activities | Who may enter | Who may exit |
|---|---|---|---|---|
| Discovery | Requirements gathering, PRD authoring, antipattern review, feasibility analysis | Code changes, test changes, spec amendments | Orchestrator on human request | Orchestrator when PRD is confirmed |
| Design | ADR authoring, schema design, milestone decomposition, planner invocation | Production code changes, bypassing review | Orchestrator after Discovery | Orchestrator after human plan confirmation |
| Implementation | Implementer delegation, test authoring, code changes, checkpoint commits | Bypassing reviewer, modifying tier-0 artifacts without authorization | Orchestrator after Design | Orchestrator on milestone complete or escalation |
| Review | Reviewer and red team invocation, verdict recording, re-delegation on FAIL | New implementation work during an open review cycle | Orchestrator after each implementation step | Orchestrator on reviewer PASS or FAIL resolution |
| Release | Build candidate tagging, version bump, adapter sync, backport | New feature work, spec amendments | Orchestrator after all milestone tasks pass review | Orchestrator after release artifacts committed |
| Hotfix | Targeted fix under bypass protocol (§7.9), audit trail creation | Scope expansion beyond the declared incident, skipping post-mortem trigger | Orchestrator on human-declared incident | Orchestrator after fix committed and post-mortem triggered |

**Phase transitions.** Transitions are initiated by the orchestrator and must be recorded in the journal (§6.5) before any work begins under the new phase. No agent other than the orchestrator may write to `.armature/session/phase`. A subagent that encounters a phase-prohibited activity must refuse and report to the orchestrator rather than silently skip or adapt the work.

**Phase-trait activation.** The following discipline traits (§4.7) are automatically activated for every delegation in the named phases. Additional traits may fire via trigger rules (§3.9); the phase-based activations listed here are additive.

| Phase | Auto-activated traits |
|---|---|
| Discovery | `phase-aware`, `antipattern-aware` |
| Design | `phase-aware`, `antipattern-aware` |
| Implementation | `phase-aware`, `tdd-strict`, `tier0-gated` |
| Review | `phase-aware` |
| Release | `phase-aware`, `tier0-gated` |
| Hotfix | `phase-aware`, `tier0-gated` |

`phase-aware` activates in all phases because the phase-gate check is a precondition for any delegation. `tdd-strict` activates specifically in Implementation because that is the only phase where implementation code is produced. `antipattern-aware` activates in Discovery and Design, where antipattern recognition informs requirements and architectural choices before constraints are committed. This phase-scoped activation is the primary mechanism that limits strict-trait conflicts: a strict trait is only active in the phases where its mandate is executable within the scope's authority. When a strict trait's mandate cannot be satisfied within the scope's authority even in the appropriate phase, the pre-flight rejection rule in §4.8 applies.

**Relationship to gates.** Phase state is the primary input consumed by the phase gate (GATE-PHASE-001), which enforces PHASE-001. The gates registry (§5.7) enumerates which gates are applicable per phase. The orchestrator queries both the phase state and the gates registry at Phase C pre-flight (§5.1).

**Cross-references.** Trait definitions: §4.7. Composition rules: §4.8. Trigger registry phase dimension: §3.9. Gate definitions: §5.7. Phase transition journal protocol: §6.5.

**Legal phase transitions.** The following table specifies which destination phases are reachable from each source phase and the condition that must hold before the orchestrator may initiate the transition. Every transition must be recorded in the journal (§6.5) before work begins under the destination phase.

| From | To | Condition |
|---|---|---|
| Discovery | Design | PRD confirmed by human |
| Design | Implementation | Implementation plan confirmed by human |
| Implementation | Review | Implementer reports completion of a delegation |
| Review | Implementation | Reviewer verdict is FAIL; orchestrator re-delegates the task |
| Review | Release | Reviewer verdict is PASS and all milestone tasks are accepted |
| Release | Discovery | Next milestone initiated by human |
| Release | (terminal) | Project complete; no further milestones planned |
| Hotfix | (prior phase) | Fix committed and post-mortem triggered; orchestrator restores the phase that was active at incident declaration |
| Hotfix | Discovery | No prior phase was active at incident declaration (e.g., incident occurs at project start) |
| (any) | Hotfix | Human declares a production incident requiring gate bypass per §7.9 |
| Hotfix | Hotfix | **Prohibited** (enforced behaviorally by the orchestrator per this transition table; no hook fires on attempted re-entry — the orchestrator refuses the transition). A concurrent incident during an active Hotfix is treated as scope expansion of the existing bypass; the orchestrator appends a referencing entry to the open bypass-intent record (§7.9) rather than opening a new lane entry. |

Hotfix is the only phase that may be entered from any other phase. It is also the only phase whose exit destination depends on runtime state (the phase recorded at incident declaration). The orchestrator must record the active phase in the bypass-intent journal entry (§7.9) so that the return destination is unambiguous at post-mortem close.

### 5.7 Gates Registry

A lifecycle gate is a named enforcement point that blocks or advises against a transition or action when a specified condition is not met. Gates are the bridge between the persona behavioral layer (§4.2–§4.8) and the mechanical hook layer (§5.2): they define what must hold; hooks implement the check.

**Gate record schema.** Each gate entry carries:

| Field | Description |
|---|---|
| `gate-id` | Unique identifier (e.g., `GATE-TDD-001`) |
| `lifecycle-event` | The pipeline step or hook event that triggers evaluation (e.g., `PreToolUse(Bash)`, `task-delegation`, `build-candidate-tag`) |
| `phase-applicability` | Which SDLC phases (§5.6) this gate is active in; `all` means every phase |
| `mode` | `blocking` — gate failure prevents the action; `advisory` — gate failure produces a warning but does not block |
| `hook-script` | Path to the hook script that implements the check; `planned` if the script lands in a later milestone |
| `governing-invariant` | The invariant ID this gate enforces |

The `advisory` value in the `mode` field is the gate-enforcement disposition (failure warns but does not block); it is unrelated to the composition-mode `advisory` in §4.7/§4.8 (trait is a recommendation the agent may adapt).

**Enumerated gates (M1 registry — hook scripts land in M3/M5/M7/M8).**

| Gate ID | Lifecycle event | Phase applicability | Mode | Hook script | Governing invariant |
|---|---|---|---|---|---|
| `GATE-TDD-001` | `task-delegation` | Implementation | blocking | `planned (.armature/hooks/tdd-gate.sh, M3)` | TDD-001 |
| `GATE-TIER0-001` | `PreToolUse(Edit,Write)` | all | blocking | `planned (.armature/hooks/tier0-preflight.sh, M3)` | TIER0-001 |
| `GATE-PHASE-001` | `task-delegation` | all | blocking | `planned (.armature/hooks/phase-gate.sh, M3)` | PHASE-001 |
| `GATE-TASK-001` | `task-delegation` | all | blocking | `planned (.armature/hooks/task-readiness.sh, M5)` | TASK-001 |
| `GATE-TASK-002` | `SubagentStop` | all | advisory | `planned (.armature/hooks/task-completion.sh, M5)` | TASK-002 |
| `GATE-TASK-003` | `task-delegation` | all | blocking | `planned (.armature/hooks/auto-reviewer.sh, M5)` | TASK-003 |
| `GATE-CI-001` | `build-candidate-tag` | Release | blocking | `planned (.armature/hooks/post-stop.sh extension, M7)` | CI-001 |
| `GATE-HOTFIX-001` | `task-delegation` | Hotfix | blocking | `planned (.armature/hooks/hotfix-audit.sh, M8)` | HOTFIX-001 |

**Gate semantics (one-line per gate).**

- `GATE-TDD-001` — Requires a failing test to exist before implementation code may be written in the Implementation phase.
- `GATE-TIER0-001` — Requires explicit orchestrator authorization in session state before any write to a tier-0 artifact.
- `GATE-PHASE-001` — Requires the current SDLC phase (§5.6) to permit the requested activity before delegation proceeds.
- `GATE-TASK-001` — Requires the task to have a resolved scope annotation and dependency chain before delegation.
- `GATE-TASK-002` — Advises when a task's declared done-criteria are not all verifiable at stop time.
- `GATE-TASK-003` — Requires a reviewer to be queued for every delegation that produces a changeset.
- `GATE-CI-001` — Requires CI to pass on the build candidate commit before the release phase may complete.
- `GATE-HOTFIX-001` — Requires a bypass-intent record (audit trail) to be present in the journal before a hotfix delegation may proceed.

**Orchestrator consultation.** The orchestrator consults this registry at Phase C pre-flight (§5.1) to determine which gates are active for the current SDLC phase and lifecycle event. Gates in `blocking` mode that evaluate to FAIL cause the orchestrator to reject the delegation and report to the human. Gates in `advisory` mode that evaluate to FAIL are logged in session state but do not block the delegation.

**Override protocol.** A blocking gate may be bypassed only via the hotfix lane (§7.9). Bypasses produce an audit trail entry in `.armature/journal.md` and trigger a post-mortem. No gate may be bypassed silently; all bypasses are visible in the governance record.

**Cross-references.** Phase context consumed by gates: §5.6. Trigger conditions that may reference gate IDs: §3.9. Mechanical hook implementation: §5.2. Orchestrator pre-flight where gates are consulted: §5.1. Hotfix bypass protocol: §7.9.

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

**Checkpoint protocol** (step numbers match the `/checkpoint` skill's `### Step N` headings):
1. Orchestrator updates `.armature/session/state.md` with full current status
2. Orchestrator syncs with Taskmaster (all task statuses current)
3. Orchestrator verifies the governance journal is current
4. Orchestrator confirms the current build candidate tag
5. Orchestrator runs a **memory-consolidation pass** — when the project uses a persistent agent-memory store (the external per-project memory store defined in `/resolve` Phase 6), the orchestrator enforces a hard budget gate that keeps the memory index (`MEMORY.md`) within the runtime's memory-load budget, ensuring every indexed entry remains visible at session start. The budget-gate verification runs on **every** checkpoint where a memory store exists; it is never deferred. What is need-driven is the **clustering work**: active consolidation is required when any trigger applies (new banks, near-budget pressure, lingering stopgaps from a prior checkpoint, or an un-clustered backlog — see `/checkpoint` Step 5 for the authoritative trigger set); when no trigger applies the step is a verified no-op — the orchestrator confirms the index is under budget and records that confirmation without fabricating clustering work. See `/checkpoint` Step 5 for the operational protocol.
6. Human may safely run `/compact`

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
8. Scans `.armature/journal.md` for unclosed bypass-intent records — a bypass-intent entry is unclosed if no matching post-mortem closure entry referencing the same bypass-intent timestamp exists. Any unclosed record must be surfaced to the human before any new normal-phase task begins.

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
9. If complexity > 7, OR (estimated LOC > `changeset-budget.planner-trigger-loc` and the changeset is not documentation-only — see §5.1), invoke the planner persona first
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

**Documentation-only exemption:** changesets that touch only prose documentation (and no governed/structural file) are exempt from `planner-trigger-loc` and `target-loc` regardless of size — see the documentation-only fast path in §5.1. The reviewer still runs.

**Pre-flight estimation protocol:**
Before every implementer delegation, the orchestrator estimates:
1. Files to be touched (count and paths)
2. Expected net LOC (new + modified lines)
3. Invariants at risk
4. Cross-scope dependencies

If estimated LOC > `target-loc` (unless the changeset is documentation-only — §5.1): decompose into smaller subtasks or invoke the planner.
If estimated LOC > `warn-loc`: this is a hard stop — decompose before delegating (no exceptions, including documentation-only).
If estimated LOC > `planner-trigger-loc` and the planner was not already invoked: invoke the planner (unless the changeset is documentation-only — §5.1).

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

### 7.9 Hotfix Lane

The hotfix lane is a controlled gate-bypass protocol for production incidents. It is not a general escape hatch. Every use of the hotfix lane produces a mandatory audit record and triggers a post-mortem obligation. Hotfix bypasses gates; it does not bypass the reviewer.

**Conditions for use.** The hotfix lane may be invoked only when:
1. A human has declared a production incident by explicit instruction to the orchestrator.
2. The normal review cycle cannot meet the required fix delivery time.

The orchestrator does not self-declare incidents. If the orchestrator concludes that a situation warrants hotfix treatment, it surfaces the recommendation and awaits explicit human authorization before proceeding.

**Audit protocol.** The orchestrator executes the following sequence, in order:

1. **Transition to Hotfix phase.** Orchestrator writes the Hotfix phase to `.armature/session/phase` and records the active prior phase in the bypass-intent journal entry so the return destination is unambiguous at post-mortem close. Phase transition rules in §5.6 apply.
2. **Write bypass-intent record.** Before overriding any gate, the orchestrator appends a bypass-intent entry to `.armature/journal.md` (§6.5) using the standard journal entry format. The journal is append-only (§6.5); when a subsequent event requires updating a prior bypass-intent record — such as a concurrent incident treated as scope expansion per §5.6 — the orchestrator appends a new referencing follow-up entry that cites the original entry's timestamp and declares the updated status, rather than editing the original. This referencing entry supersedes the prior entry's status field while preserving the original record intact. The entry must include:
   - Incident reference (identifier or description provided by the human)
   - Gates being bypassed (list of gate IDs from §5.7)
   - Expected scope of the fix (files, components, and boundaries)
   - The human who authorized the bypass (by name or session identifier)
3. **Implementer executes targeted fix.** The delegated implementer works within the declared scope. Any change outside the declared scope must be refused and escalated; scope expansion is a blocked activity in the Hotfix phase (§5.6).
4. **Reviewer runs without exception.** The reviewer (§4.4) evaluates the fix against all active invariants. Hotfix bypasses lifecycle gates; it does not bypass review. The reviewer's verdict is recorded in the same session before the fix is committed. On a FAIL verdict, the orchestrator MUST: (a) record the FAIL in `.armature/journal.md`; (b) not commit the failed work; and (c) either remediate by re-delegating the fix to the implementer within the same declared scope, or escalate to the human per §6.6 if the contradiction cannot be resolved within the incident scope.
5. **Commit uses hotfix prefix.** Commits follow the standard format (§6.3) with a `hotfix-` prefix: `hotfix-task-{id}: {title}`. This prefix makes hotfix commits identifiable in the git history.
6. **Post-mortem is mandatory.** Before the next normal-phase task begins, the orchestrator runs the `/postmortem` command (M6). The post-mortem creates an entry in `.armature/antipatterns.md` (§7.10) and closes the audit trail opened by the bypass-intent record. Normal-phase work is blocked until the post-mortem entry is committed (enforced by HOTFIX-001).

**Trait set during Hotfix.** During the Hotfix phase, discipline traits activated automatically via §3.9 `path`, `content`, or `invariant` trigger conditions are suspended; only the trait set declared explicitly in the bypass-intent record applies. This ensures the declared incident scope governs the delegation rather than trigger evaluation producing additional `strict` constraints that could conflict with `GATE-HOTFIX-001`. The `explicit` trigger type (§3.9) remains available for the orchestrator to add traits deliberately.

Build candidates may still be tagged from hotfix commits per §6.4, provided the reviewer has issued a PASS verdict.

**HOTFIX-001 invariant.** A hotfix bypass must produce a bypass-intent audit record in `.armature/journal.md` before any gate is overridden, and normal-phase task delegation must be blocked until the post-mortem entry is committed to `.armature/antipatterns.md`. Severity: high (enforcement hook planned for M8). Bypassing the bypass-intent record requirement — that is, overriding a gate without first writing the journal entry — is a governance violation regardless of incident urgency.

**Cross-references.** Hotfix SDLC phase definition and entry/exit conditions: §5.6. Gate override mechanics: §5.7. Build candidate tagging from hotfix commits: §6.4. Journal entry format: §6.5. Antipattern catalog and post-mortem output: §7.10. The invariant IDs are not section references and do not implicate SPEC-002.

### 7.10 Antipattern Catalog

The antipattern catalog is the project's institutional memory of recurring failure modes — patterns of bug, mis-design, or governance violation that have manifested in practice and that future work should recognize and avoid.

**File.** The catalog lives at `.armature/antipatterns.md`. The file is append-only; entries are never removed or edited after they are committed. Corrections are made by appending a follow-up entry that references the entry being superseded.

**Entry structure.** Each catalog entry contains:

| Field | Description |
|---|---|
| Title | Short, scannable name for the antipattern |
| Date | ISO date the entry was committed |
| Originating incident or postmortem | Reference to the incident or session that produced the entry |
| Observed failure pattern | Description of what went wrong and how it manifested |
| Recommended counter-pattern | Concrete alternative behavior or design that avoids the failure |
| Related ADRs and invariants | References to architectural decisions and invariant IDs that bear on this pattern |

**Creation paths.** A catalog entry is created by one of two mechanisms:

1. `/postmortem` command (landing in M6) — automatically invoked after the hotfix lane closes (§7.9). The command generates a structured entry from the incident record, the bypass-intent journal entry, and the fix changeset. This is the primary creation path.
2. Manual append — the orchestrator may write an entry proactively when learning from an external incident, a code review finding, or a recurring pattern observed across tasks. Manual entries follow the same structure as post-mortem entries. Concurrent writes to the antipattern catalog are not coordinated by the spec — the orchestrator owns the append operation; manual edits should happen only when no orchestrator session is active.

**Orchestrator consults the catalog during Discovery.** The `antipattern-aware` discipline trait (§4.7) activates in the Discovery and Design phases (§5.6). When this trait is active, the orchestrator or delegated agent scans `.armature/antipatterns.md` for entries relevant to the current task before requirements are finalized or architectural choices are committed. Recognized antipatterns are flagged in session state and surfaced to the human as part of Discovery output.

The term "failure pattern" in this section refers to a recurring mis-design or governance violation observed in project history. This is distinct from the trigger conditions and trigger types (`path`, `invariant`, `content`, `explicit`) defined in §3.9, which are machine-readable activation conditions in `triggers.yaml` that determine when a discipline fires.

**Cross-references.** Hotfix lane — primary creation trigger: §7.9. Antipattern-aware trait definition: §4.7. Discovery phase where catalog is consulted: §5.6. Journal entry format (append-only, committed): §6.5.

---

## 8. Schemas

### 8.1 .armature/config.yaml

```yaml
armature-version: "1.2.0"       # Armature methodology version

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
    final-reviewer: ""        # Bot login to invoke after score gate passes
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
  planned-enforcement: []    # Planned enforcement targets for invariants whose hooks land in a later milestone; pairs with empty enforced-by lists
  referenced-in: []          # agents.md and other governance file paths
  exceptions: []             # Approved exceptions with rationale and ADR reference
```

The `planned-enforcement` field is optional. It documents hook scripts or CI targets that will enforce this invariant in a future milestone when `enforced-by` lists are empty. It carries no runtime effect — it is an audit trail field that prevents mistaking an unhooked invariant for one intentionally left unenforced. The `planned-enforcement` field should be cleared once the entries in `enforced-by` cover all planned mechanisms.

### 8.4 Discipline Trigger Schema

`.armature/disciplines/triggers.yaml` must conform to this schema. Each key is a discipline ID matching a `.md` file in `.armature/disciplines/`.

```yaml
triggers:
  {discipline-id}:                    # Matches filename in .armature/disciplines/ (no extension)
    severity: critical | high | standard  # Determines blocking behavior when trigger fires
    composition-mode: strict | advisory   # strict = mandatory traits; advisory = recommended traits
    triggers:
      - type: path                    # path | invariant | content | explicit
        pattern: ""                   # Glob or regex for path; invariant ID for invariant;
                                      # regex for content; discipline-id for explicit
      - type: invariant
        pattern: []                   # List of invariant IDs that activate this discipline
      - type: content
        pattern: ""                   # Regex matched against task annotation / changeset description
      - type: explicit
        pattern: ""                   # Discipline ID; fires when orchestrator sets discipline-tags
```

**Field documentation:**

| Field | Required | Values | Description |
|---|---|---|---|
| `discipline-id` | Yes | kebab-case string | Matches the filename stem of the standards file in `.armature/disciplines/` |
| `severity` | Yes | `critical` \| `high` \| `standard` | Controls whether the orchestrator must resolve a trigger conflict before delegating |
| `composition-mode` | Yes | `strict` \| `advisory` | Binds traits as mandatory constraints (`strict`) or recommended guidance (`advisory`) |
| `triggers[].type` | Yes (when `triggers` is non-empty) | `path` \| `invariant` \| `content` \| `explicit` | Activation mechanism; multiple entries within one discipline are OR-combined |
| `triggers[].pattern` | Yes (when `triggers` is non-empty) | string or list | Pattern interpretation varies by type; see schema comments above |

An entry with no `triggers` list is valid and acts as an always-on discipline (fires for every delegation). Use sparingly — prefer `agents.md` body content for universal guidance.

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
