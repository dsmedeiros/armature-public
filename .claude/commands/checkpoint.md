---
description: >
  Save current Armature session state before compaction or session end.
  Updates session state file, syncs Taskmaster status, and confirms
  the current build candidate. Run this before /compact.
---

# Armature Checkpoint

You are the orchestrator. Save all current session state to disk so the session can be safely compacted or resumed later. Follow the checkpoint protocol defined in `.armature/ARMATURE.md` §6.2.

## Protocol

### Step 1: Update Session State
Write the current state to `.armature/session/state.md`:

- **Current Objective:** What is the human working toward?
- **Build Candidate:** What is the latest build candidate tag? If none, state "none."
- **Task Status:** For each Taskmaster task: ID, description, status (pending / delegated / complete / rejected / escalated).
- **Active Delegation:** Is any implementer currently working? If so, what task, what scope, when started?
- **Pending Reviews:** Any tasks awaiting reviewer pass?
- **Invariants Touched:** Which invariant IDs were relevant this session? Any ambiguities found?
- **Decisions Log:** Append any new decisions made since last checkpoint.
- **Discovered Context:** Append anything learned that isn't yet captured in agents.md or ADRs.

### Step 2: Sync Taskmaster
Query Taskmaster for all current task statuses. Ensure:
- No task is in an ambiguous state (e.g., marked "in-progress" with no active delegation)
- Completed tasks are marked complete
- Blocked or escalated tasks have accurate status
- Record the current Taskmaster task summary in the session state file under "Task Status"

### Step 3: Verify Journal
Confirm that all governance-relevant events from this session are recorded in `.armature/journal.md`. If any are missing (escalations, invariant exceptions, component onboarding, build candidate tags, rollbacks), append them now.

### Step 4: Confirm Build Candidate
State the current build candidate tag. If work has been accepted and committed since the last tag, ask the human if a new build candidate should be tagged before compaction.

### Step 5: Memory Consolidation (MANDATORY — every checkpoint where a memory store exists)

**Skip guard:** If the project has no persistent agent-memory store — i.e., `/resolve` Phase 6 has not been set up and `<memory-root>` does not exist or is empty — record `consolidation: N/A — no memory store configured` in `.armature/journal.md` and advance to Step 6. The rest of this step does not apply.

For projects that **do** have a memory store, memory consolidation runs on **every** checkpoint — the *step* is never skipped
and never deferred to a future "dedicated pass." Deferring it is exactly what lets
the index bloat past the memory-load budget, at which point entries beyond the
budget silently fail to load and are invisible when the memory index is loaded at
session start. It is the umbrella-clustering mechanism (sub-steps 5.2–5.6) that keeps the
`MEMORY.md` index within budget (see ARMATURE.md §6.2 step 5).

What the step **always** does is verify the hard budget gate (below). What is
*need-driven* is the amount of clustering work — see **"When active consolidation
is required"** below. A checkpoint with no new banks, an index under budget with
headroom, and no remaining stopgaps or un-clustered clusters is satisfied by the
verification alone: record it as a **verified no-op** rather than fabricating
clustering churn (which itself risks *over*-consolidation — collapsing genuinely
distinct entries just to "do something"). This is NOT an escape hatch that skips
the step unless a size threshold is crossed: that approach lets backlog sit
un-clustered across many checkpoints (it gates on a too-high size and on *new*
banks, ignoring backlog), which is how indexes bloat. The no-op here is
reachable **only** when backlog is fully cleared — any new bank, budget pressure,
or remaining un-clustered cluster forces active work.

**Memory path.** The per-project memory store lives at `<memory-root>` as defined
in `/resolve` Phase 6 ("Save Learnings"), which also explains how to resolve
`<memory-root>` robustly for Claude Code and other runtimes. This step reads and
writes `<memory-root>/MEMORY.md` (the index) and `<memory-root>/feedback_*.md`
(individual entry files). Do **not** re-derive the resolution here — consult
`/resolve` Phase 6 for the authoritative derivation.

**Hard budget gate (the success criterion):** after this step,
`<memory-root>/MEMORY.md` MUST be within the runtime's memory-load budget — for
Claude Code this is approximately **24.4 KB** (measure with `wc -c`). Content
beyond the load budget does not load and is silently dropped. If the index is over
budget, this step is **not done**; keep consolidating.

**To get/stay under budget, in priority order:**
1. **Umbrella consolidation (primary):** cluster L0 entries under L1 umbrellas
   (sub-steps 5.2–5.6) and **de-index the clustered children** (sub-step 5.4) so the index has
   fewer, richer top-level lines. Removing index lines — not just shortening
   them — is the real fix and the ONLY lever that lowers the line *count*.
2. **Terse descriptions (secondary):** compress surviving index lines to a
   one-line when/what pointer; full detail stays in the entry file.
3. **Title-only (last resort):** only where the title is fully self-describing
   and a long filename leaves no room.

**When active consolidation is required (vs. a verified no-op).** The hard budget
gate above is checked on **every** checkpoint regardless. Beyond that, perform
active clustering/de-indexing this checkpoint if **any** of these hold:
- **New banks:** ≥1 `feedback_*.md` banked since the last consolidation → cluster
  them under umbrellas (sub-steps 5.3–5.4).
- **Near budget:** `wc -c <memory-root>/MEMORY.md` ≥ **22 KB** (≈90% of the 24.4 KB Claude Code
  gate; adjust for other runtimes) → keep de-indexing as far as available
  clustering allows, to rebuild headroom before the next bank pushes it over.
- **Stopgaps remain:** any title-only or truncated index line persists from a
  prior checkpoint → convert it to proper umbrella structure.
- **Un-clustered backlog:** any cluster of 2+ L0 entries sharing an umbrella is
  still individually indexed → process at least the largest such cluster.

If **none** hold (0 new banks AND index < 22 KB AND no stopgaps AND no
un-clustered 2+ cluster), the step is a **verified no-op**: confirm `wc -c
<memory-root>/MEMORY.md` is within the load budget, record `"consolidation: verified, no work
required (N entries, X KB)"` in the journal, and proceed. Do **not** invent
clustering work for an empty checkpoint.

**While any trigger fires, backlog progress is mandatory — not just new entries.**
Cluster this session's new banks AND convert at least the largest remaining
un-clustered cluster. Stopping at "this session's new entries only" is what grows
the backlog. Once the backlog is fully cleared and the index sits under budget with
headroom, the triggers stop firing and the step becomes the verified no-op above —
that is the intended terminal state, not a regression.

**Protocol (conservative — never deletes content):**

**5.1 Inventory.** Run `wc -c <memory-root>/MEMORY.md` and `ls <memory-root>/feedback_*.md | wc -l`. Report current size and entry count. Identify entries banked since last consolidation: memory lives OUTSIDE the repo, so use `ls -t` to sort by mtime rather than `git log`.

**5.2 Classify breadth.** For each entry banked since last consolidation, classify into one of three layers:

| Layer | Scope | Examples |
|---|---|---|
| **L0 — Tool-specific** | One toolchain/file-format/library | Python shlex, Go gofmt, OPA Rego, GH Actions, Helm |
| **L1 — Pattern-specific** | Pattern across tools sharing a mechanism | silent-skip, drift between mirrored files, claim-of-invariance, scope-tightening |
| **L2 — Meta-discipline** | Process or decision-framework that applies to nearly all PRs | four-layer verification, red-team trigger, confirm-but-misdirected |

**5.3 Cluster L0 entries by shared L1 pattern.** For each L0 entry, identify the L1 umbrella it instances. If 2+ L0 entries share an umbrella, the cluster is consolidation-eligible. **Cluster scope is the WHOLE index, not just this session's new banks** — the budget gate (above) is satisfied by working down the existing backlog, so each checkpoint processes new entries plus at least the largest remaining un-clustered backlog cluster.

**5.4 Promote / extend umbrella entries.** For each consolidation-eligible cluster:
- If an L1 umbrella entry already exists, **extend** it with: (a) the new L0 instance in its `## Instances` section, (b) any new pattern triggers the L0 entry surfaced, (c) any new audit-checklist items.
- If no umbrella exists, **create** one. The umbrella file states the general principle + pattern triggers + audit checklist + lists the L0 entries as instances. Keep the L0 entry FILES; they hold the specific reproducer + fix template + tool-specific commentary.
- **De-index clustered children — THIS is the line-count reducer.** Once an L0 entry is listed in an umbrella's `## Instances` section, REMOVE its standalone top-level line from the `MEMORY.md` index. The L0 `.md` file is kept and stays reachable via the umbrella's Instances list — this is de-indexing, NOT deletion (sub-step 5.7). It is the only operation that lowers the index line count, so it is what makes the budget gate terminate when many already-terse L0 lines still exceed budget: N clustered children collapse to ~1 umbrella line. (The umbrella line is then visible when the memory index is loaded at session start; sub-step 5.9 verifies it still surfaces the children's scenarios.)

**5.5 Index hygiene.** For each entry in `MEMORY.md`:
- The index line MUST fit on one line, **≤ 200 chars** including the markdown link prefix. Compress overlong descriptions; move detail into the entry file.
- Format: `- [Title](filename.md) — One-line "when it applies" + "what to do" summary. Source: <PR/instance>. Parent: <umbrella entry>.`
- Index lines that exceed 200 chars are truncated by the memory-load tooling — anything past the cut is invisible when the memory index is loaded at session start. This is the #1 cause of "entry banked but never re-loaded" bugs.
- **Whole-file gate (binding):** the per-line ≤ 200 char rule is necessary but NOT sufficient. After hygiene, `wc -c <memory-root>/MEMORY.md` MUST be within the load budget (≤ 24.4 KB for Claude Code). The load tooling stops at the budget regardless of per-line length, so an index of many ≤200-char lines can still exceed the budget and drop its tail. If over, return to sub-step 5.4 and **de-index more clustered children** (collapsing L0 lines under umbrella `## Instances` is what reduces the line *count* — once the per-line link-prefix floor dominates, the whole-file budget cannot be met by shortening descriptions alone).

**5.6 Cross-reference.** Every L0 entry gains a `## Related disciplines` or `## Parent` section pointing at its umbrella. Every umbrella entry gains an `## Instances` section listing its children.

**5.7 NEVER delete entry FILES (de-indexing the top-level line IS allowed).** Consolidation never deletes a `feedback_*.md` FILE — every banked lesson stays on disk and reachable via its umbrella's `## Instances` list. What it DOES remove is an entry's standalone top-level INDEX LINE once that entry is represented under an umbrella (sub-step 5.4); that line-count reduction is the point of consolidation and what lets the hard budget gate terminate. Even if two entries seem to overlap completely, keep both files — the second captured something the first didn't or it wouldn't have been banked. Merge their checklists into the umbrella, leave the originals as instance pointers.

**5.8 Record the consolidation in the journal.**
Append an entry to `.armature/journal.md`:
```
## YYYY-MM-DD — Memory consolidation
- Pre: N entries, X KB index (L lines)
- Post: N' entries, Y KB index (L' lines)  (Δ index = -Z KB, -ΔL lines)
  (N' = N + the number of NEW umbrella FILES created this checkpoint. Consolidation NEVER deletes a file, and de-indexing a child removes its INDEX line (lowering L' — the line count), NOT its file (N is unchanged by de-index). So write "Post: N entries (unchanged)" ONLY when 0 umbrellas were created; otherwise N' = N + umbrellas-created.)
- Umbrellas extended/created: M  (only CREATE adds a file and raises N'; extend and de-index do not)
- Cross-references added: K
```
Note: memory lives OUTSIDE the repo — use `ls -t` by mtime, not `git log`, to find recently-banked entries.

**5.9 Sanity check.** After consolidation, spot-check by picking a recent finding from the journal and verifying the consolidated discipline corpus would still surface the relevant entries when the memory index is loaded at session start. If the consolidation hid a checklist item, restore it to the umbrella.

### Step 6: Confirm
Tell the human:
- Session state saved to `.armature/session/state.md`
- Taskmaster synced
- Governance journal current
- Current build candidate: {tag}
- Safe to run `/compact`

Remind the human: after compaction, CLAUDE.md will reload automatically (re-establishing orchestrator identity), the session state file and governance journal will be read to restore context.
