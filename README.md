# Armature

**Agentic Repository Management Architecture**

Version 1.0.0 | Dave Medeiros / Panoptic Systems

---

Armature is a portable scaffold specification for standing up agentic repository governance. It defines the complete system -- governance file hierarchy, agent persona architecture, invariant enforcement, and operational protocols -- so that any new project can be initialized with a production-grade structure for human-directed, AI-executed development.

Armature is not a framework or a library. It is a structural methodology encoded as files, conventions, and protocols.

## Quick Start

1. Copy the `.armature/` directory, `.claude/` directory, and `docs/` directory into your project root
2. Run `/armature-init` in Claude Code to initialize the scaffold for your project
3. The orchestrator will guide you through project discovery and generate all governance files (CLAUDE.md, agents.md, scoped agents.md, ADRs, invariants, personas)
4. To upgrade later: run `/armature-backport <path-to-canonical-armature-repo>`

## Repository Structure

```
armature/
├── README.md                           <- You are here
├── LICENSE                             <- Apache 2.0
├── CLAUDE.md                           <- Orchestrator entry point (live, not template)
├── agents.md                           <- Root development directives (live)
├── .armature/
│   ├── ARMATURE.md                     <- Full specification (the source of truth)
│   ├── config.yaml                     <- Project metadata and topology
│   ├── agents.md                       <- Scoped directives for specification scope
│   ├── journal.md                      <- Governance journal (committed, append-only)
│   ├── .gitignore                      <- Ephemeral state exclusions
│   ├── personas/
│   │   ├── orchestrator.md             <- Orchestrator persona (main agent)
│   │   ├── reviewer.md                 <- Compliance reviewer persona
│   │   ├── reviewer-redteam.md         <- Adversarial red team reviewer persona
│   │   ├── planner.md                  <- Opt-in planner persona
│   │   └── implementers/              <- Per-component implementer personas
│   ├── invariants/
│   │   ├── registry.yaml               <- Machine-readable invariant index
│   │   └── invariants.md               <- Human-readable invariant list
│   ├── templates/
│   │   ├── adr.md.tmpl                 <- Architecture Decision Record template
│   │   ├── agents.md.tmpl              <- Scoped agents.md template
│   │   └── persona.md.tmpl             <- Implementer persona template
│   ├── hooks/
│   │   └── post-stop.sh                <- Mechanical validation hook
│   ├── session/                        <- Ephemeral working state (gitignored)
│   ├── reviews/                        <- Reviewer verdict artifacts (committed)
│   └── escalations/                    <- Circuit breaker handoff packages (gitignored)
├── .claude/
│   ├── commands/
│   │   ├── armature-init.md            <- /armature-init instantiation protocol
│   │   ├── armature-extend.md          <- /armature-extend component onboarding
│   │   ├── armature-update.md          <- /armature-update specification changes
│   │   ├── armature-backport.md        <- /armature-backport framework upgrades
│   │   ├── checkpoint.md               <- /checkpoint pre-compaction state save
│   │   └── agents.md                   <- Scoped directives for commands scope
│   └── agents/
│       ├── reviewer.md                 <- Claude Code subagent wiring for reviewer
│       ├── reviewer-redteam.md         <- Claude Code subagent wiring for red team
│       ├── planner.md                  <- Claude Code subagent wiring for planner
│       ├── specification-impl.md       <- Implementer wiring for .armature/ scope
│       ├── commands-impl.md            <- Implementer wiring for commands scope
│       ├── agent-wiring-impl.md        <- Implementer wiring for agent wiring scope
│       └── agents.md                   <- Scoped directives for agent wiring scope
├── .github/
│   └── workflows/
│       └── governance.yml              <- CI: governance validation on push/PR
└── docs/
    └── adr/
        └── 0001-governance-as-files.md <- Core architectural decision
```

## What Gets Created During /armature-init

The initialization protocol (Phase 0 scan, Phase 1 discovery, Phase 2 scaffolding) generates:

- **CLAUDE.md** -- orchestrator entry point with routing table (from CLAUDE.md.tmpl)
- **Root agents.md** -- global development directives (from agents.md.tmpl)
- **Scoped agents.md** files -- per-component governance with YAML frontmatter
- **ADRs** in docs/adr/ -- architecture decisions with invariant declarations
- **Invariant registry** -- populated from ADRs and existing test enforcement
- **Implementer personas** -- one per component in .armature/personas/implementers/
- **Subagent wiring** -- implementer .claude/agents/ files
- **Taskmaster integration** -- task graph from PRD

## Framework Files vs. Project-Specific Files

**Framework (generic, reusable across projects):**
- `.armature/ARMATURE.md` -- the specification
- `.armature/personas/orchestrator.md`, `reviewer.md`, `reviewer-redteam.md`, `planner.md`
- `.armature/templates/*`
- `.armature/hooks/post-stop.sh`
- `.claude/commands/*`
- `.claude/agents/reviewer.md`, `reviewer-redteam.md`, `planner.md`

**Project-specific (generated during init):**
- `.armature/config.yaml` -- project metadata and topology
- `.armature/invariants/registry.yaml` -- project constraints
- `.armature/invariants/invariants.md` -- human-readable constraints
- `.armature/personas/implementers/*.md` -- component-scoped personas
- `.claude/agents/*-impl.md` -- implementer subagent wiring
- `CLAUDE.md` -- project-specific orchestrator entry point
- `agents.md` -- project-specific global directives
- `docs/adr/*.md` -- project-specific architecture decisions
- `{source}/agents.md` -- scoped governance files

## Design Principles

1. **Governance as Structure** -- Rules encoded in files at the locations they govern
2. **Progressive Disclosure** -- Agents read only what their scope requires
3. **Authority Boundaries** -- Personas defined by decision authority, not skill
4. **Externalized Working Memory** -- State on disk, not in conversation context
5. **Defense in Depth** -- Behavioral + mechanical + CI enforcement layers
6. **Inside/Outside Separation** -- Orchestrator sees topology; implementers see code
7. **Machine-Readable Governance** -- Structured frontmatter for programmatic parsing
8. **Degraded Mode as Documentation** -- Everything human-readable without tooling
9. **YAGNI** -- Single developer + agentic workflow; multi-user deferred

## License

Copyright 2026 Panoptic Systems. Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
