# Armature — Development Directives

## Coding Standards

- All governance files use Markdown with YAML frontmatter where applicable
- YAML files must be valid and parseable by Python's `yaml.safe_load()`
- Bash scripts must use `set -euo pipefail`
- Use 2-space indentation in YAML, 4-space in Python
- Headings use ATX style (`#`) not Setext style

## Architecture

- ARMATURE.md is the single source of truth for the methodology
- Persona files implement what the spec defines — they must not contradict it
- Commands are operational protocols — they reference the spec, not redefine it
- Agent wiring files are thin pointers to persona files — minimize duplication
- Tool adapter entrypoints (for example `CLAUDE.md` and `CODEX.md`) are routing layers over shared governance — they must not introduce contradictory rules
- Templates define structure, not content — project-specific content is generated during init

## ADR Governance

- Core architectural decisions must be captured as ADRs in `docs/adr/` before implementation.
- Review applicable ADRs at the start of every implementation effort.
- Commits must reference governing ADRs when applicable.
- If no ADR exists for a core decision, create one first.

## Cross-Reference Integrity

- Every agents.md path in CLAUDE.md routing table must point to an existing file
- Every agents.md path in CODEX.md routing table must point to an existing file when CODEX.md is present
- Every ADR referenced in agents.md frontmatter must exist in docs/adr/
- Every invariant ID referenced in agents.md frontmatter must exist in the registry
- Every enforced-by path in the registry must point to an existing file
- Section references within ARMATURE.md must use correct section numbers

## Testing

- Run `bash .armature/hooks/post-stop.sh` to validate governance integrity
- CI runs this automatically on every push and PR
- All validation must pass before merging

## Commit Conventions

- Specification changes: `armature: {description}`
- Command changes: `commands: {description}`
- Agent wiring changes: `agents: {description}`
- Multi-scope changes: `armature: {description}` (use the primary scope)
- Always reference the governing ADR if applicable
