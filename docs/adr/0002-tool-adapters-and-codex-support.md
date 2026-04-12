# ADR-0002: Tool Adapters and Codex Support

**Status:** Accepted
**Date:** 2026-04-11
**Supersedes:** N/A

## Context

Armature's core governance model is intentionally portable: root and scoped `agents.md` files, ADRs, the invariant registry, and persona definitions are not inherently tied to one agent runtime. But the operational layer in the current scaffold is Claude-oriented. `CLAUDE.md`, `.claude/commands/`, `.claude/agents/`, and the documented hook lifecycle all assume Claude Code semantics.

Codex can use the governance model effectively, but only by translating those assumptions manually. That translation is currently implicit, which creates avoidable ambiguity. If Codex is to be treated as a first-class Armature environment, the scaffold needs an explicit adapter layer that preserves one governance source of truth while accurately reflecting Codex's actual execution model.

## Decision

Armature will support multiple agent runtimes through thin tool adapter entrypoints layered on top of the same governance sources.

- Root and scoped `agents.md`, ADRs, the invariant registry, and persona files remain the canonical governance system.
- `CLAUDE.md` remains the Claude Code adapter and continues to describe Claude-specific entrypoint and routing behavior.
- `CODEX.md` is added as a Codex adapter entrypoint. It translates the same governance sources into Codex-native instructions without redefining them.
- Tool adapters must stay thin. They route to governance sources and explain runtime-specific execution mechanics; they do not create contradictory rules, duplicate ADR content, or invent unsupported capabilities.
- When a runtime lacks a Claude-specific feature such as slash commands or lifecycle hook wiring, the adapter must specify the runtime-accurate equivalent: conversational protocol execution, or hooks.json-based/manual/CI hook invocation. For subagent orchestration, the adapter must describe the runtime's actual capabilities (e.g., Codex supports explicit parallel subagent spawning on user request) rather than defaulting to sequential-only.
- Codex routing should point directly to shared persona files and scoped governance, not to Claude-specific subagent wiring, which remains a Claude-only adapter layer.

## Consequences

- Armature remains single-source-of-truth while gaining first-class Codex support.
- Projects can ship both `CLAUDE.md` and `CODEX.md` without splitting governance.
- Claude-specific files remain valid and do not need to be generalized beyond their adapter role.
- Tool adapters become additional files that must be kept synchronized with the underlying governance.
- Some behaviors remain runtime-specific: Claude hook wiring and slash commands have no exact Codex equivalent and must be documented as manual or optional in `CODEX.md`.

## Invariants

- **ADAPTER-001:** Tool-specific adapter files must route to the same governance sources and must not redefine or contradict root/scoped governance, ADRs, or the invariant registry.
- **REF-003:** All governance file paths referenced in `CODEX.md` routing tables must exist as files.

## Supersedes Invariants

None.

## Non-Goals

- Creating a new `.codex/` subagent wiring tree parallel to `.claude/`
- Standardizing a cross-runtime hook API (though runtime-specific hook templates are provided when the runtime supports lifecycle hooks)
- Replacing Claude-specific commands or wiring with generic files

## Observability

- Manual review verifies that tool adapters stay thin and consistent with the shared governance sources.
- `post-stop.sh` validates `CODEX.md` routing references when the file exists.
- CI runs the same validation through the governance workflow.

## Security Considerations

No additional security considerations beyond existing baseline. The Codex adapter narrows risk by documenting unsupported features instead of implying they exist.

## Acceptance Criteria

- [ ] The spec describes `CODEX.md` as a Codex adapter layered on shared governance.
- [ ] A `CODEX.md` template exists for scaffold generation.
- [ ] The canonical repository includes a `CODEX.md` entrypoint.
- [ ] `post-stop.sh` validates `CODEX.md` routing references when present.
- [ ] Init, extend, and backport protocols account for `CODEX.md` and its template.
