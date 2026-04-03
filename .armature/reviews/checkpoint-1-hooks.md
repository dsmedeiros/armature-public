# Review Verdict: checkpoint-1-hooks

## Scope Compliance
- Declared scope: `.armature` — "Core specification, persona definitions, invariant registry, templates, and validation hooks"
- Files modified:
  - `.armature/hooks/block-dangerous-commands.sh` (new)
  - `.armature/hooks/block-config-changes.sh` (new)
  - `.armature/hooks/mark-dirty.sh` (new)
  - `.armature/hooks/post-stop.sh` (modified)
  - `.armature/hooks/inject-context.sh` (new)
  - `.armature/hooks/reinject-context.sh` (new)
  - `.armature/hooks/check-required-reading.sh` (new)
- Out-of-scope modifications: none — all files are within `.armature/hooks/`

## Invariant Compliance
| Invariant | Status | Notes |
|---|---|---|
| SPEC-001 | N/A | No changes to ARMATURE.md section numbering |
| SPEC-002 | N/A | No changes to ARMATURE.md internal references |
| SCHEMA-001 | N/A | No changes to config.yaml |
| SCHEMA-002 | PASS | registry.yaml was not modified; post-stop.sh check 2 (YAML validation) is preserved intact |
| REF-001 | PASS | post-stop.sh check 1 (CLAUDE.md routing table reference validation) is preserved intact |
| REF-002 | PASS | post-stop.sh check 4 (ADR reference resolution) is preserved intact |

## Structural Consistency

Evaluated per the stated structural invariants for this checkpoint:

**Shebang (`#!/usr/bin/env bash`):** Present in all 7 files. PASS.

**`set -euo pipefail` or `set -uo pipefail`:** Present and correct in all 7 files.
- Guards (block-dangerous-commands.sh, block-config-changes.sh, check-required-reading.sh): use `set -euo pipefail`. PASS.
- Observers (mark-dirty.sh): uses `set -euo pipefail`. PASS.
- Validators (post-stop.sh): uses `set -euo pipefail`. PASS.
- Context injectors (inject-context.sh, reinject-context.sh): use `set -uo pipefail` (omitting `-e`). This is intentional — these hooks must not abort on partial failures (e.g. a missing file). PASS.

**`REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"`:** Present in all 7 files. PASS.

**Header comments (trigger event, stdin format, exit codes):** All 7 files have clear header comment blocks. All new guards document stdin format and exit semantics. PASS.

**No hardcoded absolute paths:** All file paths are constructed relative to `$REPO_ROOT` or `$ARMATURE_DIR`. PASS.

**Python fallback pattern consistent with post-stop.sh:** post-stop.sh establishes the pattern of resolving `PYTHON` once via `command -v python3` then `command -v python`. All new scripts that use python follow the same resolution order. One deviation: `mark-dirty.sh` passes `$INPUT` via shell string interpolation into a Python heredoc using triple-quote wrapping (`'''${INPUT}'''`) — this is fragile when the JSON input contains triple quotes or multi-line values with embedded quotes, but it is not a structural invariant violation. CONDITIONAL — see Required Changes.

## Exit Code Semantics

- **Guards exit 2 to block, exit 0 to allow:**
  - `block-dangerous-commands.sh`: exits 2 via `block()` helper on violations, exits 0 at end. PASS.
  - `block-config-changes.sh`: exits 2 via `block()` helper on violations, exits 0 at end. PASS.
  - `check-required-reading.sh`: exits 0 unconditionally (advisory-only). The header correctly documents this as advisory with future upgrade path. PASS.

- **Observers exit 0 always:**
  - `mark-dirty.sh`: all code paths exit 0. PASS.
  - `inject-context.sh`: exits 0 at end; all error paths emit comments and continue. PASS.
  - `reinject-context.sh`: exits 0 at end; all error paths fall through gracefully. PASS.

- **Validators exit 1 on failure:**
  - `post-stop.sh`: accumulates failures into `EXIT_CODE` and exits with that value. PASS.

## Post-stop.sh Integrity

The 4 original checks are verified to be unchanged:

1. Check 1 (lines 27–35): CLAUDE.md agents.md reference existence — identical to prior version. PASS.
2. Check 2 (lines 38–53): registry.yaml YAML validation — identical. PASS.
3. Check 3 (lines 56–61): uncommitted governance changes warning — identical. PASS.
4. Check 4 (lines 64–92): ADR reference resolution in agents.md frontmatter — identical. PASS.
5. Check 5 (lines 95–134): dirty-marker test runner — new, appended after check 4. PASS.

The dirty-marker cleanup logic in check 5 is sound: the marker is removed on test pass (line 122) but left in place on test failure (EXIT_CODE=1, marker retained). The SKIP path (no test runner detected) removes the marker to avoid indefinite accumulation — this is reasonable but marginally debatable since it means a repo without a detectable test runner silently clears the dirty flag. This is an advisory observation, not an invariant violation.

## Portability

- **No jq dependency:** Confirmed — all JSON parsing uses Python with sed/grep fallback. PASS.
- **No OS-specific paths:** All paths are constructed from `$REPO_ROOT`. The `check-required-reading.sh` Python code has an explicit Windows drive-letter guard (`except ValueError: return path`). PASS.
- **No tool-specific assumptions beyond bash and optionally python:** PASS.
- **`mark-dirty.sh` JSON parsing:** Uses triple-quote shell interpolation of `$INPUT` into Python source. This approach is fragile if `$INPUT` contains triple-quotes, newlines with embedded quotes, or backslash sequences — the Python source itself becomes syntactically invalid. The other scripts that parse JSON pass data via `printf '%s' "$VAR" | python3 -c` with `sys.stdin`, which is safe. This is the sole portability concern. CONDITIONAL — see Required Changes.

## Checkpoint: 1 of 1

## Verdict: CONDITIONAL

## Required Changes

1. **`mark-dirty.sh` — unsafe JSON interpolation into Python source (lines 23–39):**
   The pattern `json.loads('''${INPUT}'''.replace(...))` interpolates raw shell variable content directly into Python source code. If the JSON payload contains triple-quote sequences, backslash-newline sequences, or other characters that alter Python string literal parsing, the Python invocation will fail silently (due to `2>/dev/null || true`). All other scripts in this checkpoint use `printf '%s' "$VAR" | python3 -c "..." < /dev/stdin` or pass data via environment variables (as inject-context.sh does). The fix must use a safe data-passing mechanism — either pipe via stdin (`printf '%s' "$INPUT" | python3 -c "import json,sys; data=json.load(sys.stdin); ..."`) or pass via an environment variable (as inject-context.sh does with `_INJECT_STDIN_JSON`). The current implementation is a latent correctness defect that will silently produce an empty `FILE_PATH` on malformed input, which causes a false-safe exit 0 — acceptable for an observer, but the method should be consistent with the established pattern.

## Rollback Recommendation: NO
The defect in mark-dirty.sh is a silent fail-safe (the observer exits 0, no blocking occurs). The original 4 post-stop.sh checks are fully intact. Remediation of the JSON parsing method in mark-dirty.sh is sufficient; rollback is not warranted.
