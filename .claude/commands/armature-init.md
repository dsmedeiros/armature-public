---
description: >
  Initialize Armature governance scaffold for this repository.
  Works for both new (greenfield) and existing repos.
  Three-phase process: Phase 0 scans existing state, Phase 1 discovers
  through conversation + code analysis, Phase 2 generates governance files.
  Run once per repository.
---

# Armature Initialization

You are the orchestrator. Execute the Armature instantiation protocol as defined in `.armature/ARMATURE.md` §7.1.

**Bootstrapping note:** During initialization, CLAUDE.md is an unpopulated template. Skip reading it for orientation — you will generate the populated version as part of Phase 2. Your operating protocol for this command is defined entirely in this file and `.armature/ARMATURE.md`.

## Phase 0 — Pre-Flight

Before discovery, assess the current state of the repository:

1. **Scan the codebase.** Read the directory tree, READMEs, package manifests, config files, and any existing documentation. Build a mental model of what already exists — structure, languages, frameworks, conventions, test suites, CI configuration.
2. **Check for existing governance artifacts:**
   - Does a `CLAUDE.md` already exist? → Will need to be merged/replaced in Step 7.
   - Does an `agents.md` or `AGENTS.md` exist? → Incorporate its content into the root governance file, preserving the project's existing filename convention (lowercase or uppercase).
   - Does a `docs/adr/` directory exist with ADRs? → Adopt existing ADRs rather than re-creating.
   - Does a `.claude/` directory exist with agents or commands? → Preserve non-conflicting items.
   - Does a `.taskmaster/` directory exist? → Skip Taskmaster init; verify config.
   - Does a `.gitignore` exist? → Append to it, don't replace.
   - **Determine the project's governance filename convention:** If existing governance files use `AGENTS.md` (uppercase), all newly created governance files must also use `AGENTS.md`. If lowercase or no existing files, default to `agents.md`.
3. **Tag the pre-Armature baseline.** Before making any changes, tag the current HEAD:
   ```
   git tag armature/pre-init
   ```
   This provides a clean rollback point if the scaffolding itself causes problems.

Report your findings to the human: "Here's what I found in the repo. Here's what I'll need to create, and here's what already exists that I'll incorporate."

## Phase 1 — Project Discovery

Combine what you learned from scanning the codebase with a conversation with the human. Don't re-ask things you can already see in the code — demonstrate your understanding and ask the human to correct or extend it.

**For existing repos, lead with what you've observed:**

"I can see this is a {language} project using {framework}. The main components appear to be {list}. Your test suite uses {framework} and your CI runs on {system}. Let me confirm a few things and understand the parts that aren't obvious from the code..."

**What you need to learn (gather organically, combining code analysis and conversation):**

- **What is this?** The project's purpose, domain, and users. For existing repos, confirm your understanding from the codebase.
- **What's the stack?** Languages, frameworks, databases, infrastructure, CI. For existing repos, read this from package manifests, configs, and CI files — confirm versions.
- **What are the pieces?** The major components, services, or modules. For existing repos, read the directory structure and identify natural boundaries. Confirm with the human which boundaries matter for governance.
- **What decisions have already been made?** For existing repos, many decisions are implicit in the code. Surface them: "I see you're using {pattern} for {concern} — should this be codified as an ADR?" Existing ADR-like documents should be adopted.
- **What must never break?** For existing repos, look at existing tests, assertions, guards, and validation. Surface implicit invariants: "Your test suite enforces {constraint} — is this a hard invariant?" Also ask about constraints that aren't yet tested.
- **What's the current state?** For existing repos: What's working? What's broken? What's in progress?
- **What do you want to build/fix/change next?** This becomes the initial PRD. Understand scope, requirements, acceptance criteria.

**After the conversation:**

1. Summarize what you've learned — both from code analysis and conversation — back to the human in structured form. Get explicit confirmation.
2. Write the project metadata to `.armature/config.yaml`. The `governance.changeset-budget` section is populated with defaults (target-loc: 300, warn-loc: 500, planner-trigger-loc: 400). Ask the human if they want to adjust these thresholds based on their project's characteristics — smaller projects may want lower targets, larger codebases may need higher ones.
3. Generate the initial PRD from the conversation and save it to `.taskmaster/docs/prd.txt`. Confirm the PRD with the human.
4. Proceed to Phase 2 only after the human confirms both the config and the PRD.

## Phase 2 — Scaffolding

Using the completed `config.yaml` and the pre-flight assessment, generate files in this exact order (dependencies flow downward). **For each step, check whether the artifact already exists before creating it.**

### Step 1: Seed ADRs
For each foundational decision from discovery:
- **If existing ADRs are present** in `docs/adr/`, adopt them. Renumber if needed to fill gaps. Add Invariants sections if they lack them. Do not re-create decisions that are already recorded.
- **For new decisions** not yet captured, create ADRs using the template at `.armature/templates/adr.md.tmpl`. Number them sequentially, continuing from the highest existing ADR number.
- Ensure each ADR includes an Invariants section with IDs in the format `{CATEGORY}-{NNN}`.

### Step 2: Invariant Registry
For each invariant declared in the ADRs (existing and new), create an entry in `.armature/invariants/registry.yaml`.
- Set `defined-in` to the corresponding ADR.
- For existing repos: scan for existing tests, guards, and validation that enforce invariants. Populate the `enforced-by` fields with these paths. Mark gaps as TODOs.
- Set `referenced-in` to the agents.md files that will be created in Step 4.

### Step 3: Human-Readable Invariants
Populate `.armature/invariants/invariants.md` from the registry. Group by category. Include ID, severity, rule, rationale, and enforcement for each.

### Step 4: Scoped Governance Files

**CRITICAL: Iterate the topology, not existing files.** The authoritative list of components comes from `config.yaml` topology, not from globbing for existing `AGENTS.md` files. Globbing only finds what already exists and silently misses components that need new governance files. The correct loop is:

```
for each component in config.yaml topology:
  if AGENTS.md exists in component directory → update (add frontmatter, restructure)
  if AGENTS.md does NOT exist → create from template
```

For each component in the topology:
1. The component directory should already exist for existing repos. Create only if it doesn't.
2. **Check whether an `agents.md` or `AGENTS.md` file exists in that directory.**
   - **If present:** Incorporate existing content into the Armature-formatted governance file (add frontmatter, restructure into the 4-section template). Preserve existing directives. Keep the existing filename casing.
   - **If absent:** Create the governance file using the template at `.armature/templates/agents.md.tmpl`, using the project's established filename convention (see Phase 0, Step 2). Read source code in the directory to understand what the component does, then populate the body with component-specific directives.
3. Populate frontmatter: scope, governs, inherits, adrs, invariants, persona, authority, restricted.
4. Write the body: overview, behavioral directives, change expectations, cross-links.

**Verification gate:** After processing all components, count the resulting governance files and compare against the topology count. Every component in the topology MUST have a governance file. If the counts don't match, identify and create the missing files before proceeding.

Also create/update:
- Root governance file (`agents.md` or `AGENTS.md`) with global directives. **If one exists**, merge Armature directives (ADR governance, cross-cutting invariants, scoped directive references) with existing content. Preserve existing coding standards, conventions, and filename casing.
- Source-level governance file (e.g., `src/agents.md`) if the topology has multiple components under a shared parent.

### Step 5: Persona Files
1. Verify `.armature/personas/orchestrator.md`, `reviewer.md`, and `planner.md` are present (from the scaffold copy).
2. For each component, create `.armature/personas/implementers/{component}.md` using the template at `.armature/templates/persona.md.tmpl`. Fill in scope, responsibility, authority, restricted, and ADR references.

### Step 6: Claude Code Subagent Wiring
Create subagent files in `.claude/agents/` for implementers, reviewer, and planner only (NOT the orchestrator — it is the main agent):
- `.claude/agents/reviewer.md` → references `.armature/personas/reviewer.md`
- `.claude/agents/planner.md` → references `.armature/personas/planner.md`
- `.claude/agents/{component}-impl.md` → references `.armature/personas/implementers/{component}.md`

**If `.claude/agents/` already exists** with other subagent definitions, preserve them. Armature subagents are additive.

### Step 7: CLAUDE.md
**If a CLAUDE.md already exists:**
- Read its current content. Identify project-specific instructions, conventions, or context worth preserving.
- Generate the new CLAUDE.md with the Armature structure, incorporating preserved content into the appropriate sections (project overview, quick reference, etc.).
- Inform the human what was preserved and what was replaced. Confirm before writing.

**If no CLAUDE.md exists (or only the Armature template):**
Generate root `CLAUDE.md` (~200 lines) with:
- **Orchestrator directive (MUST be the first content):** "You are the orchestrator. Read and follow `.armature/personas/orchestrator.md` as your operating protocol." Include session recovery instructions and explicit Taskmaster MCP tool list.
- System overview (from config.yaml project section)
- Critical invariants (top 5–10 from registry, severity = critical)
- Routing table (from topology — map task types to agents.md + ADR paths)
- Meta-instruction including commit protocol summary and journal recovery directive.
- Agent workflow topology (brief description of the pipeline and personas)
- Quick reference (build, test, deploy commands from the tech stack)

### Step 8: Gitignore and Directory Markers

Create the following Armature ephemeral-state filesystem artifacts (they will not exist in a fresh scaffold):

- `.armature/escalations/.gitkeep` — ensures the escalations directory is tracked by git
- `.armature/session/logs/.gitkeep` — ensures the session logs directory is tracked by git
- `.armature/.gitignore` — internal gitignore scoped to the `.armature/` directory, with contents:
  ```
  session/
  escalations/
  .code-dirty
  ```

**Append** the following to the root `.gitignore` (do not replace existing content):
```
# Armature ephemeral state
.armature/session/
.armature/escalations/
.armature/.code-dirty
```

Note: Do NOT gitignore `.taskmaster/tasks/` — commit task files for persistence and rollback safety.

### Step 8.5: Hook Wiring

Armature ships with mechanical enforcement hooks in `.armature/hooks/` and a wiring template at `.armature/templates/settings-hooks.json.tmpl`. These hooks need to be wired into Claude Code's lifecycle events via the project's settings.

1. Read `.armature/templates/settings-hooks.json.tmpl` for the complete hook configuration.
2. Check if `.claude/settings.json` exists in the project. If not, it will need to be created.
3. Present the hook wiring to the human:
   - **PreToolUse(Bash):** `block-dangerous-commands.sh` — blocks destructive shell commands
   - **PreToolUse(Edit|Write):** `check-required-reading.sh` — advises required governance reading
   - **PostToolUse(Edit|Write):** `mark-dirty.sh` — tracks code changes for conditional testing
   - **Stop / SubagentStop:** `post-stop.sh` — governance validation + conditional test runner
   - **SubagentStart:** `inject-context.sh` — injects governance context into subagents
   - **SessionStart(compact):** `reinject-context.sh` — restores state after compaction
   - **ConfigChange:** `block-config-changes.sh` — prevents agent self-governance modification
4. With human confirmation, merge the hook entries from the template into `.claude/settings.json`.
5. If the human declines hook wiring (e.g., wants to evaluate first), note this as a TODO in the journal.

### Step 9: Taskmaster
**If `.taskmaster/` already exists:**
- Skip `task-master init`. Verify the config is compatible (models set to `claude-code` provider).
- If there are existing tasks, inform the human and ask whether to incorporate or start fresh.

**If `.taskmaster/` does not exist:**
1. If `task-master-ai` is not installed globally, run: `npm install -g task-master-ai`
2. Run `task-master init` in the project root.
3. Verify the MCP server is registered with Claude Code. If not, run:
   ```bash
   claude mcp add-json "task-master" '{"command":"npx","args":["-y","task-master-ai"],"env":{"MODEL":"claude-code"}}'
   ```
4. Update `.taskmaster/config.json` to use Claude Code's built-in models:
   ```json
   {
     "models": {
       "main": {
         "provider": "claude-code",
         "modelId": "sonnet",
         "maxTokens": 64000,
         "temperature": 0.2
       },
       "research": {
         "provider": "claude-code",
         "modelId": "opus",
         "maxTokens": 32000,
         "temperature": 0.1
       },
       "fallback": {
         "provider": "claude-code",
         "modelId": "sonnet",
         "maxTokens": 64000,
         "temperature": 0.2
       }
     }
   }
   ```

**Then, for both cases:**
5. Parse the PRD from Phase 1 via Taskmaster's `parse_prd` MCP tool.
6. Run complexity analysis via `analyze_project_complexity`.
7. Expand any tasks scoring > 7 or exceeding `changeset-budget.planner-trigger-loc` via `expand_task`.
8. Present the full task graph to the human: task titles, dependency order, complexity scores, target scope (agents.md path). Confirm the plan.
9. Recommend committing `.taskmaster/tasks/` to version control.

### Step 10: Verification and Launch
Confirm with the human:
- All components have scoped governance files (`agents.md` or `AGENTS.md`)
- All foundational decisions are captured as ADRs (existing adopted + newly created)
- All hard constraints are in the invariant registry
- CLAUDE.md routing table is complete
- Persona files exist for all components
- The Taskmaster task graph is confirmed and ready for execution
- Hook wiring in `.claude/settings.json` matches `.armature/templates/settings-hooks.json.tmpl` (or TODO noted in journal if human declined)
- Pre-Armature baseline is tagged (`armature/pre-init`)

Tag the initial Armature build candidate: `bc/{today's date}/000`.

Write the initialization to `.armature/journal.md`:
```markdown
### {date} — initialization
Armature scaffold applied to {existing/new} repository.
Pre-init baseline: armature/pre-init
Initial build candidate: bc/{date}/000
Components: {list}
ADRs: {count} ({n} existing adopted, {n} newly created)
Invariants: {count}
```

Then ask: "Ready to start building? I'll begin with the first task in the dependency chain."
