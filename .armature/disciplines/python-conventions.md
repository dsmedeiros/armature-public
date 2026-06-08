---
id: python-conventions
severity: standard
composition-mode: advisory
---

# Python Conventions

## When to apply

Apply to Python files (`**/*.py`). Triggered when language is Python.

## Standards

1. **PEP 8 essentials — non-negotiable.** 4-space indent (no tabs), snake_case for functions
   and variables, PascalCase for classes, UPPER_SNAKE_CASE for module-level constants,
   max 100-character line length (not the PEP 8 default of 79 — project override).

2. **Import ordering: stdlib → third-party → local, alphabetized within each group.**
   Separate groups with one blank line. Example:
   ```python
   import os
   import sys

   import yaml

   from armature.config import load
   from armature.hooks import validate
   ```
   Use `isort` configuration to enforce automatically.

3. **Docstring format: Google style, consistently applied.** Every public function, class,
   and module must have a docstring. Format:
   ```python
   def parse_config(path: Path) -> dict[str, object]:
       """Parse a YAML config file and return a normalized mapping.

       Args:
           path: Absolute path to the config file.

       Returns:
           Normalized key-value mapping.

       Raises:
           ConfigError: If the file is missing or malformed.
       """
   ```

4. **Module entry points use `if __name__ == "__main__":`.** Script logic executed at import
   is a test-breaking anti-pattern. All top-level execution must be guarded.

5. **No wildcard imports (`from x import *`).** Wildcard imports pollute the namespace
   and break static analysis. Import explicitly or use `__all__` in the source module.

## Cross-references

- ARMATURE.md §3 (behavioral rules)
- `typing.md` (annotation conventions for Python)
- `clean-code.md` (naming conventions)
