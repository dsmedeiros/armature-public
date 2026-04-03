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

### Step 5: Confirm
Tell the human:
- Session state saved to `.armature/session/state.md`
- Taskmaster synced
- Governance journal current
- Current build candidate: {tag}
- Safe to run `/compact`

Remind the human: after compaction, CLAUDE.md will reload automatically (re-establishing orchestrator identity), the session state file and governance journal will be read to restore context.
