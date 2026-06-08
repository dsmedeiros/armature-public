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

**HOOK-007 — Red-Team Pre-PR Gate** (standard)
Rule: The `pre-pr-create.sh` hook intercepts `gh pr create` on PreToolUse(Bash) and blocks (exit 2, when `ARMATURE_RED_TEAM_ENFORCE` is set to `1` or `true`) or advises (exit 0, default) when a red-team trigger fired for the current branch but no valid red-team marker exists.
Rationale: The auto-reviewer (TASK-003) flags a red-team trigger in Phase A (SubagentStop), but prior to HOOK-007 nothing prevented opening a PR in Phase B without acting on that advisory. This gate closes the Phase A→Phase B gap. Advisory-by-default allows soft deployment and zero disruption to existing workflows; operators opt into blocking enforcement via `ARMATURE_RED_TEAM_ENFORCE`, giving teams a graduated adoption path.
Enforcement: `pre-pr-create.sh` on PreToolUse(Bash); consumes the shared `red_team_check` lib's marker validation (verdict, content_fingerprint, branch). The lib checks for a valid marker file at `.armature/session/red-team-<branch>.json` — valid means verdict ∈ {APPROVED, PASS}, fingerprint matches the current working tree, and the branch matches.

## Lifecycle Gates

**TDD-001 — Test-Driven Development Gate** (high)
Rule: Source file edits require a matching test file to exist.
Rationale: Untested code silently accumulates technical debt and regression risk. A gate that blocks source edits without a corresponding test file makes the TDD obligation mechanical rather than advisory, surfacing it at the moment it can be satisfied.
Enforcement: `tdd-gate.sh` (planned, M3). No mechanical enforcement until M3; currently advisory.

**PHASE-001 — SDLC Phase Gate** (high)
Rule: Edits must be permitted by the current SDLC phase.
Rationale: Phase discipline prevents implementation work during design phases, code changes during review freezes, and ad-hoc commits during release windows. A gate that reads the current phase state and blocks prohibited activities makes phase adherence enforceable rather than relying on agent recall.
Enforcement: `phase-gate.sh` (planned, M3). No mechanical enforcement until M3; current phase stored at `.armature/session/phase`.

**TIER0-001 — Tier-0 Preflight** (high)
Rule: DOMAIN.md and PROJECT.md must exist at repo root.
Rationale: The orchestrator requires domain and project context before it can make governance-aware delegation decisions. Absent these files the orchestrator has no authoritative source for project intent, technology choices, or stakeholder expectations, leading to governance-blind execution.
Enforcement: `tier0-preflight.sh` (planned, M3). No mechanical enforcement until M3.

**TASK-001 — Task Readiness Gate** (standard)
Rule: Tasks must have acceptance criteria before delegation.
Rationale: Delegating a task without acceptance criteria gives the implementer no objective measure of completion. This creates ambiguity in reviewer verdicts, risks rework loops, and allows work to close without satisfying the original intent.
Enforcement: `task-readiness.sh` (planned, M5). No mechanical enforcement until M5.

**TASK-002 — Task Completion Gate** (standard)
Rule: Deliverables must be auto-verified against acceptance criteria.
Rationale: Manual completion checks are inconsistent and subject to optimism bias. Auto-verification against the acceptance criteria recorded at task-readiness time closes the loop mechanically and makes the completion decision auditable.
Enforcement: `task-completion.sh` (planned, M5). No mechanical enforcement until M5.

**TASK-003 — Auto-Reviewer Gate** (standard)
Rule: Reviewer and (when triggered) red team must auto-fire on SubagentStop.
Rationale: Requiring the orchestrator to manually invoke the reviewer after every subagent stop creates a process gap — review can be skipped under time pressure or forgotten during recovery. Auto-firing on SubagentStop makes the review loop invariant.
Enforcement: `auto-reviewer.sh` (planned, M5). No mechanical enforcement until M5.

**CI-001 — CI Pipeline Gate** (high)
Rule: Full CI pipeline (tests + types + lint + invariants) must run on Stop when code is dirty.
Rationale: Code that exits a session without passing CI can silently introduce failures that compound across sessions. Gating Stop on a dirty marker ensures no code change closes without machine verification, making CI a session invariant rather than a repository-level convention.
Enforcement: Extension of `post-stop.sh` (planned, M7). Partial enforcement via existing `post-stop.sh` governance checks; full CI integration lands in M7.

**HOTFIX-001 — Hotfix Audit Trail** (high)
Rule: Hotfix bypass must produce an audit record and block subsequent normal-phase work until postmortem lands.
Rationale: Hotfix lanes exist to enable rapid response to critical production issues but are inherently ungoverned departures from the SDLC. Without a mandatory audit record and postmortem gate, hotfixes become normalized shortcuts that erode phase discipline and accumulate unreviewed changes.
Enforcement: `hotfix-audit.sh` (planned, M8). No mechanical enforcement until M8; severity stays `high` until enforcement is wired.

## Engineering Disciplines

**DISCIPLINE-001 — Discipline Tag Definition** (standard)
Rule: Persona discipline tags declared in agents.md frontmatter must be defined in the standards corpus.
Rationale: An undefined discipline tag creates a false governance claim — the orchestrator believes a discipline is active when no corresponding standards file exists to define its traits or trigger conditions. References to undefined disciplines silently degrade governance coverage.
Enforcement: Orchestrator protocol (no script). The orchestrator must validate discipline-tags against `.armature/disciplines/` during delegation planning.

## Doc-Drift Guardrails

**DRIFT-001 — Invariant-ID Resolution** (standard)
Rule: Every invariant-shaped token (`[A-Z]{2,}[A-Z0-9]*-\d+`) appearing in governed markdown must resolve against the registry, match a universal allowlist pattern (ADR refs, PR refs, checkpoint / cycle / severity codes, well-known technical standards, spec-illustrative placeholders), or be amended into both — a registry entry for new invariants, an allowlist pattern for new non-invariant nomenclature.
Rationale: Stale renames, typos, and dangling references silently accumulate in governance prose. A check that flags every invariant-shaped token catches three failure modes the routing-table and frontmatter checks miss: (1) an invariant renamed in the registry but still cited in CLAUDE.md or an ADR by its old name; (2) a future invariant ID cited speculatively in a postmortem or design doc but never registered; (3) a domain-specific finding-code series (e.g. `CTX-NN-XXX`) that should have been added to the allowlist before being used. The check runs at post-stop, so drift is visible at every session boundary rather than only at human review.
Enforcement: `.armature/hooks/post-stop.sh` section 9 — scans `.armature/**.md` (excluding `session/`, `escalations/`, `reviews/`, `postmortems/`), `docs/adr/*.md`, every `agents.md` / `AGENTS.md` (excluding `.claude/worktrees/`), and top-level `CLAUDE.md` / `CODEX.md` / `AGENTS.md` / `PROJECT.md` / `DOMAIN.md` / `README.md` when present. Unknown tokens FAIL with exit 1.

**DRIFT-002 — Cascade Co-Staging** (standard)
Rule: When a file matching a cascade rule's `when_touched` pattern is part of a changeset, that rule's declared companions (`must_also_touch` and, when `same_dir_roots` is configured, `must_also_touch_same_dir`) must be part of the same changeset. The canonical rule (`registry-invariants-cascade`) pairs `.armature/invariants/registry.yaml` with `.armature/invariants/invariants.md` so the machine-readable index and the human-readable constraint list always land together.
Rationale: Some artifacts are coupled — a schema and its docs, a registry and its prose mirror, a manifest and its checksums — such that landing one without the other leaves the repository internally inconsistent. Path-based edit gates (TDD, phase, tier-0) operate file-by-file and cannot see this cross-file coupling. A cascade rule enforces *co-staging* (not correctness): it guarantees the companion was touched in the same changeset, and the reviewer assesses whether the companion change is adequate. Rules are kept to genuinely coupled artifacts so they do not force no-op edits.
Enforcement is two-layer (defense in depth):
- **Authoritative — CI backstop.** `.armature/hooks/cascade-ci.sh` runs in CI (`.github/workflows/governance.yml`, job `cascade-backstop`) and evaluates `check-cascade.sh` **per-commit** against the actual committed changeset (`base..head`), with no command-string parsing. This is the layer that guarantees the invariant: a cascade-violating commit fails CI regardless of how it was produced (including forms the PreToolUse gate cannot model — e.g. edit-before-stage `printf … > trigger && git add trigger && git commit`).
- **Convenience — PreToolUse gate.** `.armature/hooks/precommit-cascade-gate.sh` (PreToolUse(Bash), exit 2 blocks the commit) delegates to `check-cascade.sh` to catch violations *before* they are committed, pre-flighting the file set each commit-producing git form will land (including compound `git add … && git commit`, subshell scope, and prior `cd`) and bypassing recovery commands (`--abort` / `--quit` / `--skip`). It is best-effort: because it runs before the command executes it cannot observe runtime file edits, so it is a fast first line of defense, not the guarantee — the CI backstop is.

`check-cascade.sh` evaluates `.armature/cascade-rules.yaml` and is runnable manually (`bash .armature/hooks/check-cascade.sh --staged-only`). Downstream projects wire the PreToolUse(Bash) gate and the CI backstop via `/armature-init`.
