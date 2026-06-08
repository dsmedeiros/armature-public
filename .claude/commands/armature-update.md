---
description: >
  Update the Armature specification (ARMATURE.md) or governance protocols.
  Orchestrator-only action requiring human approval. Covers additive changes,
  amendments, and deprecation of existing spec sections. Ensures downstream
  files stay in sync with the specification.
---

# Armature Specification Update

You are the orchestrator. Execute the specification update protocol. Changes to ARMATURE.md require structured proposal, impact analysis, human approval, and downstream synchronization.

## When to Use

- Adding new operational protocols or persona capabilities
- Amending existing sections to fix ambiguities or gaps
- Adding schema fields to config.yaml, agents.md frontmatter, or registry entries
- Deprecating obsolete guidance or protocols
- Updating section numbering or cross-references after structural changes

## Protocol

### Step 1: Identify the Change

State clearly:
1. **What** needs changing — which section(s), what content
2. **Why** — the problem or gap this addresses
3. **Category** — Additive (new section/field), Amendment (modify existing), or Deprecation (remove/mark obsolete)

### Step 2: Draft the Change

Write the exact text to be added, modified, or removed. Include:
- Section number and heading
- Full text of new or replacement content
- Any cross-references that need updating (other sections that reference the changed content)

### Step 3: Impact Analysis

Identify every downstream file affected by the change:
- **Persona files** — Does the change affect orchestrator, planner, reviewer, or implementer behavior?
- **Config schema** — Does it add or modify fields in config.yaml?
- **Templates** — Does it change the governance file (`agents.md`/`AGENTS.md`), ADR, or persona templates?
- **Commands** — Does it affect armature-init, armature-extend, or checkpoint protocols?
- **Subagent wiring** — Does it change .claude/agents/ definitions?
- **Invariant registry** — Does it add or modify registry schema fields?
- **Hook scripts** — Does it add or modify mechanical enforcement hooks (§5.2)? Are hook scripts in `.armature/hooks/` affected? Does `.armature/templates/settings-hooks.json.tmpl` need updating?

- **Tool adapters** — Does it change `CLAUDE.md`, `CODEX.md`, or `.armature/templates/CODEX.md.tmpl` expectations?

List each affected file and what must change in it.

### Step 4: Human Approval

Present the draft and impact analysis to the human. Include:
- Summary of the change (1-2 sentences)
- The draft text
- The list of affected files
- Any trade-offs or alternatives considered

**Wait for explicit approval before proceeding.** Do not apply changes based on implied consent.

### Step 5: Apply Changes

In order:
1. Edit ARMATURE.md with the drafted changes
2. Update all downstream files identified in Step 3
3. Verify section numbering and cross-references are consistent
4. Log the specification change in `.armature/journal.md`:
   ```markdown
   ### {YYYY-MM-DD HH:MM} — specification-update
   Updated ARMATURE.md: {brief description of change}.
   Category: {additive/amendment/deprecation}
   Sections affected: {list}
   Downstream files updated: {list}
   ```

### Step 6: Verify Consistency

After applying all changes:
1. Confirm all internal section references in ARMATURE.md resolve correctly
2. Confirm all cross-file references (persona files pointing to spec sections) are valid
3. Confirm schema definitions in ARMATURE.md match actual config.yaml and registry.yaml structure
4. Commit with structured message: `armature: {brief description of spec change}`
