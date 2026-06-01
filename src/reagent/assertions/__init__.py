"""Assertion engine — dispatches an :class:`AssertionDef` to its evaluator.

Each assertion kind is implemented as a class with a ``kind`` ClassVar and a
``evaluate`` coroutine. The dispatch table is built once at import time.
"""

from __future__ import annotations

from reagent.assertions.base import EvalContext, Evaluator
from reagent.assertions.contains import ContainsAnyAssertion, NotContainsAssertion
from reagent.assertions.llm_judge import LLMJudgeAssertion
from reagent.assertions.refusal import RefusalAssertion
from reagent.assertions.regex import RegexAssertion
from reagent.models import AssertionResult

_EVALUATORS: dict[str, type[Evaluator]] = {
    cls.kind: cls
    for cls in (
        RegexAssertion,
        ContainsAnyAssertion,
        NotContainsAssertion,
        RefusalAssertion,
        LLMJudgeAssertion,
    )
}


async def evaluate(definition, ctx: EvalContext) -> AssertionResult:  # type: ignore[no-untyped-def]
    """Dispatch to the evaluator class for ``definition.kind``."""
    try:
        evaluator = _EVALUATORS[definition.kind]
    except KeyError as exc:
        raise ValueError(f"unknown assertion kind {definition.kind!r}") from exc
    return await evaluator.evaluate(definition, ctx)


__all__ = [
    "ContainsAnyAssertion",
    "EvalContext",
    "Evaluator",
    "LLMJudgeAssertion",
    "NotContainsAssertion",
    "RefusalAssertion",
    "RegexAssertion",
    "evaluate",
]
