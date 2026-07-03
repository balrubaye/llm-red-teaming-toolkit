# Reagent: Enterprise LLM Evaluation & Red-Teaming Toolkit

> **Open-source continuous compliance and red-teaming for LLM architectures.**
> Statistically rigorous regression diffs, a maintained multi-taxonomy attack corpus, actionable remediation, and live system-level testing — all in one binary.

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)
![Status: beta](https://img.shields.io/badge/status-beta-orange)

## Why Reagent?

Most AI evaluation tools test raw foundational models in isolation. But in the enterprise, a model is just one layer of a complex system surrounded by RAG pipelines, system prompts, guardrails, and tools.

Reagent is built for **System-Level Testing**. It doesn't just test models; it tests your actual application boundaries.

* **Multi-Layered Architecture:** Test raw models, simulate prompt templates, or blast attack payloads directly into live Python agents (LangChain, etc.) or HTTP APIs.
* **Continuous Compliance Engine:** Our attack corpus isn't just a list of prompts. Every test case maps to **OWASP Top 10 for LLMs**, and the architecture natively supports **NIST AI RMF**, **MITRE ATLAS**, and **METR / UK AISI**. A single test run can populate multiple compliance dashboards.
* **Actionable Remediation:** Reagent doesn't just fail a build. HTML reports include programmatically mapped "Remediation Guidance" (e.g., XML boundaries for prompt injections) so developers can fix issues immediately.
* **Statistically Rigorous CI:** No naive pass/fail counting. We use Wilson 95% confidence intervals and McNemar's test so you never chase ghosts or block a PR over statistical noise.

---

## 🚀 Quickstarts by Persona

Reagent is designed for Model Researchers, Application Developers, and AppSec Engineers. Pick the onboarding path that matches your role:

### 1. For Model Evaluators (Raw Model Testing)
*Goal: Benchmark a raw foundational model against the OWASP top 10.*

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Make sure you have a local Ollama model
ollama pull llama3.1:8b

# 3. Run the bundled red-team corpus
reagent redteam --model ollama:llama3.1:8b --owasp LLM01,LLM06
```

### 2. For Developers (Prompt Simulation)
*Goal: Test if your application's specific system prompt and input format defends against attacks better than the raw model.*

Create an `AppProfile.yaml` to simulate your application's architecture:
```yaml
name: "AcmeCorp E-Commerce Assistant"
system_prompt: |
  You are an e-commerce assistant for AcmeCorp. Only answer questions about AcmeCorp products.
input_template: |
  <user_query>
  {{ payload }}
  </user_query>
```
Run Reagent to automatically wrap all attack payloads in your application's tags:
```bash
reagent redteam --model ollama:llama3.1:8b --app-profile AppProfile.yaml
```

### 3. For AppSec & Pentesters (Live System Testing)
*Goal: Test an end-to-end proprietary backend (e.g., a LangChain agent, RAG pipeline, or custom HTTP API).*

Write a simple Python adapter script (`my_agent.py`):
```python
async def complete(prompt: str) -> str:
    # Blast the attack payload through your actual application logic/API!
    response = await my_custom_backend.send_query(prompt)
    return response.text
```
Run Reagent using the `exec:` Target Adapter. Reagent will evaluate the final output of your pipeline against the attack assertions:
```bash
reagent redteam --model exec:my_agent.py
```

---

## 🧩 Advanced Features

### Custom Payload Mixing (`--extra-cases`)
Don't want to duplicate the core Reagent corpus? You can maintain your own private, domain-specific attack payloads (e.g., trying to grant unauthorized refunds on your specific product).
```bash
reagent redteam --model ollama:llama3.1:8b --extra-cases ./my_private_payloads/
```
Reagent will dynamically merge your custom cases with the core corpus and generate a unified scorecard.

### Actionable Reporting
Outputs go to `./reports/`:
* `scorecard-01HXXX.json`: Canonical artifact (machine-readable, CI-ready).
* `scorecard-01HXXX.md`: Markdown summary for automated PR comments.
* `scorecard-01HXXX.html`: A single-file, offline-friendly browser report containing full input/output diffs, OWASP breakdowns, and **Remediation Tips** tailored to the failed vulnerability classes.

---

## 🗺️ Roadmap & Multi-Taxonomy Vision

Reagent is evolving from a local testing tool to an enterprise compliance suite.

| Feature Area | Current Status (Beta) | Roadmap (v1.0) |
|---|---|---|
| **Taxonomies** | OWASP Top 10 | MITRE ATLAS, NIST AI RMF, METR/UK AISI mappings. |
| **Model Adapters** | Ollama, OpenAI, Anthropic, Gemini | Bedrock, Mistral, xAI Grok. |
| **Target Adapters** | `exec:` (Python Scripts) | `http:` (Raw API testing). |
| **Statistical CI** | JSON Scorecards & Actionable HTML | `reagent diff` with Wilson CI & SARIF output. |
| **Corpus Upgrades**| Instruction Override, Tool Confusion | Multi-turn dialogues, payload obfuscation, RAG context stuffing. |

## Responsible Use

Reagent is a tool for *authorized* security testing of LLM systems you own or have permission to test. See [THREAT_MODEL.md](THREAT_MODEL.md) for the responsible-handling posture of the bundled red-team corpus.

## Development

```bash
pip install -e ".[dev]"
pytest -q              # tests
ruff check src tests   # lint
pyright src            # types
```

## License

Apache-2.0. See [LICENSE](LICENSE).
