# Security Policy

## Reporting a vulnerability in Reagent

If you believe you have found a security vulnerability in **Reagent itself**
(the toolkit code, not a model under test), please report it privately. Do
**not** open a public GitHub issue.

Until a long-term mailbox is established, please open a private GitHub
Security Advisory on the repository
(<https://github.com/reagent-eval/reagent/security/advisories/new>). Include:

- A description of the issue and its impact.
- Steps to reproduce, including any required configuration.
- The affected version (`reagent --version`).
- Whether you'd like to be credited.

We aim to acknowledge receipt within **3 business days** and provide an
initial assessment within **10 business days**.

## Reporting a vulnerability in a model provider

If, while authoring or running a red-team template, you discover a working
exploit against a major model provider (OpenAI, Anthropic, Google, Meta, etc.),
we strongly encourage **coordinated disclosure to the provider first**. Most
providers operate a security program:

| Provider  | Disclosure channel                                                     |
|-----------|------------------------------------------------------------------------|
| OpenAI    | <https://openai.com/security/disclosure/>                              |
| Anthropic | <https://www.anthropic.com/responsible-disclosure-policy>              |
| Google    | <https://bughunters.google.com/>                                       |
| Meta      | <https://www.facebook.com/whitehat>                                    |

Once the provider has addressed the issue (or a reasonable deadline has
elapsed), the template may be contributed back to Reagent's corpus.

## Scope

Reagent's threat model and what we consider in/out of scope is documented in
[THREAT_MODEL.md](THREAT_MODEL.md).

## Hall of fame

We will list (with consent) researchers who report valid vulnerabilities here
once the project has reached its first stable release.
