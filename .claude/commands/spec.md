---
description: "Scaffold a task specification with acceptance criteria for TASK-001."
argument-hint: "<title or problem statement>"
discipline-tags: [definition-of-done]
---

# Spec — Task Specification Scaffold

You are the orchestrator. The user has requested a new task specification via `/spec`.

<!-- discipline-tags: [definition-of-done] -->

## Argument Handling

Examine `$ARGUMENTS`:

- If `$ARGUMENTS` is non-empty: trim leading and trailing whitespace. Use the trimmed value as
  the Title slot in the template below. The rendered heading will read
  `# Task Specification: $ARGUMENTS`.
- If `$ARGUMENTS` is empty or whitespace-only: use the literal placeholder `<title>` for
  the Title slot. The rendered heading will read `# Task Specification: <title>`.

Do NOT auto-pre-fill any other slots from `.armature/session/state.md`. Populating those slots
is a deliberate authoring act by the human; pre-filling them with session state would produce
stale or misleading context unless explicitly reviewed and confirmed.

## Emit the Template

Present the following scaffold verbatim to the human. Copy it exactly — including all headings,
HTML comments, and angle-bracket placeholders. The `## Acceptance Criteria` heading and the
three placeholder bullets are required exactly as shown; they satisfy the strict-mode regex in
`task-readiness.sh` (`^#{1,6}\s+Acceptance\s+Criteria\s*$`) so that this specification, once
populated, passes the TASK-001 delegation gate without modification.

```markdown
# Task Specification: <title>

<!-- discipline-tags: [definition-of-done] -->

## Context / Motivation
<!-- Why this task exists; what problem it solves. -->
<context>

## Acceptance Criteria
- Must <primary functional requirement>
- Must <secondary functional requirement>
- Must <third functional requirement — add as many as needed>

## Out of Scope
<!-- Explicitly list related work NOT covered by this task. -->
<out-of-scope>

## Risks
<!-- Technical, governance, or dependency risks. -->
<risks>

## Verification Steps
<!-- How the orchestrator and reviewer confirm the work is done. -->
<verification>

## Dependencies
<!-- Other tasks or invariants this depends on. Leave blank if none. -->
<dependencies>

## Related ADRs / Invariants
<!-- e.g., ADR-0001, TASK-001 -->
<related>
```

Present this scaffold to the human. Wait for them to populate the slots and confirm before
using this as a delegation prompt for a sub-agent. The canonical `## Acceptance Criteria`
heading guarantees task-readiness.sh strict-mode detection passes when this is sent through
SubagentStart or PreToolUse(Task).
