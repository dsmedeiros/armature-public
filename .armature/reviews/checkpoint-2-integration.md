# Review Verdict: checkpoint-2-integration

## Scope Compliance
- Declared scope: `.armature` (governed by `.armature/agents.md`)
- Files modified:
  - `.armature/ARMATURE.md` (§5.2 expansion)
  - `.armature/invariants/registry.yaml` (6 HOOK entries added)
  - `.armature/invariants/invariants.md` (Hook Enforcement section added)
  - `.armature/templates/settings-hooks.json.tmpl` (new file)
  - `CLAUDE.md` (Critical Invariants table expanded)
  - `.armature/agents.md` (frontmatter updated)
- Out-of-scope modifications: none — all files are within `.armature` or `CLAUDE.md`, both governed by `.armature/agents.md`

## Invariant Compliance

| Invariant | Status | Notes |
|---|---|---|
| SPEC-001 | PASS | Section headings are contiguous: §5.2 gains subsections 5.2.1–5.2.6 using `####` depth, which does not displace §5.3 or §5.4. All top-level and second-level numbering verified via heading grep: 1, 2, 3, 3.1–3.7, 4, 4.1–4.6, 4.6.1, 5, 5.1, 5.2, 5.2.1–5.2.6, 5.3, 5.4, 6, 6.1–6.8, 7, 7.1–7.8, 8, 8.1–8.3, 9, 10, 10.1–10.2. No gaps. |
| SPEC-002 | PASS | The pre-existing "See §8 Conflict Resolution" reference at line 208 is a stale reference (§7.4 is Conflict Resolution, §8 is Schemas) but it predates this changeset — confirmed via `git show HEAD`. The new §5.2.6 references `.armature/templates/settings-hooks.json.tmpl`, which now exists as an untracked file. No new broken references were introduced. |
| SCHEMA-001 | N/A | config.yaml was not modified. |
| SCHEMA-002 | FAIL | The §8.3 Invariant Registry Entry schema defines `enforced-by` with exactly three permitted sub-keys: `ci`, `startup`, `runtime`. All 6 new HOOK entries (HOOK-001 through HOOK-006) use `hooks:` as the `enforced-by` sub-key, which is not present in the §8.3 schema definition. The §8.3 schema block in ARMATURE.md was not updated to include the `hooks:` sub-key. This is a schema divergence between the canonical schema definition and the actual registry entries introduced by this changeset. |
| REF-001 | PASS | Routing table paths verified: `.armature/agents.md`, `.claude/commands/agents.md`, `.claude/agents/agents.md` all exist. |
| REF-002 | PASS | All HOOK entries declare `defined-in: docs/adr/0001-governance-as-files.md`, which exists. The `.armature/agents.md` frontmatter `adrs: [ADR-0001]` resolves to the same file. |
| HOOK-001 | PASS | `.armature/hooks/block-dangerous-commands.sh` exists. Referenced in `.armature/invariants/invariants.md` and `.armature/agents.md`. CLAUDE.md table entry present. |
| HOOK-002 | PASS | `.armature/hooks/block-config-changes.sh` exists. Referenced in `.armature/invariants/invariants.md` and `.armature/agents.md`. CLAUDE.md table entry present. |
| HOOK-003 | PASS | `.armature/hooks/mark-dirty.sh` and `.armature/hooks/post-stop.sh` both exist. Referenced in `.armature/invariants/invariants.md` and `.armature/agents.md`. CLAUDE.md table entry present. |
| HOOK-004 | PASS | `.armature/hooks/inject-context.sh` exists. Referenced in `.armature/invariants/invariants.md` and `.armature/agents.md`. CLAUDE.md table entry present. |
| HOOK-005 | PASS | `.armature/hooks/reinject-context.sh` exists. Referenced in `.armature/invariants/invariants.md` and `.armature/agents.md`. CLAUDE.md table entry present. |
| HOOK-006 | PASS | `.armature/hooks/check-required-reading.sh` exists. Referenced in `.armature/invariants/invariants.md` and `.armature/agents.md`. CLAUDE.md table entry present. |

## Checkpoint: 2 of 2

## Verdict: FAIL

## Required Changes:

1. **SCHEMA-002 violation — §8.3 schema must be updated to include the `hooks:` sub-key under `enforced-by`.**

   Location: `.armature/ARMATURE.md`, §8.3 "Invariant Registry Entry" (lines 1250–1253).

   The schema block currently reads:
   ```yaml
   enforced-by:
     ci: []                   # Test file paths
     startup: []              # Fail-fast guard paths
     runtime: []              # Runtime guard paths
   ```

   The 6 new HOOK entries use `hooks:` as the `enforced-by` sub-key (e.g., `.armature/hooks/block-dangerous-commands.sh`). The schema must be extended to declare `hooks:` as a valid sub-key, or the registry entries must be restructured to use an existing sub-key (e.g., `runtime`). The chosen resolution must be consistent across §8.3 and all 6 HOOK entries in `registry.yaml`.

## Rollback Recommendation: NO
The violation is contained to a schema definition omission — the §8.3 schema block was not updated to reflect the new `hooks:` sub-key used by the HOOK entries. All hook files exist, all references resolve, and the structural logic of the deliverable is sound. Remediation (updating the schema block in §8.3) is a targeted single-location fix that does not require unwinding any of the integration work.
