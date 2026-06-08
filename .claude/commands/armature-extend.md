---
description: >
  Onboard a new component into the Armature governance scaffold.
  Creates scoped agents.md, implementer persona, and Claude Code subagent.
  Updates the invariant registry, tool adapter routing tables, and config.yaml.
  This is an orchestrator-only action.
argument-hint: "<component-path>"
---

# Armature Component Onboarding

You are the orchestrator. A new component needs to be added to the governance scaffold. Follow the onboarding protocol defined in `.armature/ARMATURE.md` §7.2.

## Component: $ARGUMENTS

### Step 1: Gather Context
Determine:
1. **Path:** Where does this component live in the directory tree?
2. **Responsibility:** What does this component do? (2–3 sentences)
3. **Parent:** Which existing agents.md does this component inherit from?
4. **Governing ADRs:** Which existing ADRs apply to this component?
5. **Invariants:** Which existing invariants from the registry apply?
6. **New invariants:** Does this component introduce any new hard constraints? If so, they need registry entries.
7. **Authority:** What actions should the implementer be permitted? (read, write, test, deploy)
8. **Restricted:** What actions should be prohibited? (cross-cutting-changes, schema-migration, etc.)

### Step 2: Create Governance File
Create `{component-path}/agents.md` (or `AGENTS.md`, matching the project's existing convention) using the template at `.armature/templates/agents.md.tmpl`. Populate all frontmatter fields and all four body sections (Overview, Behavioral Directives, Change Expectations, Cross-Links).

### Step 3: Create Implementer Persona
Create `.armature/personas/implementers/{component-name}.md` using the template at `.armature/templates/persona.md.tmpl`. Fill in scope, responsibility, authority, restricted, and ADR references.

### Step 4: Create Claude Code Subagent
Create `.claude/agents/{component-name}-impl.md` wired to the persona file.

### Step 5: Update Registry (if needed)
If the component introduces new invariants:
1. Add entries to `.armature/invariants/registry.yaml`
2. Update `.armature/invariants/invariants.md`
3. Ensure new invariants have IDs and are referenced in the new agents.md frontmatter

If new invariants use `enforced-by.hooks` entries, verify the relevant hooks are wired in `.claude/settings.json` per `.armature/templates/settings-hooks.json.tmpl`.

### Step 6: Update Tool Adapters
Add the new component to the routing table in `CLAUDE.md`. If `CODEX.md` exists, update its routing table as well.

### Step 7: Update config.yaml
Add the component to the `topology.components` list in `.armature/config.yaml`.

### Step 8: Log
Record the onboarding in `.armature/session/state.md` under the Decisions Log:
- What component was added
- Why it was needed
- Which ADRs and invariants govern it

Confirm completion with the human.
