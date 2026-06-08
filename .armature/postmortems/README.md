# Armature Postmortems

This directory holds governance artifacts produced by the `/postmortem` command. Each file documents a completed Hotfix bypass incident per the audit protocol in ARMATURE.md §7.9, tracing the bypass-intent declaration through the fix, the reviewer verdict, and the root-cause analysis.

## Naming Convention

Files follow the pattern `YYYY-MM-DD-<slug>.md` where the date is the UTC date the postmortem was scaffolded and the slug is derived from the `/postmortem` command argument (lowercased, whitespace replaced by dashes, non-alphanumeric characters stripped). When no argument is provided, the slug is `unnamed`. Example: `2026-03-15-auth-token-leak.md`.

## Redaction

Postmortems are committed to the repository and become part of the permanent governance audit trail. Authors must redact sensitive details before committing. Slots marked `<!-- REDACT if sensitive -->` in the `/postmortem` template may be replaced with `[REDACTED — see secure incident log]`. The obligation is on the author: review every slot before committing and apply this substitution wherever the content would expose credentials, personal data, customer information, or internal system details that should not be in version control.

## Append-Only Convention

Once committed, a postmortem file is never edited. This mirrors the append-only convention of the governance journal (ARMATURE.md §7.10) and preserves an unambiguous audit trail. If a committed postmortem contains an error or requires a correction, author a new dated file that references the original and declares the correction. The original file remains intact.

## Cross-References

- `.armature/antipatterns.md` — distilled counter-pattern entries extracted from postmortems; one entry per incident, appended by the `/postmortem` command.
- `.armature/journal.md` — governance journal that records bypass-intent declarations and the closure entries that reference the postmortem file path.
