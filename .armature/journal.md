# Armature Governance Journal

Append-only log of governance-relevant events.

---

### 2026-04-01 — initialization
Armature scaffold applied to its own repository (dogfooding).
Pre-init baseline: existing scaffold from extraction + improvements.
Components: .armature/ (specification), .claude/commands/ (protocols), .claude/agents/ (wiring)
ADRs: 1 (ADR-0001: governance as files)
Invariants: 6 (SPEC-001, SPEC-002, SCHEMA-001, SCHEMA-002, REF-001, REF-002)

### 2026-04-11 - codex-adapter
Added first-class Codex support as a tool adapter layer.
Artifacts: CODEX.md, CODEX.md template, ADR-0002, adapter invariants, protocol/spec updates.
Version: 1.1.0

### 2026-06-08 — 1.2.0: mechanical enforcement and authoring discipline
Major framework build-out since 1.1.0, developed and dogfooded on Armature itself:
- **Lifecycle hook suite.** Mechanical enforcement across the SDLC — TDD gate,
  phase gate, tier-0 preflight, task readiness/completion, auto-reviewer, CI
  runner, cascade gate, and a red-team pre-PR gate (HOOK-007) — backed by a
  comprehensive pytest suite.
- **Discipline corpus** (`.armature/disciplines/`): SDLC phases, clean code,
  testing standards, security (OWASP), error handling, typing, and more,
  surfaced contextually to agents.
- **Operational protocols:** `/resolve` (PR review-thread resolution),
  `/postmortem` (hotfix audit trail), and `/spec`.
- **Governance data:** expanded invariant registry, cascade rules (DRIFT-002),
  the antipattern catalog, and a harness-feedback lessons corpus.
- **Memory consolidation** added to the checkpoint protocol.
Version: 1.2.0
