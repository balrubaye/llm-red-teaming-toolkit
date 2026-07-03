# Reagent — Threat Model & Responsible Use

This document spells out what Reagent does and does not protect against, the
risks the bundled red-team corpus introduces, and the commitments contributors
make when adding new attack templates.

## What Reagent is

A toolkit for **authorized** security and quality testing of LLM systems. It
sends prompts (some adversarial) to a model you control or have permission to
test, evaluates the responses against assertions, and produces a scorecard.

Think of Reagent as **comparable to a load-testing or fuzzing tool**: the harm
profile is "this software can do things with the model API keys you give it."

## Interpreting Failures: Model-Level vs. System-Level Testing

When interpreting a Reagent scorecard, it is critical to distinguish between testing a raw foundational model and testing a complete AI application:

1. **Model-Level Testing (Raw APIs):** If you run Reagent against a raw model (e.g., `ollama:llama3.1:8b`) with a basic system prompt, **failures are expected**. Foundational models are trained to be highly compliant instruction-followers. If a user payload says "Ignore previous instructions", the model is technically doing its job by following the most recent instruction. A failure here does not mean the model itself is "insecure"; it simply proves that the model lacks the intrinsic ability to prioritize instructions on its own.
2. **System-Level Testing (AI Applications):** Reagent is most effective when configured to simulate your *complete application stack*. This means running tests using your application's actual, robust system prompts, retrieval context (RAG), and architecture. If Reagent reports a failure at the system level, it means an attacker successfully bypassed your application's defenses. This is a true vulnerability.

**To make Reagent tests effective for your app:** Do not just test the raw model. Copy your application's exact system instructions into the Reagent test cases, and use Reagent to prove that your *application architecture* (e.g., using XML tags, strict output parsing, or input guardrails) successfully prevents the model from being hijacked.

## What Reagent is *not*

- It is **not** a vulnerability scanner against arbitrary third-party services
  you do not own.
- It is **not** a mechanism to extract production secrets, training data, or
  user data from someone else's deployment.
- It does **not** carry novel zero-day exploits in its bundled corpus. The
  shipped templates illustrate **well-documented**, publicly known attack
  classes (most carry citations to peer-reviewed work or vendor advisories).

## Risks introduced by the bundled corpus

1. **Misuse against unauthorized targets.** A user could point Reagent at a
   model they do not have permission to test.
   - *Mitigation:* clear documentation; we do not gate the tool behind
     telemetry that we would have to operate.
2. **Provider Terms-of-Service exposure.** Adversarial payloads against cloud
   providers may violate their AUP. The user is responsible for compliance.
   - *Mitigation:* we recommend local Ollama for adversarial workloads where
     possible, and the v0.1 release supports only local Ollama for exactly
     this reason.
3. **Payload sensitivity in logs.** Some templates contain content (encoded
   payloads, role-play framings) that a user may not want in shared CI logs.
   - *Mitigation:* a `--safe-mode` redactor lands in v0.2.
4. **Severity creep.** Without curation, the corpus could accumulate trivial
   or actively harmful payloads.
   - *Mitigation:* contribution checklist below + severity-gated default run
     (we do not include `severity: critical` payloads in `reagent redteam`
     without an explicit flag — landing in v0.2 with the first `critical`
     additions).

## Contributor checklist for new red-team templates

Before submitting a PR that adds or modifies a template, confirm:

- [ ] **Authorized example.** The technique is documented in published research
      or a vendor advisory, OR is a clear illustration of a class (not a novel
      working exploit).
- [ ] **Taxonomy mapped.** Sets `owasp`, `attack_class`, and `severity`. Adds
      MITRE ATLAS IDs in `atlas:` when applicable.
- [ ] **Cited.** References at least one source in `references:` unless the
      attack is "obvious" (e.g., a direct "ignore previous instructions").
- [ ] **Specific.** Uses unique marker tokens (e.g., `PROJECT_SAFFRON_KESTREL`)
      so detection doesn't rely on fuzzy phrase matching.
- [ ] **No exfil.** The template does not attempt to leak actual production
      secrets, real PII, or sensitive third-party data. Use clearly synthetic
      data (e.g., `123-45-6789` for SSN).
- [ ] **No targeting.** The system prompt and input describe a generic
      AcmeCo-style company, not a real named vendor or product.
- [ ] **No novel zero-days.** If the template represents a working exploit
      against a current frontier model, follow [SECURITY.md](SECURITY.md) for
      coordinated disclosure *before* opening the PR.

PRs that violate any of these will be politely closed with a request to
revise. Reviewers will mention specific items.

## Out-of-scope harm we will refuse to ship

We will not accept templates whose primary purpose is to generate:

- CBRN (chemical, biological, radiological, nuclear) operational instructions.
- Operational malware (working keylogger source, functional ransomware, etc.).
- CSAM or sexual content involving minors, under any framing.
- Detailed targeting of identifiable real people for harassment.

The above are out of scope regardless of the OWASP cell they might map to.
Refusal-resistance testing for these categories is better done by AI safety
labs with the appropriate oversight, not by an OSS project's default corpus.

## Reporting concerns

If a shipped template strikes you as crossing one of the above lines, file an
issue tagged `corpus-review` or follow [SECURITY.md](SECURITY.md) for
sensitive reports. We take this seriously and will move quickly.
