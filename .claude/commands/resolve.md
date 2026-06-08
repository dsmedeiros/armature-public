---
description: >
  Drive a PR to clean state. Red-team reviewer findings first — confirm
  each bug is real and in the direction claimed before fixing anything.
  Reply with citations to false alarms; fix confirmed issues surgically
  with a security-, observability-, auditability-, and governance-first
  lens. Save non-obvious findings as agent-memory learnings so the next
  PR does not re-learn the same lesson. Then request re-review.
argument-hint: "[<pr-number>]"
discipline-tags: [definition-of-done]
---

# Resolve

You are the orchestrator. The user has invoked `/resolve` to drive a pull request to a clean, reviewable state by resolving every outstanding issue — unresolved review conversations, open comments, and CI failures — and to capture the durable learnings from the review cycle before requesting re-review.

(File and command name follow the single-noun convention in [`.claude/commands/agents.md`](../../.claude/commands/agents.md) alongside `/spec`, `/postmortem`, and `/checkpoint`. The protocol's exclusive scope is pull-request resolution; that scope is documented here and in the command description rather than encoded in the filename.)

This command codifies a triage-first protocol that protects against two failure modes seen across governed projects: (1) reviewers — especially automated ones — confidently flag non-bugs, and silently implementing a fix for a non-bug pollutes the audit trail; (2) the durable learnings from one PR review cycle evaporate after the session compacts unless they are externalized. The Save Learnings phase (§Phase 6) addresses the second by writing structured memory entries to the agent's persistent memory store.

## Fix-Evaluation Lens

This command does **not** introduce new normative policy. Every fix proposed in this protocol is evaluated against four pre-existing disciplines already governed by the standards corpus and ARMATURE.md. The lens below is a per-decision checklist that composes those disciplines for the specific context of accepting or rejecting a reviewer-proposed fix; it is not a new governance concept and does not bind any project that did not already opt into the underlying disciplines via [`.armature/disciplines/triggers.yaml`](../../.armature/disciplines/triggers.yaml).

When facing a design choice in any phase below, ask: **"Does this preserve or weaken the security / observability / audit / governance posture already encoded in the project's disciplines and invariants?"** If it weakens any of them, choose the harder path. The four lenses and the disciplines that authorize them:

1. **Security lens** — fail-closed defaults; never widen trust boundaries, broaden auth fallbacks, weaken cryptographic verification, or ship a bypass enabled-by-default. Environment-variable guards alone are insufficient (operators misconfigure them). Authority: [`.armature/disciplines/owasp-checklist.md`](../../.armature/disciplines/owasp-checklist.md) (OWASP-aligned security review), [`.armature/disciplines/guardrail-rules.md`](../../.armature/disciplines/guardrail-rules.md) (fail-closed defaults), [`.armature/disciplines/error-handling.md`](../../.armature/disciplines/error-handling.md).
2. **Observability lens** — every control-plane decision, security action, and fail-closed rejection must be loggable and metrically countable; silent skips become explicit errors or auditable warnings tied to an opt-in flag. Authority: [`.armature/disciplines/metrics.md`](../../.armature/disciplines/metrics.md), [`.armature/disciplines/error-handling.md`](../../.armature/disciplines/error-handling.md).
3. **Auditability lens** — every state change is traceable end-to-end; do not drop data-integrity constraints, remove audit columns, or modify already-applied historical artifacts (migrations, journal entries per ARMATURE.md §6.5, postmortems per §7.9, accepted reviewer verdicts). When a reviewer flags a bug introduced by removing a constraint, restore the constraint — never "add an application check instead." Authority: [`.armature/disciplines/data-handling.md`](../../.armature/disciplines/data-handling.md), [`.armature/disciplines/definition-of-done.md`](../../.armature/disciplines/definition-of-done.md), ARMATURE.md §6.5 (journal append-only), §7.9 (postmortems), §7.10 (antipatterns).
4. **Governance lens** — respect the Armature pipeline (orchestrator → planner → implementer → reviewer per ARMATURE.md §4), the scoped `agents.md` authority for every component touched, and entries in `.armature/invariants/registry.yaml`. If a reviewer's proposed fix conflicts with an invariant, push back rather than implement it; cite the invariant ID in your reply. Authority: [`.armature/disciplines/adr-process.md`](../../.armature/disciplines/adr-process.md), [`.armature/disciplines/code-review.md`](../../.armature/disciplines/code-review.md), [`.armature/disciplines/definition-of-done.md`](../../.armature/disciplines/definition-of-done.md), ARMATURE.md §4 (agent topology), §3.7 (invariant registry).

If a project's `triggers.yaml` does not activate one of these disciplines, the corresponding lens is advisory rather than non-negotiable in that project — projects scope their own discipline activation. The lens framing is a useful general-purpose checklist regardless, but its *binding force* always traces back to the project's own discipline configuration.

## Inputs

The user may provide a PR number via `$ARGUMENTS`. If not, detect the PR associated with the current branch via `gh pr view --json number,url,headRefName`. If no PR is associated with the current branch, ask the user for the PR number rather than guessing.

**`gh api` placeholder contract.** Per the [gh manual](https://cli.github.com/manual/gh_api), only `{owner}`, `{repo}`, and `{branch}` are auto-expanded inside `gh api` endpoint paths. **`{number}` is NOT auto-expanded** and will be sent literally, hitting an endpoint that does not exist. Throughout this protocol, capture the PR number once at the start of Phase 1 into a shell variable named `number` and substitute it via `$number` in every endpoint path. The `{owner}/{repo}` substitutions are left as-is because they DO auto-expand and the auto-expansion is preferable to brittle hard-coded values that drift when the protocol is invoked from a fork or against a transferred repo.

**`-f` vs `-F` field flags.** `gh api` (REST and `graphql`) accepts two field flags with different semantics, and choosing wrong silently corrupts the call:
- `-F` / `--field` applies **magic coercion** — values that look like `true`, `false`, `null`, or an integer are sent as that type, and a value beginning with `@` is read as a **filename**.
- `-f` / `--raw-field` always sends the literal **string**, with no coercion and no `@file` expansion.

Rule of thumb used below: **free text and opaque strings use `-f`** (reply bodies — which often start with `@mention` or could be the literal text `true`/`123`; owner/repo logins; pagination cursors; GraphQL node IDs), and **only genuinely-typed values use `-F`** (the PR `number`, which must arrive as the GraphQL `Int!`). Using `-F body=` for a reply that starts with `@codex` would make `gh` try to open a file named after the mention and fail the call.

## Protocol

### Phase 1: Gather State

0. **Capture the PR number into a shell variable.** Used by every endpoint call below:
   ```
   number="$ARGUMENTS"
   [ -z "$number" ] && number=$(gh pr view --json number --jq '.number')
   [ -z "$number" ] && { echo "no PR number; ask the user"; exit 1; }
   ```

1. **Fetch PR metadata:**
   ```
   gh pr view "$number" --json number,url,title,headRefName,reviews,statusCheckRollup
   ```
   The `reviews` array carries each review's top-level `body`, `state` (`CHANGES_REQUESTED` / `COMMENTED` / `APPROVED`), and `author`. This is a **distinct finding surface** from diff review threads (step 2) and timeline comments (step 3): a reviewer — especially an automated one — can request changes or raise actionable findings in the review `body` alone, with no diff-anchored comment. Extract every review carrying a non-empty `body` and treat it as a Phase 2 triage item:
   ```
   gh pr view "$number" --json reviews \
     --jq '.reviews[] | select(.body != "") | {author: .author.login, state: .state, body: .body}'
   ```
   Like timeline comments, review bodies are not threaded and have no `isResolved` state — they are addressed by reply only (Phase 5, step 5).

2. **Fetch all review comments (unresolved conversations):**
   ```
   gh api "repos/{owner}/{repo}/pulls/$number/comments" --paginate
   ```
   Also fetch review threads to identify which are resolved vs unresolved. The GraphQL `reviewThreads` connection is paginated — `first: 100` returns at most one page, and the protocol's promise to resolve **every** outstanding issue requires walking `pageInfo.hasNextPage` / `endCursor` until the cursor is exhausted. A single fixed-page query silently drops later threads on PRs with more than 100 conversations.
   ```
   # Paginated walk using GraphQL variables ($owner/$repo/$number/$cursor)
   # passed as field flags so we never string-interpolate values into the
   # query body (strings use -f, the Int! number uses -F; see the -f/-F note above).
   # IMPORTANT: the FIRST request must NOT pass a cursor. `reviewThreads(after:)`
   # rejects an empty-string cursor — passing `cursor=""` would send `after: ""`,
   # which errors before any page is fetched. Omit the cursor arg entirely
   # on the first iteration so the nullable `$cursor` variable defaults to null
   # (→ `after: null` → first page). Only pass the cursor once endCursor is known.
   owner=$(gh repo view --json owner --jq '.owner.login')
   repo=$(gh repo view --json name --jq '.name')
   cursor=""
   while :; do
     # owner/repo/cursor are strings → -f (a numeric-looking login or an
     # opaque cursor must not be coerced); number is the GraphQL Int! → -F.
     args=(-f owner="$owner" -f repo="$repo" -F number="$number")
     [ -n "$cursor" ] && args+=(-f cursor="$cursor")
     page=$(gh api graphql "${args[@]}" \
       -f query='query($owner:String!,$repo:String!,$number:Int!,$cursor:String) {
         repository(owner:$owner, name:$repo) {
           pullRequest(number:$number) {
             reviewThreads(first:100, after:$cursor) {
               pageInfo { hasNextPage endCursor }
               nodes { isResolved id comments(first:10) { nodes { databaseId body author { login } path line } } }
             }
           }
         }
       }')
     echo "$page" | jq '.data.repository.pullRequest.reviewThreads.nodes[]'
     has_next=$(echo "$page" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage')
     [ "$has_next" = "true" ] || break
     cursor=$(echo "$page" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.endCursor')
   done
   ```

3. **Fetch top-level PR timeline comments.** The two calls above return only *diff* review comments (comments anchored to a line in the diff). Reviewers and bots frequently post findings as top-level PR comments, which live on the **issues** API — GitHub treats every pull request as an issue for this endpoint. Skipping this call means Phase 2 never triages those findings and Phase 5 never replies, so `/resolve` can report a clean PR while actionable comments remain open:
   ```
   gh api "repos/{owner}/{repo}/issues/$number/comments" --paginate
   ```
   Timeline comments are not threaded and have no `isResolved` state, so they are addressed by reply only (Phase 5) — there is no `resolveReviewThread` step for them. Treat each substantive one as a finding for Phase 2 triage just like a diff comment.

4. **Fetch CI status:** Identify failing checks from `statusCheckRollup`. For each failure, fetch logs via `gh run view <id> --log-failed` or `gh api` as needed.

5. **Read the relevant agents.md** for every component touched by the PR (use the routing table in CLAUDE.md). Read relevant ADRs. These constrain what fixes are acceptable.

### Phase 2: Red-team the reviews (verify before acting)

**Do not trust reviewer findings by default.** Automated reviewers (codex, greptile, and similar bots) and human reviewers operate on local context — they see the diff and the surrounding lines, but not the full architecture, invariants, recent decisions, or design intent. They can be wrong about whether the bug exists, the direction of harm, the severity, or the proposed fix. Thrashing on fixes because a reviewer was confidently wrong is more costly than a thoughtful pushback.

**Before planning a fix, audit every finding with an adversarial eye:**

1. **Read the actual code the finding cites.** Not just the flagged lines — the function body, its callers, and whatever invariant or data path the reviewer claims is broken. Confirm the bug is real and in the direction claimed.

2. **Construct a concrete harm scenario.** If the reviewer says "X can happen," trace an interleaving or input that actually produces X. If you cannot construct one, the finding may be speculative.

3. **Check the direction of harm.** A common reviewer error is getting the direction backwards — e.g., claiming "this causes events to be dropped" when the code actually re-delivers them. Make sure the claimed failure mode matches the code's real behavior.

4. **Verify the proposed fix.** Reviewer-suggested fixes can weaken invariants, break other callers, or solve a non-problem. Before implementing, trace whether the fix preserves security / observability / audit / governance and does not regress a callsite the reviewer did not consider.

5. **Triage each finding into one of:**
   - **Confirmed** — real bug, clear fix path. Proceed to Phase 3.
   - **Confirmed but misdirected** — real bug, but reviewer's proposed fix is wrong or incomplete. Fix the underlying issue correctly; explain the divergence in the reply.
   - **False alarm** — code is correct, reviewer misread it. Do NOT fix; reply with a citation explaining why (file:line, invariant, test, or concrete non-failing interleaving).
   - **Partial / wrong severity** — real but not what the reviewer claimed. Fix the actual issue, not the claimed one; clarify in the reply.
   - **Out of scope** — real but unrelated to this PR. File a separate issue; reply with the issue link.

6. **Output a triage table before implementing anything.** For each review thread: finding summary, your verdict, cited evidence. This forces you to articulate the reasoning and catches cases where you were about to fix something that was not broken.

**Pushback is expected.** Reviewers are stakeholders, not authorities. A polite, well-cited "this is working as intended because [invariant/test/interleaving]" reply is the correct response to a false alarm. Silently implementing a fix for a non-bug pollutes the commit history and trains future reviewers to trust bad findings.

### Phase 3: Analyze and Plan

For each finding that survived Phase 2 triage:

1. **Understand the issue.** Read the referenced file and surrounding code. Understand *why* the reviewer flagged it — and why Phase 2 confirmed it.
2. **Check for related issues.** Search the codebase for similar patterns — if the reviewer found a bug in one place, the same bug likely exists elsewhere. Fix all instances, not just the one flagged.
3. **Plan a surgical fix.** The fix must be:
   - **Precise:** Change only what is necessary. No drive-by refactors, no formatting changes, no unrelated improvements.
   - **Regression-free:** Run targeted tests for every file touched. If a test does not exist, consider whether one is needed — especially for the security / observability / audit paths the change touches.
   - **Security-first:** Never weaken security, auditability, data integrity, or governance. If two approaches exist and one is more secure, choose it. Bypass flags default to `false`; fallbacks are narrowly gated (specific error reason, not "any error"); auth decisions remain cryptographically grounded.
   - **Observable:** Any new error path, skip path, or fallback must emit a structured log or metric that makes it auditable post-hoc. Replace silent skips with explicit errors or an opt-in flag + auditable warning.
   - **Auditable:** No modifications to applied migrations or other historical artifacts. No dropping integrity constraints to "simplify" a fix. Preserve the audit trail end-to-end.
   - **Governance-compliant:** Verify the fix respects all relevant ADRs and invariants from `.armature/invariants/registry.yaml`. If a reviewer's suggestion conflicts with an invariant, cite the invariant ID in your reply and propose a compliant alternative instead of implementing the conflicting fix.

### Phase 4: Implement Fixes

For each finding that survived Phase 2 triage and was planned in Phase 3:

1. **Delegate to the appropriate scoped implementer** (per the routing table) if the fix crosses component boundaries. Otherwise, make the fix directly within the active scope's authority (per the scope's agents.md).
2. **Run targeted tests** for every package or module touched, using the project's test invocation (per `config.yaml` `governance.ci-review-pipeline.test-command` if set, otherwise the project's standard test runner). Escalate to a broader test suite only after focused tests pass.
3. **Stage and commit** each logical fix separately using Conventional Commits format. Keep commits small and atomic — one fix per commit when practical.

### Phase 5: Respond to Review Threads, Review Bodies, and Timeline Comments

Address three distinct comment surfaces, all gathered in Phase 1:
- **Diff review threads** (from the `reviewThreads` walk) — reply then resolve (steps 1–3 below).
- **Top-level timeline comments** (from `issues/$number/comments`) — reply only; they are not threaded and have no resolve state (step 4 below).
- **Pull-request review bodies** (from the `reviews` array, Phase 1 step 1) — reply only; like timeline comments they are not threaded and have no resolve state (step 5 below).

For each unresolved conversation (including findings you rejected as false alarms):

1. **Post a reply comment** on the review thread explaining:
   - For **confirmed** findings: what was fixed (commit SHA + brief description). If the fix addresses related instances found elsewhere, mention those too.
   - For **false alarms**: a polite, well-cited explanation of why the code is correct. Cite the relevant file:line, invariant ID, test name, or concrete non-failing interleaving that demonstrates the finding is wrong. Do not leave false alarms silent — unresolved threads accumulate and the next reviewer will re-raise them.
   - For **confirmed-but-misdirected** or **partial** findings: explain the divergence between what the reviewer proposed and what you actually shipped, and why.
2. Post the reply. Two endpoints exist; prefer the GraphQL thread-reply mutation because it is keyed by `thread_id` and cannot mis-target:
   - **GraphQL (preferred)** — keyed by the `thread_id` captured in Phase 1, so it always lands on the exact thread regardless of duplicate line/text collisions:
     ```
     # -f for both: $thread_id is an opaque node ID and $reply is free text
     # (often starts with @mention) — neither may be coerced or @file-expanded.
     gh api graphql -f id="$thread_id" -f body="$reply" -f query='mutation($id:ID!,$body:String!) {
       addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$id, body:$body}) { comment { id } }
     }'
     ```
   - **REST (alternative)** — the endpoint requires the REST `databaseId` of the **top-level** comment in the thread (NOT a reply id). That id is `comment_id = .comments.nodes[0].databaseId` from the Phase 1 `reviewThreads` walk (the query now captures `databaseId` for exactly this purpose). Matching by `path`/`line` alone is unreliable when multiple unresolved threads share a line or identical bot text, so always carry the `databaseId` from the thread node rather than re-deriving it from the flat REST comment list:
     ```
     comment_id=$(echo "$thread_json" | jq -r '.comments.nodes[0].databaseId')
     gh api "repos/{owner}/{repo}/pulls/$number/comments/$comment_id/replies" -f body="$reply"
     ```

3. **Mark the thread resolved** via the GraphQL `resolveReviewThread` mutation. Posting a reply does **not** flip `isResolved` — without this step the thread stays open even though it has been addressed, Phase 7's "conversations resolved" count is inflated, and the next reviewer sweep will re-surface the same finding. Use the `thread_id` (node ID, `PRRT_…`) captured during Phase 1's paginated `reviewThreads` walk:
   ```
   gh api graphql -f query='mutation($id:ID!) {
     resolveReviewThread(input:{threadId:$id}) { thread { id isResolved } }
   }' -f id="$thread_id"
   ```
   Resolve threads only after the reply is posted, so the audit trail captures the citation before the thread closes. False-alarm threads are resolved the same way: the reply explains the reasoning, the resolution marks the thread as addressed. If a thread is genuinely undecidable (rare — usually means Phase 2 triage was incomplete), leave it open and flag in the Phase 7 report.

4. **Respond to top-level timeline comments** (from Phase 1 step 3). These are not threaded, so there is no resolve mutation — a reply is the only acknowledgement. Post a new top-level comment that references the original (by author + paraphrase, since timeline comments have no per-comment reply endpoint) and states the disposition (fixed in <SHA> / false alarm with citation / out of scope with issue link):
   ```
   gh api "repos/{owner}/{repo}/issues/$number/comments" -f body="$reply"
   ```
   Because these cannot be marked resolved, they will keep showing in the timeline; the Phase 7 report must enumerate which timeline findings were addressed and how, so the human can confirm none were silently skipped.

5. **Respond to pull-request review bodies** (from Phase 1 step 1). A `CHANGES_REQUESTED` or `COMMENTED` review can carry actionable findings in its top-level `body` with no diff-anchored comment. There is no per-review reply endpoint and no resolve mutation, so acknowledge each substantive review body with a new top-level comment that references the review (by author + state + paraphrase) and states the disposition (fixed in `<SHA>` / false alarm with citation / out of scope with issue link):
   ```
   gh api "repos/{owner}/{repo}/issues/$number/comments" -f body="$reply"
   ```
   As with timeline comments, review bodies cannot be marked resolved, so the Phase 7 report must enumerate which review-body findings were addressed and how. A `CHANGES_REQUESTED` review whose body is left unaddressed also continues to block merge, so none may be silently skipped.

### Phase 6: Save Learnings

For each non-obvious finding that would help future reviewers — especially findings that touch security, observability, auditability, or governance — save a memory entry so the next PR does not re-learn the same lesson. The agent's persistent memory store survives session boundaries and compaction; the journal and antipatterns catalog do not capture every reviewer interaction at this granularity.

**Where memory lives — NOT in the repo worktree.** The agent's persistent memory store is the runtime's *external, user-level* memory directory (e.g. the Claude Code per-project memory root resolved from the absolute project path, outside the checked-out tree). It is **not** a repo-relative `.claude/projects/...` path — writing there would create untracked files inside the repository and leave `/resolve` with a dirty worktree, directly contradicting the command's clean-state goal. Resolve the concrete location from the runtime. For Claude Code this is the per-project directory `~/.claude/projects/<project-slug>/memory/`, where `<project-slug>` is the project's absolute path with each path separator — and, on Windows, the drive-letter colon — replaced by `-` (e.g. `/home/me/app` → `~/.claude/projects/-home-me-app/memory/`; `C:\Users\me\app` → `~/.claude/projects/C--Users-me-app/memory/`). Claude Code keys this per-project store to the **main repository root** and shares it across all linked worktrees, so derive `<project-slug>` from the main worktree root — not from whatever directory `/resolve` happens to run in. Obtain that root robustly with `git worktree list --porcelain | sed -n '1s/^worktree //p'`: the first entry is always the main worktree, regardless of whether the command runs from the main checkout or a linked worktree. (Do **not** rely on `git rev-parse --show-toplevel` for this — in a standard linked worktree it returns the *linked* worktree's own root, yielding the wrong slug.) Then confirm by listing `~/.claude/projects/` and matching the entry whose name is the *exact* encoding of that main-repo root (not a prefix — per-worktree slug directories exist and share it as a prefix, but shared memory is loaded from the main-root slug, not those). For other runtimes, use the equivalent user-level agent-memory location. If a project deliberately wants in-repo memory, that directory MUST be gitignored before any entry is written. Below, `<memory-root>` denotes that external per-project memory directory.

1. **Save a `feedback`-type memory entry** to `<memory-root>/feedback_<short-slug>.md` using the memory-system frontmatter schema (`name`, `description`, `metadata.type: feedback`). The body MUST structure as:
   - **Rule:** the rule (what to do / not do), stated as the lead line.
   - **Why:** the reason — framed in terms of the four first-principle concerns. Which guarantee was weakened, which signal was lost, which audit path was broken, or which invariant was at risk. Include the originating PR number and reviewer when known so future readers can trace provenance.
   - **How to apply:** when this guidance kicks in (file pattern, config shape, review-trigger cue, language idiom). Future-you reads this line first to decide whether the memory is relevant to the current change.
2. **Update the memory index at `<memory-root>/MEMORY.md`** with a one-line pointer in the format `- [Title](file.md) — one-line hook`. The index file lives next to the memory entries (same `<memory-root>` directory) so the runtime can find it deterministically at session start; an index written anywhere else is invisible across sessions and creates a silent split-brain across implementations.
3. **Flag structural gaps to the user at the end of the run.** If the finding reveals a structural gap — a missing invariant in `.armature/invariants/registry.yaml`, a missing ADR, a missing CI check, a missing reviewer persona — do not silently absorb governance debt. Surface it in the Phase 7 report so the human can decide whether to file a follow-up task. Recurring structural gaps (the same class of finding showing up in multiple PRs) are also candidates for promotion into `.armature/antipatterns.md` via `/postmortem` — though that is a separate decision the human makes.

Memory entries are scoped to the agent's external persistent memory, not to `.armature/` and not to the repo worktree. They are not committed governance artifacts. Governance-relevant decisions (exception, rollback, build-candidate tag, invariant interaction) still go to `.armature/journal.md` per ARMATURE.md §6.5; the two stores serve different purposes and the orchestrator writes to both as appropriate.

### Phase 7: Request Re-Review

1. **Verify CI is green:**
   ```
   gh pr checks "$number"
   ```
   If any check is still failing, investigate and fix before proceeding. Do not request re-review while CI is red — the reviewer will re-flag the failure as a new finding.

2. **Post the re-review request** as a top-level PR comment, using whichever bot trigger is configured for the project (e.g., `@codex review this`, `@greptileai review`, or a project-specific tag). The `config.yaml` `governance.ci-review-pipeline.final-reviewer-trigger` field declares this string when CI-driven review is wired up; otherwise ask the user. Use `gh pr comment` (its `--body` takes the text literally — no field-flag coercion, so a leading `@mention` is safe):
   ```
   gh pr comment "$number" --body "$trigger"   # e.g. trigger="@codex review this"
   ```

   **Clean-pass rule — do not re-request a reviewer that has already passed.** Before posting the trigger, resolve the reviewer's author login by this precedence:

   1. Use `config.yaml` `governance.ci-review-pipeline.final-reviewer` (a bot login) if it is set.
   2. Else derive it from what the project has configured or what Phase 1 observed: check `governance.ci-review-pipeline.review-bots[].name` for configured bot logins, and check the Phase 1 `reviews` array for the author logins of automated reviews on this PR. If exactly one automated reviewer is identifiable from these sources, treat that login as the reviewer.
   3. **Else — if the reviewer's identity cannot be determined — fail safe: do NOT treat any prior review as a clean pass. Post the re-request.** Silently skipping a final re-review on an unidentifiable reviewer is the unsafe failure mode; a redundant request is always preferable.

   Once the login is resolved, check whether that author has already given a clean pass on the current PR state. `final-reviewer-trigger` is only the comment text to post, not the reviewer's identity. Identify a clean pass by intent, not a literal phrase: any review that surfaces no actionable findings — no numbered issues, no suggested changes — whether phrased "no issues found", "LGTM", or "looks good". A comment that merely summarizes the diff or proposes an optional follow-up, with no blocking finding, still counts as clean. **Important:** an acknowledgment reaction (e.g. a 👍 on the trigger comment) is NOT a clean pass — it only signals the request was received (and may be the reviewer's configured ack-emoji per ARMATURE.md ack-emoji config), so reactions must never be treated as a clean-pass signal. Phase 1 does not fetch per-comment reactions (they live on a separate `.../issues/comments/{id}/reactions` endpoint that this protocol does not call), so reaction state is unavailable regardless; rely exclusively on the review text gathered in Phase 1.

   Once a reviewer has given such a clean pass, **do not re-trigger it even after you push fixes for other reviewers' findings** — a fresh pass on top of an already-clean verdict is redundant noise. Still address and reply to the other reviewers' threads (Phase 5), and report the prior clean pass in the Phase 7 summary.

   Re-request a reviewer that already passed **only when:**
   - **(a)** The user explicitly instructs it; OR
   - **(b)** The changes pushed since the clean pass are **substantial** — use the project's `changeset-budget` (`.armature/config.yaml`) as the objective bar: cumulative post-clean-pass changes exceeding `changeset-budget.warn-loc` (currently 500 LOC), OR spanning multiple components, OR materially reworking the logic or security surface the reviewer originally cleared. A one-line or comment-only fix for another reviewer's nit does NOT clear the bar. To measure this: obtain the commit the clean-pass review was submitted against — GraphQL `pullRequest.reviews` nodes expose `commit { oid }` (the commit SHA the review was submitted against), or match the review's `submittedAt` timestamp against `git log` on the PR branch — then run `git diff <clean-pass-sha>..HEAD --numstat` and sum the totals against `changeset-budget.warn-loc`.

   When you re-request on basis (b), state the rationale (what changed since the clean pass) in the comment so the re-review is scoped. When in doubt, default to NOT re-requesting and surface the judgment call to the user.

   This rule is reviewer-agnostic: it applies to whichever automated reviewer is identified via the resolution chain above (login from `final-reviewer`, falling back to configured `review-bots[].name` or observed Phase 1 review authors; fail-safe when indeterminate). `final-reviewer-trigger` is the text to post, not the reviewer's identity. Reviewers that did flag issues are handled through their own threads as usual (Phase 5).

3. **Report to the user:** Summarize:
   - The Phase 2 triage breakdown (N confirmed, N false alarms, N partial/misdirected, N out-of-scope)
   - What was fixed and where (commit SHAs)
   - What was rejected as a false alarm and the citation for each rejection
   - How many diff review threads were resolved (Phase 5 step 3 mutation count), and any intentionally left open with rationale
   - Which top-level timeline comments were addressed and how (Phase 5 step 4) — these cannot be marked resolved, so enumerate them explicitly so none are silently skipped
   - Which pull-request review bodies were addressed and how (Phase 5 step 5) — likewise unresolvable, so enumerate them explicitly; flag any unaddressed `CHANGES_REQUESTED` review since it still blocks merge
   - Any new memory entries saved (file paths, one-line hooks)
   - Current CI status
   - Any structural gaps flagged (missing invariant, missing ADR, missing CI check, missing reviewer persona) — explicitly, so the human can decide on follow-up
   - Whether the re-review request was posted (with the comment reference) — or, if the configured reviewer had already given a clean pass, a note that the re-request was intentionally skipped per the clean-pass rule above (and that the user can ask for a fresh pass if they want one)

## Constraints

- **Never force-push.** Always add new commits on top. Force-pushing destroys review history and breaks the audit trail from thread to commit.
- **Never skip hooks.** If a pre-commit hook fails, fix the underlying issue. `--no-verify`, `--no-gpg-sign`, and similar bypasses are off-limits unless the user explicitly instructs otherwise.
- **Never modify already-applied historical artifacts.** Applied migrations, committed journal entries, accepted reviewer verdicts, and committed postmortems are immutable. Create new corrective artifacts instead (a new migration, a new journal entry, a follow-up review). Corrective change must be additive and idempotent.
- **Never weaken data-integrity constraints to make a test pass.** If a CHECK, FK, RLS policy, or schema validation is blocking a fix, the fix is wrong. Preserve the integrity guarantee; change the application logic instead.
- **Never default a bypass to enabled.** Auth-debug headers, dev-only listeners, and any other security bypass must default to `false` / disabled and require an explicit opt-in. Relying solely on environment-variable guards is insufficient — operators forget to set them in staging / demo / CI.
- **Fail-closed.** If you cannot determine the correct fix for an issue, escalate to the user rather than guessing. When empty / unset config would silently skip an assertion, prefer a hard error with an opt-out flag over a warning.
- **Scope discipline.** Each implementer agent stays within its declared component boundary per the routing table in CLAUDE.md. Cross-scope fixes require explicit orchestrator coordination. Do not let a single reviewer comment pull you into a refactor that touches five components.
- **Audit trail.** Every fix must be traceable — the commit message references the review thread ID or CI failure it addresses; the thread reply cites the commit SHA. Update `.armature/journal.md` per ARMATURE.md §6.5 when the fix touches an invariant or triggers a governance-relevant decision (exception, rollback, build-candidate tag).
- **Invariant integrity.** Before implementing a fix, cross-check against `.armature/invariants/registry.yaml`. If a reviewer's suggestion conflicts with an invariant, cite the invariant ID in your reply, propose a compliant alternative, and do not ship the conflicting change.

## Cross-References

- ARMATURE.md §6.5 — Governance journal append-only protocol (used by the journal-write directives in Phase 4–6).
- ARMATURE.md §7.10 — Antipattern catalog (the destination for recurring structural gaps surfaced by Phase 6).
- `.armature/invariants/registry.yaml` — The invariant registry that Phase 3 and the constraints section both consult.
- `.armature/personas/orchestrator.md` — The orchestrator persona this command operates as.
- CLAUDE.md routing table — The scope-to-implementer mapping referenced by Phase 1 step 5 and Phase 4 step 1.
