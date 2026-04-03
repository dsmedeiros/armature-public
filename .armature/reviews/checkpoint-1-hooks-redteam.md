# Red Team Verdict: checkpoint-1-hooks

## Summary

Seven hook scripts were subjected to adversarial probing for bypass vectors, silent failure modes, breaking changes, and edge cases. No code execution vulnerabilities were confirmed, but several HIGH-severity bypass gaps exist in `block-dangerous-commands.sh` that allow dangerous commands to pass uncaught, plus two code injection surfaces in `mark-dirty.sh` and `check-required-reading.sh` that degrade to silent failure rather than exploitation. The `--force-with-lease` false positive is the most likely real-world annoyance. Overall the hooks are structurally sound but the command blocklist has meaningful gaps.

## Critical Findings

### FINDING-01: `rm -rf src node_modules` bypasses guard (HIGH)

- **File:** `.armature/hooks/block-dangerous-commands.sh`, line 79 (`is_safe_rm_target`)
- **Bug:** `is_safe_rm_target` extracts only the *last* whitespace-delimited token (`${cmd##* }`) as the target. When `rm -rf` is invoked with multiple arguments, only the final argument is checked against the safe list.
- **Trigger:** `rm -rf src node_modules` -- the function sees `node_modules` (safe), so the entire command is allowed, but `src` is also being deleted.
- **Impact:** An agent can destroy arbitrary directories by appending a safe target name.
- **Verified:** Yes. The command exits 0 when it should exit 2.
- **Severity:** HIGH

### FINDING-02: `git add -u` and `git add --update` not blocked (HIGH)

- **File:** `.armature/hooks/block-dangerous-commands.sh`, lines 153-157
- **Bug:** The git-add rule catches `-A`, `--all`, and bare `.` but does not catch `-u` or `--update`. Both `git add -u` and `git add --update` stage all tracked modified files indiscriminately, which carries the same risk as `git add -A` (committing unintended changes to tracked files such as `.env` if it was previously tracked).
- **Trigger:** `git add -u .` or `git add -u` or `git add --update`
- **Impact:** The governance intent (stage files explicitly by name) is fully defeatable.
- **Verified:** Yes. All three variants exit 0.
- **Severity:** HIGH

### FINDING-03: `--force-with-lease` falsely blocked (HIGH)

- **File:** `.armature/hooks/block-dangerous-commands.sh`, line 110
- **Bug:** The regex `git.*push.*--force` matches `--force-with-lease` because `--force-with-lease` contains the substring `--force`. `--force-with-lease` is a safe push mode specifically designed to prevent overwriting others' work -- it is not equivalent to `--force`.
- **Trigger:** `git push --force-with-lease origin feature`
- **Impact:** Blocks a legitimate and safe workflow. Agents that should use `--force-with-lease` for rebased feature branches are prevented from doing so.
- **Verified:** Yes. The command exits 2 with "git push --force" message.
- **Severity:** HIGH

### FINDING-04: `--no-verify` false positives on unrelated flags (MEDIUM)

- **File:** `.armature/hooks/block-dangerous-commands.sh`, line 146
- **Bug:** The regex `$COMMAND =~ --no-verify` is a substring match with no word boundary. It matches `--no-verify-ssl`, `--no-verify-signatures`, or any flag/string that contains the substring `--no-verify`.
- **Trigger:** `curl --no-verify-ssl https://example.com` or `echo "the --no-verify flag"` in a quoted string.
- **Impact:** False blocks on legitimate commands. The `echo` case is particularly annoying -- an agent explaining governance in a log message would be blocked.
- **Verified:** Yes. Both `--no-verify-ssl` and an echo containing the string are blocked.
- **Severity:** MEDIUM

### FINDING-05: `git checkout -- .`, `git restore .`, `git branch -D` not caught (MEDIUM)

- **File:** `.armature/hooks/block-dangerous-commands.sh`
- **Bug:** The hook has no rules for `git checkout -- .` (discards all unstaged changes), `git restore .` (same effect), or `git branch -D` (force-deletes a branch, potentially losing unmerged commits). These are destructive git commands explicitly called out in the Claude Code system prompt as dangerous.
- **Trigger:** Any of these three commands.
- **Impact:** An agent can discard all working tree changes or delete branches containing unmerged work.
- **Verified:** Yes. All three exit 0.
- **Severity:** MEDIUM

## Silent Failure Modes

### FAILURE-01: mark-dirty.sh Python code injection degrades to silent skip (MEDIUM)

- **File:** `.armature/hooks/mark-dirty.sh`, lines 23-39
- **Bug:** Raw `${INPUT}` is interpolated into Python triple-quoted string literals. If the JSON payload contains `'''`, the Python source becomes syntactically invalid. The `2>/dev/null || true` wrapper swallows the SyntaxError, FILE_PATH becomes empty, and the hook exits 0 without marking dirty.
- **Impact:** An Edit/Write event on an application file would silently fail to set the dirty marker, causing post-stop.sh check 5 to skip test execution. Not exploitable for code execution (confirmed via testing -- SyntaxError, not eval).
- **Note:** The standard reviewer already flagged this. The red team confirms it is not a code execution vector but is a correctness defect.
- **Severity:** MEDIUM

### FAILURE-02: check-required-reading.sh has same interpolation pattern (MEDIUM)

- **File:** `.armature/hooks/check-required-reading.sh`, line 47
- **Bug:** `payload_raw = '''${PAYLOAD}'''` has the same triple-quote breakout surface as mark-dirty.sh. Since this hook is advisory-only (always exits 0), the impact is limited to the advisory message being silently dropped.
- **Severity:** MEDIUM (lower than mark-dirty because no behavioral consequence)

### FAILURE-03: Unquoted heredocs in inject-context.sh and reinject-context.sh allow shell expansion (LOW)

- **File:** `.armature/hooks/inject-context.sh`, lines 38, 81; `.armature/hooks/reinject-context.sh`, line 55
- **Bug:** These use `<<PYEOF` (unquoted) for Python heredocs, meaning `${REGISTRY}`, `${STATE}`, `${JOURNAL}` are shell-expanded into the Python source. If any of these paths contain backticks, `$()`, or special characters, the shell will expand them before Python sees the code.
- **Mitigant:** These variables are derived from `git rev-parse --show-toplevel`, which the attacker would need to control (requires a maliciously named repo root). The Section 3 block in inject-context.sh correctly uses `<<'PYEOF'` (quoted) and environment variables, showing awareness of this issue. The inconsistency suggests the fix was applied only to the section handling user-controlled input.
- **Severity:** LOW (requires attacker-controlled filesystem paths)

### FAILURE-04: Empty or malformed stdin causes silent allow in block-config-changes.sh (LOW)

- **File:** `.armature/hooks/block-config-changes.sh`, lines 67-69
- **Bug:** When the source field cannot be parsed (empty stdin, malformed JSON), the hook warns to stderr but exits 0 (allow). This is a fail-open design. A malformed ConfigChange event would bypass the guard entirely.
- **Mitigant:** ConfigChange events are generated by the Claude Code runtime, not by the agent, so the agent cannot craft a malformed payload. The fail-open behavior is documented ("fail open to avoid false positives").
- **Severity:** LOW

## Breaking Changes

No breaking changes to post-stop.sh. Checks 1-4 are preserved verbatim. Check 5 is purely additive and only executes when the `.code-dirty` marker exists (which requires mark-dirty.sh to be wired). The `EXIT_CODE` accumulation pattern is correctly maintained. `set -e` does not cause premature exit because all Python invocations and test commands are guarded with `|| EXIT_CODE=1` or subshells.

## Edge Cases

### EDGE-01: `rm --recursive --force /` is caught but by accident

The regex on line 101 looks for flag clusters like `-rf`, `-fr`, `-r -f`. But `rm --recursive --force /` is caught because the regex also matches the `-f` inside `--force`. This works but is fragile -- if the regex is ever tightened to require short flags only, the long-form flags would slip through. There is no explicit rule for `--recursive` or `--force` as long-form flags.

### EDGE-02: mark-dirty.sh correctly handles `docs-extra/` vs `docs/`

Confirmed via testing. The case statement uses `docs/*` which requires the prefix to be exactly `docs/`, so `docs-extra/something.py` correctly triggers the dirty marker.

### EDGE-03: check-required-reading.sh handles repo root correctly

The `find_agents_md` function walks up from the target file's parent directory and stops at REPO_ROOT. Files at repo root will have `start_dir == REPO_ROOT`, and the function checks REPO_ROOT itself before breaking. Confirmed correct.

### EDGE-04: post-stop.sh check 5 npm test detection uses $PYTHON even when TEST_RUNNER is npm

Line 108 uses `$PYTHON -c "import json; ..."` to check if `package.json` has a `test` script. If python is unavailable (`$PYTHON` is empty), this silently fails and falls through to the Makefile check. This is acceptable degradation, but the detection order comment ("pytest, npm test, make test") is misleading when python is unavailable -- npm test detection is effectively skipped.

## Verdict: FAIL

## Blocking Issues

1. **FINDING-01 (HIGH):** `rm -rf` with multiple arguments only checks the last argument, allowing arbitrary directory deletion by appending a safe target name. The `is_safe_rm_target` function must validate all non-flag arguments, or alternatively reject any `rm -rf` with multiple non-flag arguments.

2. **FINDING-02 (HIGH):** `git add -u` and `git add --update` are not blocked despite carrying the same risk as `git add -A`. The rule on lines 153-157 must be extended to cover these variants.

3. **FINDING-03 (HIGH):** `--force-with-lease` is falsely blocked. The `--force` regex must use a word boundary or negative lookahead to exclude `--force-with-lease` and `--force-if-includes`. Suggested pattern concept: match `--force` only when followed by whitespace or end-of-string, not by `-`.

4. **FINDING-04 (MEDIUM, blocking due to usability impact):** The `--no-verify` substring match produces false positives on `--no-verify-ssl` and on the literal string appearing in echo/log output. The match should require a word boundary (whitespace or end-of-string after `--no-verify`).
