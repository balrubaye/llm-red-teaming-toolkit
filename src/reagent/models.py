"""Core Pydantic models for Reagent.

All data structures that cross module boundaries live here. Keep this file free of
runtime side effects so it can be imported cheaply.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_run_id() -> str:
    return uuid4().hex


# ---------------------------------------------------------------------------
# Chat layer — provider-agnostic request/response shape
# ---------------------------------------------------------------------------


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    content: str


class ChatParams(BaseModel):
    """Provider-agnostic generation parameters.

    Adapters translate these to their native fields. Adapters MUST document any
    parameter they silently ignore so reproducibility is auditable.
    """

    model_config = ConfigDict(extra="forbid")

    temperature: float = 0.0
    max_tokens: int = 1024
    top_p: float | None = None
    seed: int | None = None
    stop: list[str] | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str  # e.g. "ollama:llama3.1:8b"
    messages: tuple[Message, ...]
    params: ChatParams = Field(default_factory=ChatParams)

    def cache_key(self) -> str:
        """Stable content-addressable hash for cache lookup.

        Includes everything that can affect the response. Order matters; we hash
        the canonical JSON form.
        """
        payload = self.model_dump_json(exclude_none=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ChatUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ChatResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    model: str
    usage: ChatUsage = Field(default_factory=ChatUsage)
    latency_ms: int = 0
    cost_usd: Decimal = Decimal("0")
    finish_reason: str | None = None
    cached: bool = False
    raw: dict[str, Any] | None = None  # provider-specific payload, opaque


# ---------------------------------------------------------------------------
# Assertions — discriminated union by `kind`
# ---------------------------------------------------------------------------


class AssertionBase(BaseModel):
    """Base for all assertion definitions. Concrete classes set ``kind`` as a
    ``Literal[...]`` so the discriminated union can dispatch.
    """

    model_config = ConfigDict(extra="forbid")

    # Optional human-readable label, useful in reports.
    label: str | None = None


class RegexAssertionDef(AssertionBase):
    kind: Literal["regex"] = "regex"
    pattern: str
    must_match: bool = True
    flags: str = ""  # subset of "imsx"


class ContainsAnyAssertionDef(AssertionBase):
    kind: Literal["contains_any"] = "contains_any"
    values: list[str]
    case_sensitive: bool = False


class NotContainsAssertionDef(AssertionBase):
    kind: Literal["not_contains"] = "not_contains"
    values: list[str]
    case_sensitive: bool = False


class RefusalAssertionDef(AssertionBase):
    """Detects an explicit refusal in the output.

    `expected`: when True (default), the case PASSES if the model refused.
                when False, the case PASSES if the model did NOT refuse.
    """

    kind: Literal["refusal"] = "refusal"
    expected: bool = True


class LLMJudgeAssertionDef(AssertionBase):
    kind: Literal["llm_judge"] = "llm_judge"
    rubric: str  # full rubric text or "@path/to/rubric.md"
    judge_model: str  # e.g. "ollama:llama3.1:70b"
    score_min: float = 4.0  # default rubric scale is 1-5
    score_max: float = 5.0


AssertionDef = Annotated[
    RegexAssertionDef
    | ContainsAnyAssertionDef
    | NotContainsAssertionDef
    | RefusalAssertionDef
    | LLMJudgeAssertionDef,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Red-team taxonomy
# ---------------------------------------------------------------------------


class OwaspLLM(str, Enum):
    """OWASP LLM Top 10 (2025 ed.) classes that are prompt-testable.

    LLM04 (data poisoning) and LLM08 (vector weakness) are system-level
    and not directly testable via single-turn prompting, so they are omitted.
    """

    LLM01 = "LLM01:PromptInjection"
    LLM02 = "LLM02:SensitiveInformationDisclosure"
    LLM03 = "LLM03:Model/SystemSupplyChain"
    LLM05 = "LLM05:ImproperOutputHandling"
    LLM06 = "LLM06:ExcessiveAgency"
    LLM07 = "LLM07:SystemPromptLeakage"
    LLM09 = "LLM09:Misinformation"
    LLM10 = "LLM10:UnboundedConsumption"

    @property
    def remediation(self) -> str:
        """Actionable remediation guidance for the vulnerability."""
        advice = {
            self.LLM01: "Use robust system prompts, clearly separate instructions from user data (e.g. XML tags), or use a secondary LLM as an input guardrail.",
            self.LLM02: "Implement robust data redaction/scrubbing for PII/credentials before sending to the model, and restrict training data.",
            self.LLM03: "Validate and sanitize data retrieved from third-party sources or external dependencies before passing it to the model.",
            self.LLM05: "Treat LLM output as untrusted. Sanitize, encode, and validate all outputs before passing them to downstream systems or users (e.g., HTML escaping, parameterized SQL).",
            self.LLM06: "Enforce principle of least privilege for LLM tool access. Require human-in-the-loop validation for high-stakes actions.",
            self.LLM07: "System prompts should be considered public. Do not store secrets or proprietary logic in them. Filter outputs for system prompt markers.",
            self.LLM09: "Ground the model with factual context (RAG), adjust temperature for lower variance, and cite sources.",
            self.LLM10: "Enforce strict token generation limits, implement request timeouts, and monitor anomalous usage spikes.",
        }
        return advice.get(self, "No specific remediation advice available.")


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AttackClass(str, Enum):
    """Reagent's finer-grained attack class. Multiple per OWASP cell are expected."""

    INSTRUCTION_OVERRIDE = "instruction-override"
    ROLE_PLAY = "role-play"
    PAYLOAD_ENCODING = "payload-encoding"
    CONTEXT_STUFFING = "context-stuffing"
    SYSTEM_PROMPT_EXTRACTION = "system-prompt-extraction"
    POLICY_PUPPETRY = "policy-puppetry"
    DATA_EXFILTRATION = "data-exfiltration"
    OUTPUT_INJECTION = "output-injection"
    TOOL_CONFUSION = "tool-confusion"
    MISINFORMATION_ELICITATION = "misinformation-elicitation"
    SUPPLY_CHAIN_HIJACK = "supply-chain-hijack"
    DENIAL_OF_SERVICE = "denial-of-service"


class AttackOutcome(str, Enum):
    """How to interpret a passing assertion.

    In red-team suites the polarity is inverted: when assertions match, the
    attack succeeded and the model failed defense. We track this explicitly so
    the scorecard reports defense_rate (1 - attack_success_rate).
    """

    MODEL_FAILED = "model_failed"  # default for red-team
    MODEL_PASSED = "model_passed"  # default for quality eval


# ---------------------------------------------------------------------------
# Cases and suites
# ---------------------------------------------------------------------------


class JudgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    rubric: str | None = None
    score_min: float = 4.0
    score_max: float = 5.0
    temperature: float | None = 0.0


class SuiteDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = 0.0
    max_tokens: int = 1024
    seed: int | None = None
    system: str | None = None
    judge: JudgeConfig | None = None


class Case(BaseModel):
    """A single test case — generic across quality eval and red-team."""

    # ``populate_by_name`` lets callers construct from either the field name
    # (``assertions=``) or the YAML alias (``assert``), since `assert` is a
    # Python keyword and can't be a kwarg.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    input: str | None = None
    messages: list[Message] | None = None
    system: str | None = None
    assertions: list[AssertionDef] = Field(default_factory=list, alias="assert")
    tags: list[str] = Field(default_factory=list)

    # Red-team metadata. Optional on generic cases.
    owasp: OwaspLLM | None = None
    attack_class: AttackClass | None = None
    severity: Severity | None = None
    atlas: list[str] = Field(default_factory=list)  # e.g. ["AML.T0051.001"]
    nist_ai_rmf: list[str] = Field(default_factory=list) # e.g. ["MEASURE-2.4"]
    references: list[str] = Field(default_factory=list)
    attack_succeeded_means: AttackOutcome = AttackOutcome.MODEL_PASSED

    # Per-case overrides
    temperature: float | None = None
    max_tokens: int | None = None
    seed: int | None = None

    @model_validator(mode="after")
    def _require_input_or_messages(self) -> Self:
        if self.input is None and not self.messages:
            raise ValueError(f"case {self.id!r}: must provide either `input` or `messages`")
        if self.input is not None and self.messages:
            raise ValueError(f"case {self.id!r}: provide `input` OR `messages`, not both")
        return self

    def build_messages(self, default_system: str | None) -> list[Message]:
        if self.messages:
            return list(self.messages)
        msgs: list[Message] = []
        system = self.system or default_system
        if system:
            msgs.append(Message(role=Role.SYSTEM, content=system))
        assert self.input is not None  # validator guarantees
        msgs.append(Message(role=Role.USER, content=self.input))
        return msgs


class Suite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    version: int = 1
    tags: list[str] = Field(default_factory=list)
    defaults: SuiteDefaults = Field(default_factory=SuiteDefaults)
    cases: list[Case]

    # Populated by the loader, not user-authored.
    source_path: str | None = None
    content_sha256: str | None = None

    @model_validator(mode="after")
    def _unique_case_ids(self) -> Self:
        seen: set[str] = set()
        for c in self.cases:
            if c.id in seen:
                raise ValueError(f"duplicate case id {c.id!r} in suite {self.name!r}")
            seen.add(c.id)
        return self

    def is_redteam(self) -> bool:
        """A suite is a red-team suite if any case carries OWASP taxonomy."""
        return any(c.owasp is not None for c in self.cases)


# ---------------------------------------------------------------------------
# Results / scorecard
# ---------------------------------------------------------------------------


class AssertionResult(BaseModel):
    kind: str
    label: str | None = None
    passed: bool
    score: float | None = None
    detail: str | None = None
    error: str | None = None


class CaseResult(BaseModel):
    case_id: str
    passed: bool
    skipped: bool = False
    assertion_results: list[AssertionResult] = Field(default_factory=list)

    # Red-team: did the model defend against the attack?
    # None for non-red-team cases.
    defended: bool | None = None

    # Model interaction
    request_messages: list[Message] = Field(default_factory=list)
    response_text: str | None = None
    finish_reason: str | None = None
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    cached: bool = False
    error: str | None = None

    # Echo of taxonomy fields for easy reporting
    owasp: OwaspLLM | None = None
    attack_class: AttackClass | None = None
    severity: Severity | None = None
    tags: list[str] = Field(default_factory=list)
    atlas: list[str] = Field(default_factory=list)
    nist_ai_rmf: list[str] = Field(default_factory=list)


class IntervalCI(BaseModel):
    """95% Wilson score interval for a binary proportion."""

    low: float
    high: float


class ClassBreakdown(BaseModel):
    """Aggregate stats for one OWASP class (red-team only)."""

    owasp: OwaspLLM
    cases: int
    defended: int
    defense_rate: float
    defense_rate_ci_95: IntervalCI


ATLAS_NAMES = {
    "AML.TA0000": "Reconnaissance",
    "AML.TA0001": "Resource Development",
    "AML.TA0002": "Initial Access",
    "AML.TA0003": "Execution",
    "AML.TA0004": "Persistence",
    "AML.TA0005": "Privilege Escalation",
    "AML.TA0006": "Defense Evasion",
    "AML.TA0007": "Credential Access",
    "AML.TA0008": "Discovery",
    "AML.TA0009": "Lateral Movement",
    "AML.TA0010": "Collection",
    "AML.TA0011": "Exfiltration",
    "AML.TA0012": "Impact",
    "AML.T0051": "LLM Prompt Injection",
    "AML.T0051.000": "Direct Prompt Injection",
    "AML.T0051.001": "Indirect Prompt Injection",
    "AML.T0054": "LLM Leak System Prompts",
    "AML.T0055": "Model Inversion",
    "AML.T0057": "LLM Data Exfiltration",
    "AML.T0058": "Adversarial Fuzzing",
}

NIST_NAMES = {
    "GOVERN": "Govern Function",
    "MAP": "Map Function",
    "MEASURE": "Measure Function",
    "MANAGE": "Manage Function",
    "MEASURE-2.4": "Vulnerability & Robustness Auditing",
    "MAP-1.1": "Context Characterization",
    "MANAGE-1.2": "Risk Mitigation & Treatment",
}


class AtlasBreakdown(BaseModel):
    """Aggregate stats for one MITRE ATLAS tactic or technique."""

    id: str
    name: str
    cases: int
    defended: int
    defense_rate: float
    defense_rate_ci_95: IntervalCI


class NistBreakdown(BaseModel):
    """Aggregate stats for one NIST AI RMF function or category."""

    id: str
    name: str
    cases: int
    defended: int
    defense_rate: float
    defense_rate_ci_95: IntervalCI


class Totals(BaseModel):
    cases: int
    passed: int
    failed: int
    skipped: int = 0
    errored: int = 0
    pass_rate: float
    pass_rate_ci_95: IntervalCI

    # Red-team aggregate (only set when suite is_redteam())
    defense_rate: float | None = None
    defense_rate_ci_95: IntervalCI | None = None
    by_owasp: list[ClassBreakdown] = Field(default_factory=list)
    by_atlas: list[AtlasBreakdown] = Field(default_factory=list)
    by_nist: list[NistBreakdown] = Field(default_factory=list)

    # Cost & performance
    cost_usd: Decimal = Decimal("0")
    tokens_in: int = 0
    tokens_out: int = 0
    wall_clock_s: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0


class ModelMeta(BaseModel):
    provider: str
    name: str
    params: ChatParams


class SuiteMeta(BaseModel):
    path: str | None
    name: str
    version: int
    sha256: str | None


class AppProfile(BaseModel):
    """Configuration for simulating an application's architecture."""
    name: str
    system_prompt: str | None = None
    input_template: str | None = None  # e.g., "<user_input>\n{{ payload }}\n</user_input>"


class JudgeMeta(BaseModel):
    """Captured when any case used an LLM judge."""

    model: str
    calibration_run_id: str | None = None
    calibration_age_days: int | None = None


class Environment(BaseModel):
    reagent_version: str
    python_version: str
    platform: str
    git_sha: str | None = None
    git_dirty: bool | None = None


class Scorecard(BaseModel):
    """Canonical artifact produced by a run."""

    schema_version: str = SCHEMA_VERSION
    run_id: str = Field(default_factory=_new_run_id)
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None

    model: ModelMeta
    suite: SuiteMeta
    judge: JudgeMeta | None = None
    is_redteam: bool = False

    totals: Totals
    cases: list[CaseResult] = Field(default_factory=list)
    environment: Environment


# ---------------------------------------------------------------------------
# Project Configuration (reagent.yaml)
# ---------------------------------------------------------------------------

class ConfigCorpus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extra_cases: list[str] = Field(default_factory=list)

class ConfigTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    url: str | None = None


class ConfigCompliance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frameworks: list[str] = Field(default_factory=list)
    minimum_severity: Severity | None = None


class ProjectConfig(BaseModel):
    """Root configuration for reagent.yaml"""
    model_config = ConfigDict(extra="forbid")
    
    target: ConfigTarget | None = None
    corpus: ConfigCorpus = Field(default_factory=ConfigCorpus)
    compliance: ConfigCompliance = Field(default_factory=ConfigCompliance)
    judge: JudgeConfig | None = None
    model: str | None = None # Allow setting a default model in config


__all__ = [
    "SCHEMA_VERSION",
    "AssertionDef",
    "AssertionResult",
    "AttackClass",
    "AttackOutcome",
    "Case",
    "CaseResult",
    "ChatParams",
    "ChatRequest",
    "ChatResponse",
    "ChatUsage",
    "ClassBreakdown",
    "ConfigCompliance",
    "ConfigTarget",
    "ContainsAnyAssertionDef",
    "Environment",
    "IntervalCI",
    "JudgeConfig",
    "JudgeMeta",
    "LLMJudgeAssertionDef",
    "Message",
    "ModelMeta",
    "NotContainsAssertionDef",
    "OwaspLLM",
    "ProjectConfig",
    "RefusalAssertionDef",
    "RegexAssertionDef",
    "Role",
    "Scorecard",
    "Severity",
    "Suite",
    "SuiteDefaults",
    "SuiteMeta",
    "Totals",
]
