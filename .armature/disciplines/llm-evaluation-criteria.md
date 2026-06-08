---
id: llm-evaluation-criteria
severity: high
composition-mode: advisory
---

# LLM Evaluation Criteria

## When to apply

Apply when authoring or reviewing LLM outputs, evaluator logic, or prompt pipelines.
Triggered by paths matching `**/eval*`, `**/prompt*`, `**/llm*`.

## Standards

1. **Factuality: claims must be verifiable from the input or known training knowledge.**
   An LLM output that asserts a fact not present in the provided context or demonstrably
   in training data is a factuality failure. Evaluators must flag unverifiable claims, not
   just implausible ones. Example failure: asserting a file path exists when no context
   confirms it.

2. **Groundedness: output references must resolve.** Any reference to a document, section,
   ADR, or external resource must exist and be accessible. In agentic systems, every
   "according to §3.4" citation must point to an actual section. Evaluators check citation
   resolution as a first-pass structural check.

3. **Calibration: expressed confidence must match actual reliability.** Do not emit
   high-confidence language ("definitely", "always", "guaranteed") for outputs generated
   by probabilistic inference. Use hedged phrasing ("typically", "in most cases") when the
   answer depends on context not visible in the prompt.

4. **Refusal appropriateness: refuse when genuinely unsure, and explain why.** A refusal
   must state what information would allow the task to proceed: "I cannot verify the schema
   without seeing the config file — please provide it." Blanket refusals without guidance
   are a quality failure equivalent to hallucination.

5. **Deterministic vs. sampled output handling.** Outputs that must be deterministic (IDs,
   file paths, schema field names) must not be generated via unconstrained sampling.
   Use structured output formats (JSON mode, regex constraints) or post-validate against
   a schema. Document which outputs are expected to vary across runs.

6. **Evaluate at the boundary, not the interior.** Evaluation criteria apply at the
   system boundary: the final output delivered to the caller. Intermediate chain-of-thought
   steps are not evaluated for factuality — only the final claim is.

## Cross-references

- ARMATURE.md §3 (agent behavioral rules)
- `guardrail-rules.md` (content policy and output filtering)
- `error-handling.md` (fail loudly on invariant violations in evaluator pipelines)
