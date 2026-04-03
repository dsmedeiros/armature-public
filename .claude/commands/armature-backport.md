---
description: >
  Update a project's framework-generic Armature files from the canonical
  Armature repository without overwriting project-specific files.
  Use when the canonical Armature has been updated and you want to
  pull improvements into an existing project.
argument-hint: "<path-to-canonical-armature-repo>"
---

# Armature Backport

You are the orchestrator. A newer version of the Armature framework is available and needs to be backported into this project. Follow this protocol to update framework-generic files while preserving all project-specific content.

## Source: $ARGUMENTS

If no argument is provided, ask the human for the path to the canonical Armature repository (local path or git clone URL).

## Framework-Generic vs. Project-Specific

**Framework-generic (will be updated):**
- `.armature/ARMATURE.md` — the specification
- `.armature/.gitignore` — ephemeral path exclusions
- `.armature/agents.md` — governance scope directives
- `.armature/personas/orchestrator.md` — orchestrator persona
- `.armature/personas/reviewer.md` — reviewer persona
- `.armature/personas/reviewer-redteam.md` — red team reviewer persona
- `.armature/personas/planner.md` — planner persona
- `.armature/templates/` — all template files (adr.md.tmpl, agents.md.tmpl, persona.md.tmpl, settings-hooks.json.tmpl)
- `.armature/hooks/` — all hook scripts:
  - `post-stop.sh` — on-stop governance validation + conditional test runner
  - `block-dangerous-commands.sh` — PreToolUse(Bash) destructive command guard
  - `block-config-changes.sh` — ConfigChange self-governance prevention
  - `mark-dirty.sh` — PostToolUse(Edit|Write) code change tracker
  - `inject-context.sh` — SubagentStart governance context injection
  - `reinject-context.sh` — SessionStart(compact) post-compaction recovery
  - `check-required-reading.sh` — PreToolUse(Edit|Write) required reading advisory
- `.armature/escalations/.gitkeep` — escalation directory marker
- `.armature/session/logs/.gitkeep` — session log directory marker
- `.claude/commands/armature-init.md` — init protocol
- `.claude/commands/armature-extend.md` — extend protocol
- `.claude/commands/armature-update.md` — update protocol
- `.claude/commands/armature-backport.md` — this file (self-update)
- `.claude/commands/checkpoint.md` — checkpoint protocol
- `.claude/commands/agents.md` — commands scope directives
- `.claude/agents/reviewer.md` — reviewer subagent wiring
- `.claude/agents/reviewer-redteam.md` — red team subagent wiring
- `.claude/agents/planner.md` — planner subagent wiring
- `.claude/agents/agents.md` — agents scope directives

**Project-specific (NEVER overwritten):**
- `.armature/config.yaml` — project metadata and topology
- `.armature/invariants/registry.yaml` — project invariant registry
- `.armature/invariants/invariants.md` — project invariant descriptions
- `.armature/personas/implementers/*.md` — component implementer personas
- `.armature/journal.md` — governance journal
- `.armature/session/` — session state
- `.armature/reviews/` — review verdicts
- `.claude/agents/*-impl.md` — implementer subagent wiring
- `CLAUDE.md` — project orchestrator entry point
- `agents.md` / `AGENTS.md` — project root directives (either casing)
- `*/agents.md` / `*/AGENTS.md` — scoped directives (either casing)
- `docs/adr/*.md` — project ADRs

> **Important:** This list is a known baseline, not exhaustive. Step 2 performs discovery to catch new files added to the canonical repo that aren't listed here.

## Protocol

### Step 1: Read Source Version

Read the canonical Armature repo's `.armature/config.yaml` to get its `armature-version`.
Read this project's `.armature/config.yaml` to get the current `armature-version`.

Report to the human: "Upgrading Armature from {current} to {canonical}."

If versions are the same, ask the human whether to proceed anyway (there may be changes within the same version).

### Step 2: Discover and Diff Framework Files

Do NOT rely solely on the hardcoded list above. The canonical repo may have added new framework-generic files since the list was last updated.

**Discovery procedure:**
1. List all files under the canonical repo's `.armature/` and `.claude/` directories
2. Classify each as framework-generic or project-specific using these rules:
   - **Framework-generic:** Persona files in `personas/` (except `implementers/`), all files in `templates/`, all files in `hooks/`, ARMATURE.md, .gitignore, agents.md/AGENTS.md at `.armature/` root, `.gitkeep` directory markers, all files under `.claude/commands/` and `.claude/agents/` (except `*-impl.md`)
   - **Project-specific:** `config.yaml`, `invariants/registry.yaml`, `invariants/invariants.md`, `journal.md`, `session/state.md`, `reviews/`, `personas/implementers/`, `escalations/` (contents, not `.gitkeep`)
3. For any file that doesn't clearly fit either category, flag it for human review

For each framework-generic file (both listed and discovered):
1. Read the canonical version
2. Read the project's current version (if it exists)
3. Classify as: identical, modified, new (exists in canonical but not in project), or removed (exists in project but deleted in canonical)

**Write the complete classified file list as a scratch manifest** (e.g., in a todo list or temporary note). Step 4 must iterate this manifest — not reconstruct the list from memory.

Present a summary to the human:
- Files that will be updated (with brief description of what changed)
- New files that will be added
- Files that are already current (no changes needed)
- Files removed in canonical (flag for human decision)

### Step 3: Check for Project-Specific Modifications

Before overwriting, check whether any framework-generic files in the project have been locally modified (e.g., the project customized orchestrator.md beyond the standard persona). If so, warn the human:

"These framework files have local modifications that will be lost:
- {file}: {description of local changes}

Should I proceed, or do you want to merge these manually?"

### Step 4: Apply Updates

With human confirmation:
1. Copy each modified/new framework-generic file from the canonical source to the project. **Iterate the discovery manifest from Step 2** — do not reconstruct the file list from memory. This includes pre-existing files that need overwriting (e.g., `.claude/agents/reviewer.md`), not just new files.
2. Create any new directories needed (e.g., `escalations/`, `session/logs/`)
3. Do NOT touch any project-specific file
4. **Post-copy verification:** After all copies complete, diff every framework-generic file in the manifest against the canonical version. Report any remaining divergence before proceeding to schema migration. This catches files that were accidentally skipped during the copy loop.

### Step 5: Schema Migration — Config

Check whether the updated ARMATURE.md defines config.yaml schema fields that the project's config.yaml is missing.

**Full config.yaml audit procedure:**
1. Read the ARMATURE.md sections that define config.yaml schema (look for `config.yaml` references in schema sections)
2. Compare every required field against the project's actual config.yaml
3. For each missing field:
   - If it has a sensible default in the spec, add it with that default
   - If it requires project-specific values, list it for the human to fill in
4. Report all additions made and any fields requiring human input

This is a completeness check, not just a diff of "new" fields — existing projects may have been missing fields that were always required but previously unenforced.

### Step 6: Schema Migration — Registry

Check whether the updated ARMATURE.md changes the registry.yaml entry schema.

**Registry schema audit procedure:**
1. Read the ARMATURE.md registry entry schema definition (§3.7 or equivalent)
2. Compare the schema against the project's actual registry.yaml structure
3. Check for:
   - **Structural changes:** e.g., list-based entries migrated to dict-based, flat fields restructured to nested (like `enforced-by` flat array → `enforced-by.ci/startup/runtime`)
   - **New required fields:** e.g., `name`, `description`, `status` added to entry schema
   - **Field type changes:** e.g., severity values renamed
4. If structural migration is needed:
   - Present the migration plan to the human (old format → new format)
   - With approval, rewrite registry.yaml preserving all project-specific content (invariant IDs, rules, ADR references, enforcement paths) while conforming to the new schema
   - For new required fields, populate with sensible values derived from existing data (e.g., `status: active` for all entries, `name` derived from the rule text)
5. Update `invariants.md` to match any registry changes

### Step 7: Invariant Cross-Reference Audit

New framework-generic files (especially scoped `agents.md` files like `.armature/agents.md` or `.claude/commands/agents.md`) may reference invariant IDs that don't exist in the project's registry. These are typically governance invariants defined by the Armature spec itself (e.g., SPEC-001, SCHEMA-001).

**Audit procedure:**
1. Extract all invariant IDs from every `agents.md` file in the project (both existing and newly added)
2. Extract all invariant IDs from registry.yaml
3. Identify any IDs referenced in agents.md files that are missing from the registry
4. For each missing ID:
   - Check if it's a governance invariant defined by the ARMATURE.md spec (look for the ID in the spec text or in the canonical repo's own registry)
   - If found in the canonical registry, create a corresponding entry in the project registry using the canonical definition
   - If not found anywhere, flag it for human review
5. Also check the reverse: registry entries not referenced by any agents.md file (orphaned invariants)
6. **Rebuild `referenced-in` fields:** For every registry entry, mechanically scan all `agents.md` files for the invariant ID and compare against the entry's `referenced-in` array. Add any missing paths. This is especially important after Step 6 registry migration, where `referenced-in` values may have been carried over verbatim from the old schema without recomputation.
7. Update `invariants.md` to include any new invariant categories

### Step 8: Update Version

Update the `armature-version` field in the project's `.armature/config.yaml` to match the canonical version. If the field doesn't exist, add it.

### Step 9: Verify

Run `bash .armature/hooks/post-stop.sh` to confirm governance integrity after the backport.

If validation fails:
- Report which checks failed
- These are likely due to new cross-reference requirements introduced by the updated spec
- Help the human resolve each failure

**Hook output coverage check:** Do not rely solely on the exit code. Count the number of PASS/FAIL/SKIP lines in the hook output and compare against the expected number of checks (routing table resolution, registry YAML validation, uncommitted change detection, ADR reference resolution, conditional test run). If any expected check is missing from the output, report it as "CHECK MISSING — likely silently failed" and investigate. On non-Linux platforms, grep the hook source for platform-dependent constructs (`grep -P`, Bash-specific syntax) and flag any that may cause silent failures.

**Hook wiring check:** Compare the project's `.claude/settings.json` (if it exists) against `.armature/templates/settings-hooks.json.tmpl`. Report any hooks that exist as files but are not wired in settings.json. Offer to update the wiring. If no settings.json exists, advise the human to copy the template's hook entries into their Claude Code configuration.

**Additional verification:**
- Confirm all invariant IDs in agents.md files resolve to registry entries (Step 7 should have caught this, but verify mechanically)
- Confirm config.yaml has all fields required by the updated ARMATURE.md spec
- **Routing table completeness:** List all `agents.md` files in the project. For each one, verify it appears in the CLAUDE.md routing table. Report any `agents.md` files that exist but have no routing table entry. These may be pre-existing gaps rather than backport regressions, but should be resolved while governance is being audited.
- **Hook file completeness:** List all `.sh` files in `.armature/hooks/`. Verify each one is referenced in the invariant registry's `enforced-by` fields. Report any hooks that exist as files but have no registry entry.

### Step 10: Log

Append to `.armature/journal.md`:
```markdown
### {YYYY-MM-DD HH:MM} — backport
Armature framework updated from {old-version} to {new-version}.
Source: {canonical-repo-path}
Files updated: {count}
New files added: {list or "none"}
Schema migrations: {list or "none"}
Invariant migrations: {list or "none"}
Validation: {PASS or list of issues}
```

Commit with message: `armature: backport framework from {old-version} to {new-version}`
