---
id: sdlc-phases
severity: standard
composition-mode: advisory
---

# SDLC Phases

## When to apply

Apply during task planning and phase transitions. Triggered by `discipline-tags: [sdlc-phases]`
or by orchestrator pre-flight.

## Summary

Armature defines six SDLC phases. Full definitions are in ARMATURE.md §5.6.

| Phase | Purpose | Key gate |
|---|---|---|
| Discovery | Requirements, PRD | PRD must exist before Design |
| Design | Architecture, ADRs | Plan + ADRs before Implementation |
| Implementation | Code delivery | TDD-001, PHASE-001, TIER0-001 |
| Review | Reviewer verdict | PASS required before Release |
| Release | Ship + tag | Post-stop exit 0, all tests green |
| Hotfix | Emergency fix | Scoped to defect only, fast-path review |

## Phase-transition checklist

- **Discovery → Design:** PRD written and reviewed; scope approved.
- **Design → Implementation:** Implementation plan recorded in session state; ADRs filed for
  architectural decisions; LOC estimate logged; discipline trait set logged.
- **Implementation → Review:** All tests pass; DoD checklist satisfied (see `definition-of-done.md`);
  `post-stop.sh` exits 0.
- **Review → Release:** Reviewer PASS recorded in `.armature/reviews/`; no open FAIL findings.
- **Release → (next Discovery):** Journal entry appended; version tagged.
- **Any → Hotfix:** Defect scoped; original phase noted for return after hotfix.

## Cross-references

- ARMATURE.md §5.6 — full phase definitions and legal transitions
- ARMATURE.md §5.7 — gates registry
- Invariant: PHASE-001
- `definition-of-done.md` (DoD checklist for Implementation → Review gate)
