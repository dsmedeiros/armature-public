---
description: "Run post-Hotfix postmortem workflow; scaffold incident record per §7.9."
argument-hint: "<incident-slug>"
discipline-tags: [definition-of-done]
---

# Postmortem — Post-Hotfix Postmortem Workflow

You are the orchestrator. The user has invoked `/postmortem` to drive the post-Hotfix
postmortem workflow per `.armature/ARMATURE.md` §7.9 and §7.10.

## Step 1 — Detect Hotfix Context

Read `.armature/session/phase` as bytes. ASCII-strip only (per M3 lesson: Unicode whitespace
is a known bypass vector). Compare the stripped value to the string `"Hotfix"` exactly.

- **If the phase file contains `Hotfix` exactly:** The incident is ongoing. Scaffold this
  postmortem now. The postmortem document will be updated in place when the hotfix commits
  land.
- **Else if the phase file does not equal `Hotfix`:** Check whether
  `.armature/session/hotfix-audit/` exists and contains any `*.json` files.
  - **If `*.json` files are present:** List their filenames. Frame the postmortem as
    post-incident (incident closed). The audit files are the source of incident metadata.
  - **If no `*.json` files are found (directory absent or empty):** Emit the following
    advisory and continue scaffolding regardless:

    > Advisory: No active or recent Hotfix detected. If documenting a past incident,
    > proceed manually by reviewing `.armature/journal.md` for bypass-intent entries.

## Step 2 — Derive Slug

Derive a slug from `$ARGUMENTS`:

1. Convert to lowercase.
2. Replace all whitespace sequences with a single dash (`-`).
3. Strip all characters that are not alphanumeric (`a-z`, `0-9`) or a dash (`-`).
4. If the result is empty after stripping, use `unnamed`.

Document the derived slug to the human before writing the file. Example: the argument
`"Auth Token Leak"` becomes `auth-token-leak`.

## Step 3 — Ensure Target Directory Exists

Check whether `.armature/postmortems/` exists. If it does not exist, create it before writing
the postmortem document. This directory is a committed governance artifact (not gitignored).

## Step 4 — Scaffold the Postmortem Document

Write a new file to `.armature/postmortems/YYYY-MM-DD-<slug>.md` where `YYYY-MM-DD` is the
current date in UTC (ISO 8601 date format). Use the slug derived in Step 2.

The file content must follow this template exactly. Populate the `Incident Date` slot with the
current UTC timestamp. Leave all other slots as their angle-bracket placeholders for the human
to fill in. Slots marked `<!-- REDACT if sensitive -->` may be replaced with
`[REDACTED — see secure incident log]` if the content is sensitive.

```markdown
# Postmortem: <incident-title>

**File:** .armature/postmortems/YYYY-MM-DD-<slug>.md
**Postmortem Status:** Draft

---

## Incident Date

<!-- ISO 8601 UTC timestamp of the incident. Format: YYYY-MM-DDTHH:MM:SSZ -->
<YYYY-MM-DDTHH:MM:SSZ>

## Incident Summary

<!-- 1-2 sentences describing what failed and the user-facing impact. -->
<!-- REDACT if sensitive -->
<incident-summary>

## Phase at Incident

<!-- The SDLC phase active at the time the incident was declared (per §5.6). -->
<!-- This is the phase the orchestrator will return to after post-mortem closes. -->
<phase-at-incident-declaration>

## Gates Bypassed

<!-- List each gate ID that was bypassed under the hotfix lane (e.g., GATE-PHASE-001). -->
- <gate-id>

## Declared Scope of Fix

<!-- The exact scope declared in the bypass-intent journal entry. -->
<declared-scope>

## Human Who Authorized Bypass

<!-- Name or identifier of the human who authorized the hotfix lane bypass per §7.9. -->
<authorizer>

## Hotfix Actions

<!-- Chronological list of implementer actions taken during the hotfix. Include commit SHAs. -->
<!-- REDACT if sensitive -->
- <action-1>
- <action-2>

## Reviewer Verdict + Reference

<!-- The reviewer's PASS/FAIL verdict and a reference to the review file. -->
<!-- e.g., PASS — .armature/reviews/hotfix-<slug>-review.md -->
<verdict-and-reference>

## Root Cause

<!-- Analysis of the technical, process, or governance root cause. -->
<!-- REDACT if sensitive -->
<root-cause-analysis>

## Counter-Pattern

<!-- The recommended counter-pattern or design change that prevents recurrence. -->
<!-- This is the distilled recommendation. The full entry goes in antipatterns.md. -->
<counter-pattern>

## Follow-Up Tickets

<!-- Task IDs or issue references for follow-up work created by this postmortem. -->
- <follow-up-task-or-issue>

## Governance Gaps

<!-- Invariant IDs, hooks, or gates that should have caught this but did not. -->
<!-- Leave blank if no gaps identified. -->
<governance-gaps>

## Phase Transition Log

<!-- Timestamps of all phase transitions related to this incident. -->
<!-- e.g., Implementation → Hotfix at YYYY-MM-DDTHH:MM:SSZ -->
<!-- e.g., Hotfix → Implementation at YYYY-MM-DDTHH:MM:SSZ (post-mortem committed) -->
- <prior-phase> → Hotfix at <timestamp>
- Hotfix → <prior-phase> at <timestamp>

## Author

<!-- Postmortem author (orchestrator session) and human reviewers. -->
Author: <author>
Reviewers: <reviewers>

## Antipatterns.md Entry Summary

<!-- The distilled one-paragraph entry to be copied into .armature/antipatterns.md. -->
<!-- This paragraph becomes the catalog entry per §7.10. -->
<distilled-antipattern-paragraph>
```

## Step 5 — Append Antipatterns.md Entry

After the postmortem document is written, append a new entry to `.armature/antipatterns.md`.

- If `.armature/antipatterns.md` does not exist, create it with this header comment before
  appending:
  ```
  # Armature Antipattern Catalog
  <!-- Append-only. See ARMATURE.md §7.10. -->
  ```
- The entry must follow the structure defined in ARMATURE.md §7.10 and include:
  - **Title:** Short, scannable name for the antipattern
  - **Date:** ISO date this entry was committed (today's date)
  - **Originating incident or postmortem:** Path to the postmortem file just written
  - **Observed failure pattern:** From the postmortem's Root Cause section
  - **Recommended counter-pattern:** From the postmortem's Counter-Pattern section
  - **Related ADRs and invariants:** Populated from the postmortem's Governance Gaps section

Reference the postmortem file path in the entry: `.armature/postmortems/YYYY-MM-DD-<slug>.md`.

## Step 6 — Close Bypass-Intent Audit Record in Journal

Append a journal entry to `.armature/journal.md` that:

1. Cites the timestamp of the original bypass-intent entry (from the hotfix lane initiation).
2. Declares the postmortem status: `postmortem committed`.
3. References the postmortem file path: `.armature/postmortems/YYYY-MM-DD-<slug>.md`.
4. References the antipatterns.md entry added in Step 5.

The journal is append-only per §6.5. Do not edit prior entries; append only.

## Closing

Verify all slots in the postmortem document are populated (or explicitly marked `N/A`) before
considering the postmortem complete. The HOTFIX-001 audit hook (M8) will validate this
contract. Until HOTFIX-001 ships, the orchestrator performs this verification manually before
allowing the next normal-phase task to begin.
