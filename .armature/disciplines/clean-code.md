---
id: clean-code
severity: standard
composition-mode: advisory
---

# Clean Code

## When to apply

Apply to every source file change. This discipline is always-on (path trigger `**/*`).

## Standards

1. **Name functions as verbs, classes as nouns.** A function name must describe an action
   (`parse_config`, `validate_schema`). A class name must describe an entity (`ConfigLoader`,
   `SchemaValidator`). Single-letter names are banned outside loop indices and lambda arguments.

2. **No abbreviations unless domain-standard.** Use `repository` not `repo`, `configuration`
   not `cfg`, `response` not `resp`. Domain-standard exceptions: `url`, `id`, `http`, `api`.
   Example — bad: `def calc_cfg_diff(cfg1, cfg2)` / good: `def calculate_config_diff(base, override)`.

3. **Function size: ≤30 LOC target, ≤50 LOC hard ceiling.** Count non-blank, non-comment lines.
   If a function exceeds 30 LOC, extract a named helper. If it exceeds 50 LOC, it is a required
   refactor — do not merge without splitting.

4. **One responsibility per function.** A function does one thing at one level of abstraction.
   Mixing IO with computation is a violation. Test: can you describe the function in one clause
   without using "and"? If not, split it.

5. **Magic numbers become named constants.** Every numeric or string literal that encodes a
   business or protocol rule must be extracted:
   ```python
   MAX_RETRY_ATTEMPTS = 3          # good
   CONTENT_TYPE_JSON = "application/json"
   if attempts >= MAX_RETRY_ATTEMPTS: ...  # readable
   if attempts >= 3: ...           # bad — silent assumption
   ```

6. **No commented-out code in commits.** Dead code must be deleted, not commented. Version
   control preserves history. A comment like `# old approach:` followed by code is a merge blocker.

## Cross-references

- ARMATURE.md §3 (agent behavioral rules)
- DISCIPLINE-001 (discipline corpus invariant)
