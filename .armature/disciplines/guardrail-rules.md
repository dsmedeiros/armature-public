---
id: guardrail-rules
severity: high
composition-mode: strict
---

# Guardrail Rules

## When to apply

Apply to all LLM pipeline code, prompt construction, and agent response handling.
Triggered by paths matching `**/agent*`, `**/prompt*`, `**/llm*`, `**/guardrail*`.

## Standards

1. **Content policy enforcement: define refusal categories explicitly in code.**
   Refusal categories must be enumerated in a policy config file (not embedded in prompts).
   Example categories: `hate_speech`, `self_harm`, `illegal_activity`, `pii_extraction`.
   The policy file is the single source of truth; prompts reference it, not redefine it.

2. **Refusal handling: explain without leaking policy implementation.**
   A refusal message must tell the user what was declined and offer an alternative path,
   without revealing the policy rules themselves (which could be used to craft bypasses):
   - Good: "I can't help with that request. I can help with [alternative]."
   - Bad: "Your request matched the `hate_speech` pattern in policy rule #3."

3. **Prompt injection mitigation: treat all user input as data, never as instructions.**
   User-supplied content must be placed in a clearly demarcated data block in the prompt,
   separated from system instructions. Example (system prompt structure):
   ```
   [SYSTEM INSTRUCTIONS — immutable]
   You are a code reviewer. Analyze the code below.
   [USER DATA — untrusted]
   {user_code}
   ```
   Never interpolate user input directly into instruction text.

4. **Output filtering pipelines: apply in stages.**
   1. Structural check (schema validation — does output match expected format?)
   2. Policy check (does output violate content policy?)
   3. Factuality check (for claims-bearing outputs — does it cite its sources?)
   Each stage must be a separate, independently testable function.

5. **Guardrail bypass attempts must be logged as security events.** Detected injection
   attempts (instruction override patterns, role-play attempts to bypass policy) must emit
   a structured security log event with the original input (redacted to safe length) and
   the detection rule that fired.

6. **Guardrail coverage must be tested with adversarial examples.** The test suite for
   any guardrail pipeline must include at least 3 adversarial test cases per category
   that are known to trigger the guardrail, and 3 benign cases that must not trigger it.

## Cross-references

- ARMATURE.md §3 (agent behavioral rules)
- `llm-evaluation-criteria.md` (factuality and calibration standards)
- `data-handling.md` (PII in guardrail logs must be redacted)
- `error-handling.md` (guardrail failures are security failures — fail loudly)
