---
id: error-handling
severity: high
composition-mode: advisory
---

# Error Handling

## When to apply

Apply to every source file change. Always-on (path trigger `**/*`).

## Standards

1. **No bare exception catches.** In Python, `except:` or `except Exception:` without a
   re-raise is banned unless followed by structured logging and a deliberate fallback.
   Preferred pattern:
   ```python
   except ValueError as exc:
       raise ConfigError(f"Invalid field 'timeout': {exc}") from exc
   ```

2. **Fail loudly for invariant violations.** When a pre-condition that must always hold is
   broken (e.g., a required config key is missing, a type contract is violated), raise
   immediately with a specific exception type. Do not return `None` and let the caller figure
   it out — that creates silent corruption.

3. **Fail safely for user-facing errors.** Errors shown to end users must use structured
   error types that carry a `user_message` (safe, no internals) and an optional `detail`
   (for logs only). Never propagate an internal traceback to a UI boundary.

4. **Errors carry actionable messages.** The message must answer: what failed, why, and
   what the caller can do. Bad: `raise ValueError("failed")`. Good:
   `raise ValueError(f"Timeout must be a positive integer; got {value!r}")`.

5. **Separate validation errors from runtime errors.** Use distinct exception hierarchies:
   `ValidationError` (bad input, caller's fault) vs `RuntimeError` / `ServiceError`
   (system fault, not the caller's fault). Callers catch these separately to give
   appropriate user feedback.

6. **Exception chains preserve context.** Always use `raise NewError(...) from original_exc`
   when wrapping. Suppress only when the original error is truly irrelevant and you document why:
   `raise UserError("Not found") from None  # suppress: internal path not safe to expose`.

## Cross-references

- ARMATURE.md §3 (behavioral rules)
- `clean-code.md` (naming conventions for exception classes)
