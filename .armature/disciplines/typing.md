---
id: typing
severity: standard
composition-mode: advisory
---

# Typing

## When to apply

Apply to Python files (`**/*.py`). Triggered when language is Python.

## Standards

1. **Annotate all public API signatures.** Every function or method that is part of a module's
   public interface (no leading underscore) must have parameter types and a return type.
   Private helpers should be annotated where the type is non-obvious.

2. **Avoid `Any`.** `Any` disables type checking for that value. Use `object` for truly unknown
   types, or a specific `Union` / `TypeVar`. If a third-party library forces `Any`, isolate it
   in a typed wrapper and add `# type: ignore[arg-type]` with a comment explaining why.

3. **Parameterize generic collections.** Never write `list`, `dict`, `tuple`, or `set` without
   type arguments in annotations:
   ```python
   def merge(sources: list[dict[str, str]]) -> dict[str, str]: ...  # good
   def merge(sources: list) -> dict: ...                            # bad
   ```

4. **Declare return types on all functions, including `None`.** A missing return annotation
   signals intent is unclear. Explicit `-> None` is required for procedures. `-> NoReturn`
   for functions that always raise.

5. **Type the empty-collection default correctly.** Default arguments that are collections
   must use `field(default_factory=list)` (dataclass) or a factory pattern — never a mutable
   default. Annotation: `items: list[str] = field(default_factory=list)`, not `items: list = []`.

6. **Use `TypeAlias` for complex repeated types.** If a type expression appears more than
   twice, extract it: `ConfigMap: TypeAlias = dict[str, list[str]]`. This applies the
   rule-of-three from `abstraction-rules.md`.

## Cross-references

- ARMATURE.md §3 (behavioral rules)
- `abstraction-rules.md` (rule of three for type aliases)
- `definition-of-done.md` (no new `Any` introductions at DoD)
