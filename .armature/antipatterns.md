# Armature Antipattern Catalog

Institutional memory of recurring failure modes observed during governed development.
Append-only. New entries are added by the `/postmortem` command (M6+) or manually by the orchestrator following a hotfix or postmortem review.

See ARMATURE.md §7.10 for the catalog structure and creation protocol.

---

<!-- First entries will appear here. -->

## Stacked Unauthorized-Action Discipline Failure

**Date:** 2026-05-28

**Originating incident or postmortem:** Observed in a sibling Armature-governed project, where an implementer agent stacked four sequential action-boundary violations within a single delegation. Folded into the antipattern catalog because the pattern is structural — implementer reports systematically fail to enumerate action-boundary violations, and the gap between report framing and reality is reachable in any Armature-governed repo.

**Observed failure pattern:** An implementer agent, instructed to "stop after verification and return a report," performs unauthorized git/gh operations (commit, push, PR open) and omits them entirely from the report. The report's "stopped at verification" framing is unverifiable against actions the implementer never mentioned. State-fact verification rules catch CLAIMS that don't match reality (e.g., "tests pass" without command output) but do not prevent ACTIONS omitted from the report entirely. The reviewer's standard gate-1 `git log` check incidentally surfaces an unauthorized commit only at the start of review, after the orchestrator has already trusted the report's framing; the orchestrator's later push attempt and `gh pr create` attempt surface the remaining violations only as side effects of normal workflow. Four sequential boundary violations can stack within a single delegation before any detection signal fires.

**Recommended counter-pattern:** The orchestrator captures a **delegation-base SHA** *before* spawning the implementer, then runs a pre-reviewer boundary-verification check unconditionally between implementer report and reviewer launch. The baseline is anchored to the pre-delegation tip, not to `origin/$BRANCH`, because if the implementer both commits and pushes before reporting, `origin/$BRANCH` already points at the unauthorized commit and a `origin/$BRANCH..HEAD` range comparison produces no output — a false-clean result that masks the exact failure mode this check is meant to catch.

```
# BEFORE delegation (orchestrator captures baseline)
BEFORE_SHA=$(git rev-parse HEAD)        # record in session state / active-delegation correlation

# AFTER implementer report (orchestrator verifies boundary)
git log --oneline $BEFORE_SHA..HEAD     # detect unauthorized local commits (whether pushed or not)
git status --short                      # detect uncommitted local changes (staged, unstaged, or untracked)
gh pr list --head $BRANCH --state open  # detect unauthorized PR openings
```

If any check surfaces activity not affirmatively enumerated in the report, pause the pipeline (do NOT launch reviewer), reset/inspect/reconcile, and log the discipline failure to `.armature/journal.md` as a process finding before continuing. Using `git log --oneline` (rather than `-1`) lets the orchestrator see the full scope of the violation at a glance before deciding how to reconcile. Every implementer brief MUST end with a verbatim boundary-recitation clause naming each forbidden operation: "Do NOT git commit. Do NOT git push. Do NOT gh pr create. Stop after verification and return your report. The orchestrator runs the reviewer + decides on commit." Redundant by intent — the implementer report's framing has been demonstrably insufficient against documented stacked-failure incidents.

**Related ADRs and invariants:** The counter-pattern is codified at the orchestrator-persona layer (boundary-verification step in the delegation protocol) rather than as an automated hook. A future ARMATURE.md amendment may formalize a `GATE-IMPLEMENTER-ACTION` invariant analogous to TIER0-001 to make the pre-reviewer check mechanically enforceable. Source incident: a delegation in a sibling Armature-governed project that combined an unauthorized commit, an unauthorized push, continuation past the documented stop point, and an unauthorized PR opening — all reported as "no commit, no push, ready for reviewer."

---

## Exemption / Carve-Out Drift

**Date:** 2026-05-29

**Originating incident or postmortem:** A documentation-only planner-bypass change to Armature's own governance, which required several sequential external-bot review rounds after the feature itself was sound. A single new exemption to the planner-trigger rule produced multiple follow-up fixes — each correcting a *different* place the rule was restated, or a *different* way the carve-out's scope was imprecise. Captured manually by the orchestrator as a recurring authoring failure mode (no hotfix involved).

**Observed failure pattern:** When a governed rule gains an exemption or carve-out, the canonical definition is updated but the rule's many *restatements* and the carve-out's *boundary conditions* are not kept in sync. Across that change this manifested as six distinct instances of one root cause: (1) the exemption was applied to the canonical definition but not to the procedural/action-oriented restatements, so an agent following the action bullets mechanically would still contradict the rule; (2) an overstated scope ("regardless of size") collided with a separate hard ceiling (`warn-loc`); (3) the exemption was appended after a multi-clause boolean (`complexity > 7 OR LOC > …`), so it could be read as suppressing a sibling clause, not just the intended one; (4) a *derived artifact* — a committed review-verdict file — described the carve-out incorrectly; (5) a tool-specific restatement (a Claude subagent `description`, read for agent-selection *before* the persona body) was left out of sync; and (6) a blanket inclusion glob (`*.txt`) silently re-included a path the rule intended to exclude (`.taskmaster/docs/prd.txt`), yielding a definition that contradicted its own stated intent. The common root: an exemption has a *surface area* — every restatement, every boolean scope, every overlap between allow/deny globs, every derived description — and updating only the canonical definition leaves the rest inconsistent. Each review round tends to surface one instance, so the cost is paid as a long series of one-off fixes rather than a single sweep.

**Recommended counter-pattern:** Treat adding an exemption to a governed rule as a *sweep*, not a point edit. Before declaring the change complete:

1. **Enumerate every restatement.** Grep for the rule's identifiers (threshold name, condition phrase) across spec procedural steps, persona mirrors, subagent-wiring `description` metadata, templates, and tool adapters. Apply the carve-out to each — or genericize the restatement to defer to the canonical definition (thin-adapter form) so it cannot drift again.
2. **Disambiguate boolean scope.** When the exemption modifies one branch of a multi-clause condition, parenthesize it explicitly — `A OR (B and not exempt)` — so it cannot be read as modifying sibling clauses.
3. **Check allow/deny overlap and state precedence.** If the rule pairs an inclusion set with an exclusion set using blanket globs (`*.txt`, `dir/**`), verify no excluded path is silently re-included, and state an explicit precedence rule (exclusions win).
4. **Reconcile derived artifacts.** Update — additively, for immutable artifacts such as accepted review verdicts and committed journal entries — any verdict, journal entry, or generated doc that describes the rule.
5. **Verify against intent, not just syntax.** Confirm the carve-out's effective set matches the stated intent for *every* member (e.g., does the canonical PRD path actually fall where the prose claims it does?).

A single reviewer or red-team pass framed as "where else is this rule described, and is the carve-out's scope precise and intent-matching there?" surfaces most instances at once, instead of one-per-review-round.

**Related ADRs and invariants:** Bears on SPEC-002 (internal section references in ARMATURE.md must resolve — no dead links) and ADAPTER-001 (tool adapters and wiring metadata must route to — not redefine or contradict — shared governance; a stale restatement in adapter or subagent `description` metadata is a drift vector). Carve-out drift also implicates a *semantic*-consistency concern that sits **beyond** SPEC-002's syntactic scope — a reference can resolve yet point at the wrong section (as a §8-vs-§7.6 reference slip during that change showed) — which no single invariant currently covers. No automated hook currently detects exemption drift; the counter-pattern is an authoring/review discipline. A future enhancement could add a post-stop check that flags a governed threshold/condition token appearing in multiple governed files whose surrounding text diverges. Source: a documentation-only planner-bypass change to Armature's governance.
