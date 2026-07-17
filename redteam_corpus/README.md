# Reagent Bundled Red-Team Corpus

These templates exercise an LLM's defenses against well-known prompt-level attack classes. Each file is a single YAML case loaded by `reagent redteam`.

---

## Directory Structure (Tag-Driven Architecture)

The corpus is structured cleanly by **Technical Vector** (the mechanics of the attack), rather than by compliance framework. Compliance mappings are handled dynamically via YAML tags inside the payloads. Question Should we structure the directories based on taxonomy or threat framework?

```text
redteam_corpus/
├── prompt_injection/
├── sensitive_info_disclosure/
├── supply_chain_hijack/
├── insecure_output_handling/
├── excessive_agency/
├── system_prompt_extraction/
├── misinformation_elicitation/
└── unbounded_consumption/
```

---

## Coverage (v0.2)

| Taxonomy / Framework | Class / Threat Category | Templates |
|---|---|---|
| **OWASP LLM Top 10** | `LLM01:PromptInjection` | 7 |
| **OWASP LLM Top 10** | `LLM02:SensitiveInformationDisclosure` | 3 |
| **OWASP LLM Top 10** | `LLM03:Model/SystemSupplyChain` | 1 |
| **OWASP LLM Top 10** | `LLM05:ImproperOutputHandling` | 2 |
| **OWASP LLM Top 10** | `LLM06:ExcessiveAgency` | 3 |
| **OWASP LLM Top 10** | `LLM07:SystemPromptLeakage` | 5 |
| **OWASP LLM Top 10** | `LLM09:Misinformation` | 3 |
| **OWASP LLM Top 10** | `LLM10:UnboundedConsumption` | 1 |
| **Total** | | **24** |

*Note: `LLM04` (data poisoning) and `LLM08` (vector weakness) are system-level concerns that cannot be tested via single-turn prompts alone; they are tracked for future integration.*

---

## Polarity

Each case sets `attack_succeeded_means` to one of two values:

- **`model_failed`** (default for red-team) — assertions are designed to *detect attack success*. If they match, the attack worked and the model failed defense.
- **`model_passed`** — assertions verify *correct defense* (e.g., refusal). If they match, the model defended.

The runner reports a `defended` flag and an aggregate `defense_rate` over all OWASP-tagged cases, with a Wilson 95% CI.

---

## Adding a Template

1. Pick the OWASP cell. Use `reagent taxonomy` for the canonical class strings.
2. Create the `.yaml` file inside the matching **Technical Vector** subdirectory (e.g., `prompt_injection/`).
3. Set the compliance metadata (`owasp`, `atlas`, `nist_ai_rmf`) and the assertion(s) that detect attack success.
4. Add a citation in `references:` when the attack is documented in the literature.
5. Run `reagent suites validate redteam_corpus/` to lint the new suite.

See [`../THREAT_MODEL.md`](../THREAT_MODEL.md) for the responsible-handling checklist that all contributions must satisfy.
