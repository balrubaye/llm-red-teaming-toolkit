# Reagent bundled red-team corpus

These templates exercise an LLM's defenses against well-known prompt-level
attack classes from the [OWASP LLM Top 10 (2025)](https://owasp.org/www-project-top-10-for-large-language-model-applications/).
Each file is a single YAML case loaded by `reagent redteam`.

## Coverage (v0.1)

| OWASP | Class                                | Templates |
|-------|--------------------------------------|-----------|
| LLM01 | Prompt Injection                     | 6         |
| LLM02 | Sensitive Information Disclosure     | 3         |
| LLM05 | Improper Output Handling             | 2         |
| LLM06 | Excessive Agency                     | 2         |
| LLM07 | System Prompt Leakage                | 4         |
| LLM09 | Misinformation                       | 3         |
| **Total** |                                  | **20**    |

`LLM03` (supply chain), `LLM04` (data poisoning), `LLM08` (vector weakness),
and `LLM10` (unbounded consumption) are system-level concerns that cannot be
tested via single-turn prompts alone; they are tracked for future iterations.

## Polarity

Each case sets `attack_succeeded_means` to one of two values:

- **`model_failed`** (default for red-team) — assertions are designed to *detect
  attack success*. If they match, the attack worked and the model failed defense.
- **`model_passed`** — assertions verify *correct defense* (e.g., refusal). If
  they match, the model defended.

The runner reports a `defended` flag and an aggregate `defense_rate` over all
OWASP-tagged cases, with a Wilson 95% CI.

## Adding a template

1. Pick the OWASP cell. Use `reagent taxonomy` for the canonical class strings.
2. Copy any existing file in the matching subdirectory.
3. Set `id`, `owasp`, `attack_class`, `severity`, and the assertion(s) that
   detect attack success (or defense, with `attack_succeeded_means: model_passed`).
4. Add a citation in `references:` when the attack is documented in the literature.
5. Run `reagent suites validate redteam_corpus/` to lint.

See [`../THREAT_MODEL.md`](../THREAT_MODEL.md) for the responsible-handling
checklist that all contributions must satisfy.
