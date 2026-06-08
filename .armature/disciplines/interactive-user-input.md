---
id: interactive-user-input
severity: standard
composition-mode: advisory
---

# Interactive User Input

## When to apply

Apply to CLI tools, interactive agents, and any code path that prompts for user input.
Triggered by `discipline-tags: [interactive-user-input]` or content trigger (prompts,
`input()` calls, `questionary`, `click.prompt`).

## Standards

1. **Confirmation prompts must offer a default and label dangerous operations.**
   Always show the default in brackets and capitalize it to indicate it is the default:
   ```
   Delete 47 records from production? [y/N]: _    (default: N — safe)
   Proceed with dry-run? [Y/n]: _                 (default: Y — safe)
   ```
   Destructive operations must default to the safe choice (No/Cancel). Never default to
   a destructive action.

2. **Ask ONE clarifying question at a time.** When a request is ambiguous, identify the
   most important unknown and ask only that. A list of five clarifying questions is a
   friction event that causes users to abandon. After the answer, ask the next question
   if still needed.

3. **Non-interactive fallback via CLI flags or environment variables.** Every value that
   can be prompted must also be settable without prompting:
   - CLI flag: `--output-dir /path/to/dir`
   - Environment variable: `ARMATURE_OUTPUT_DIR=/path/to/dir`
   When both are set, the CLI flag takes precedence. Document the precedence order.

4. **Never block on input in automation contexts.** Detect non-interactive mode
   (`not sys.stdin.isatty()` in Python) and either use the configured default or exit
   with a clear error:
   ```python
   if not sys.stdin.isatty() and not output_dir:
       raise SystemExit("ERROR: --output-dir required in non-interactive mode")
   ```

5. **Ambiguity resolution preserves user intent.** When clarifying, restate what you
   understood: "You said 'production' — did you mean the `prod` environment at
   `api.example.com`?" This prevents fix-the-fix loops caused by wrong assumptions.

## Cross-references

- ARMATURE.md §3 (agent behavioral rules)
- `error-handling.md` (fail loudly for missing required non-interactive parameters)
- `clean-code.md` (naming: prompt variable names as nouns, not actions)
