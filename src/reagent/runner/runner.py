"""The async run loop that turns a :class:`Suite` into a :class:`Scorecard`."""

from __future__ import annotations

import asyncio
import logging
import platform
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal

from reagent import __version__
from reagent.adapters import resolve_adapter
from reagent.adapters.base import Adapter, AdapterError, parse_model_string
from reagent.assertions import evaluate as evaluate_assertion
from reagent.assertions.base import EvalContext
from reagent.models import (
    AppProfile,
    AssertionResult,
    AttackOutcome,
    Case,
    CaseResult,
    ChatParams,
    ChatRequest,
    ChatResponse,
    ChatUsage,
    Environment,
    JudgeMeta,
    LLMJudgeAssertionDef,
    Message,
    ModelMeta,
    Role,
    Scorecard,
    Suite,
    SuiteMeta,
)
from reagent.runner.cache import ResponseCache
from reagent.runner.scoring import assemble_totals

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class RunConfig:
    """All knobs for a single run."""

    model: str
    concurrency: int = 5
    use_cache: bool = True
    cache_dir: str | None = None
    budget_usd: Decimal | None = None
    # Overrides applied on top of suite defaults; per-case overrides still win.
    override_params: ChatParams | None = None
    # Optional pinning of the judge model when an assertion did not pin its own.
    default_judge_model: str | None = None
    # Optional AppProfile to override suite defaults for system-level testing
    app_profile: AppProfile | None = None


@dataclass(slots=True)
class RunResult:
    scorecard: Scorecard
    # Surface aborts so the CLI can return a distinct exit code.
    aborted_on_budget: bool = False
    errors: list[str] = field(default_factory=list)


class _AdapterPool:
    """Lazy adapter cache shared across model calls in one run.

    One :class:`Adapter` instance per provider is constructed on first use and
    reused. ``aclose`` releases them all.
    """

    def __init__(self) -> None:
        self._by_provider: dict[str, Adapter] = {}

    def get(self, model: str) -> Adapter:
        provider, _ = parse_model_string(model)
        adapter = self._by_provider.get(provider)
        if adapter is None:
            adapter = resolve_adapter(model)
            self._by_provider[provider] = adapter
        return adapter

    async def aclose(self) -> None:
        for adapter in self._by_provider.values():
            try:
                await adapter.aclose()
            except Exception as exc:  # pragma: no cover — defensive
                _log.warning("error closing adapter %r: %s", adapter.name, exc)


async def _call_model(
    request: ChatRequest,
    *,
    pool: _AdapterPool,
    cache: ResponseCache,
    semaphore: asyncio.Semaphore,
) -> ChatResponse:
    """Single completion with cache + concurrency limiting."""
    cached = cache.get(request)
    if cached is not None:
        return cached
    async with semaphore:
        adapter = pool.get(request.model)
        response = await adapter.complete(request)
    cache.put(request, response)
    return response


def _make_judge_caller(
    pool: _AdapterPool,
    cache: ResponseCache,
    semaphore: asyncio.Semaphore,
    judge_params: ChatParams,
):
    """Build the JudgeCaller capability used by `llm_judge` assertions."""

    async def call(model: str, system: str, user: str) -> str:
        req = ChatRequest(
            model=model,
            messages=(
                Message(role=Role.SYSTEM, content=system),
                Message(role=Role.USER, content=user),
            ),
            params=judge_params,
        )
        resp = await _call_model(req, pool=pool, cache=cache, semaphore=semaphore)
        return resp.text

    return call


def _build_request(case: Case, suite: Suite, config: RunConfig) -> ChatRequest:
    """Compose a ChatRequest from suite defaults + case overrides + RunConfig."""
    defaults = suite.defaults
    overrides = config.override_params

    temperature = (
        case.temperature
        if case.temperature is not None
        else (overrides.temperature if overrides else defaults.temperature)
    )
    max_tokens = (
        case.max_tokens
        if case.max_tokens is not None
        else (overrides.max_tokens if overrides else defaults.max_tokens)
    )
    seed = (
        case.seed
        if case.seed is not None
        else (overrides.seed if overrides else defaults.seed)
    )

    params = ChatParams(temperature=temperature, max_tokens=max_tokens, seed=seed)
    
    if config.app_profile:
        system = config.app_profile.system_prompt or defaults.system
        input_text = case.input
        if config.app_profile.input_template and input_text:
            input_text = config.app_profile.input_template.replace("{{ payload }}", input_text)
            
        msgs = []
        if system:
            msgs.append(Message(role=Role.SYSTEM, content=system))
        if input_text:
            msgs.append(Message(role=Role.USER, content=input_text))
            
        return ChatRequest(
            model=config.model,
            messages=tuple(msgs),
            params=params,
        )

    messages = case.build_messages(default_system=defaults.system)

    return ChatRequest(
        model=config.model,
        messages=tuple(messages),
        params=params,
    )


async def _run_one(
    case: Case,
    suite: Suite,
    config: RunConfig,
    *,
    pool: _AdapterPool,
    cache: ResponseCache,
    semaphore: asyncio.Semaphore,
    judge_caller,
) -> CaseResult:
    request = _build_request(case, suite, config)

    # 1. Get the response.
    try:
        response = await _call_model(
            request, pool=pool, cache=cache, semaphore=semaphore
        )
    except AdapterError as exc:
        _log.warning("case %s: adapter error: %s", case.id, exc)
        return CaseResult(
            case_id=case.id,
            passed=False,
            error=f"adapter error: {exc}",
            request_messages=list(request.messages),
            owasp=case.owasp,
            attack_class=case.attack_class,
            severity=case.severity,
            tags=list(case.tags),
            atlas=list(case.atlas),
            nist_ai_rmf=list(case.nist_ai_rmf),
        )

    # 2. Patch judge models if the case left them unspecified and we have a
    # default. We avoid mutating the source case by rebuilding the assertion.
    patched_assertions = []
    for assertion in case.assertions:
        if (
            isinstance(assertion, LLMJudgeAssertionDef)
            and not assertion.judge_model
            and config.default_judge_model
        ):
            patched_assertions.append(
                assertion.model_copy(update={"judge_model": config.default_judge_model})
            )
        else:
            patched_assertions.append(assertion)

    # 3. Evaluate assertions sequentially within a case (they are cheap; we
    # already parallelize at the case level).
    assertion_results: list[AssertionResult] = []
    ctx = EvalContext(
        case_id=case.id, response_text=response.text, judge_caller=judge_caller
    )
    for assertion in patched_assertions:
        try:
            result = await evaluate_assertion(assertion, ctx)
        except Exception as exc:  # safety net — assertions should not raise
            _log.exception("case %s: assertion %s raised", case.id, assertion.kind)
            result = AssertionResult(
                kind=assertion.kind,
                label=assertion.label,
                passed=False,
                error=f"unhandled error in assertion: {exc}",
            )
        assertion_results.append(result)

    # 4. Aggregate. `attack_succeeded_means` controls the polarity:
    # - MODEL_FAILED  : assertions detect *attack success*; matching => model failed.
    # - MODEL_PASSED  : assertions verify *correct behavior*; matching => model passed.
    # `defended` is reported only for red-team cases (those carrying an OWASP tag).
    if not assertion_results:
        all_matched = True
    else:
        all_matched = all(r.passed and r.error is None for r in assertion_results)

    if case.attack_succeeded_means == AttackOutcome.MODEL_FAILED:
        case_passed = not all_matched
    else:
        case_passed = all_matched

    defended = case_passed if case.owasp is not None else None

    return CaseResult(
        case_id=case.id,
        passed=case_passed,
        defended=defended,
        assertion_results=assertion_results,
        request_messages=list(request.messages),
        response_text=response.text,
        finish_reason=response.finish_reason,
        latency_ms=response.latency_ms,
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        cost_usd=response.cost_usd,
        cached=response.cached,
        owasp=case.owasp,
        attack_class=case.attack_class,
        severity=case.severity,
        tags=list(case.tags),
        atlas=list(case.atlas),
        nist_ai_rmf=list(case.nist_ai_rmf),
    )


def _skipped_result(case: Case, reason: str) -> CaseResult:
    return CaseResult(
        case_id=case.id,
        passed=False,
        skipped=True,
        error=reason,
        owasp=case.owasp,
        attack_class=case.attack_class,
        severity=case.severity,
        tags=list(case.tags),
        atlas=list(case.atlas),
        nist_ai_rmf=list(case.nist_ai_rmf),
    )


def _has_judge(suite: Suite) -> tuple[bool, str | None]:
    """Return (uses_judge, first_judge_model)."""
    for case in suite.cases:
        for assertion in case.assertions:
            if isinstance(assertion, LLMJudgeAssertionDef):
                return True, assertion.judge_model
    return False, None


async def run_suite(suite: Suite, config: RunConfig) -> RunResult:
    """Execute ``suite`` against ``config.model`` and return a :class:`RunResult`."""
    provider, model_name = parse_model_string(config.model)
    started_at = time.time()
    started_perf = time.perf_counter()
    semaphore = asyncio.Semaphore(max(1, config.concurrency))
    cache = ResponseCache(root=config.cache_dir, enabled=config.use_cache)
    pool = _AdapterPool()
    judge_caller = _make_judge_caller(
        pool,
        cache,
        semaphore,
        judge_params=ChatParams(temperature=0.0, max_tokens=512),
    )

    results_by_id: dict[str, CaseResult] = {}
    aborted_on_budget = False
    errors: list[str] = []

    async def task(c: Case) -> None:
        try:
            results_by_id[c.id] = await _run_one(
                c, suite, config,
                pool=pool, cache=cache, semaphore=semaphore, judge_caller=judge_caller,
            )
        except Exception as exc:
            _log.exception("case %s: unhandled error", c.id)
            errors.append(f"case {c.id}: {exc}")
            results_by_id[c.id] = CaseResult(
                case_id=c.id, passed=False, error=f"unhandled error: {exc}",
                owasp=c.owasp, attack_class=c.attack_class,
                severity=c.severity, tags=list(c.tags),
                atlas=list(c.atlas), nist_ai_rmf=list(c.nist_ai_rmf),
            )

    try:
        if config.budget_usd is None:
            # Fan out the whole suite at once; the semaphore caps concurrency.
            await asyncio.gather(*(task(c) for c in suite.cases))
        else:
            # Budget mode: process in chunks so we can check spend mid-run.
            # Chunk size mirrors concurrency so the check fires at sensible intervals.
            chunk_size = max(1, config.concurrency)
            spent = Decimal("0")
            i = 0
            cases = list(suite.cases)
            while i < len(cases):
                chunk = cases[i : i + chunk_size]
                await asyncio.gather(*(task(c) for c in chunk))
                i += chunk_size
                spent = sum(
                    (r.cost_usd for r in results_by_id.values()),
                    Decimal("0"),
                )
                if spent >= config.budget_usd:
                    _log.warning(
                        "budget of $%s reached after %d cases (spent $%s); aborting",
                        config.budget_usd, len(results_by_id), spent,
                    )
                    aborted_on_budget = True
                    for remaining in cases[i:]:
                        results_by_id[remaining.id] = _skipped_result(
                            remaining, reason="budget_exceeded"
                        )
                    break
    finally:
        await pool.aclose()

    wall_clock_s = time.perf_counter() - started_perf

    # Preserve declared order.
    ordered_results = [results_by_id[c.id] for c in suite.cases]

    totals = assemble_totals(
        ordered_results,
        is_redteam=suite.is_redteam(),
        wall_clock_s=wall_clock_s,
        cache_hits=cache.hits,
        cache_misses=cache.misses,
    )

    uses_judge, first_judge_model = _has_judge(suite)
    judge_meta = JudgeMeta(model=first_judge_model or "") if uses_judge and first_judge_model else None

    scorecard = Scorecard(
        started_at=_iso(started_at),
        finished_at=_iso(time.time()),
        model=ModelMeta(
            provider=provider,
            name=model_name,
            params=config.override_params or ChatParams(),
        ),
        suite=SuiteMeta(
            path=suite.source_path,
            name=suite.name,
            version=suite.version,
            sha256=suite.content_sha256,
        ),
        judge=judge_meta,
        is_redteam=suite.is_redteam(),
        totals=totals,
        cases=ordered_results,
        environment=Environment(
            reagent_version=__version__,
            python_version=sys.version.split()[0],
            platform=platform.platform(),
        ),
    )

    return RunResult(
        scorecard=scorecard,
        aborted_on_budget=aborted_on_budget,
        errors=errors,
    )


def _iso(epoch: float):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


# Suppress unused-import lint — these are re-exported for tests and consumers.
_ = (ChatUsage, AssertionResult)

__all__ = ["RunConfig", "RunResult", "run_suite"]
