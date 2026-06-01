"""Shared base types for assertion evaluators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol

from reagent.adapters.base import Adapter
from reagent.models import AssertionDef, AssertionResult


@dataclass(slots=True)
class EvalContext:
    """Context passed to every assertion evaluator.

    The ``judge_caller`` is provided by the runner so that ``llm_judge``
    assertions can issue completion requests through the same adapter pool as
    the rest of the suite, with caching and concurrency limits applied.
    """

    case_id: str
    response_text: str
    # Lazy resolver for the judge adapter — only invoked if a judge is used.
    # Returning None means no judge is configured (assertion will error).
    judge_caller: "JudgeCaller | None" = None


class JudgeCaller(Protocol):
    """Capability passed into LLM-judge assertions to actually call the judge model."""

    async def __call__(self, model: str, system: str, user: str) -> str: ...


class Evaluator(Protocol):
    """Static protocol for assertion-kind evaluators."""

    kind: ClassVar[str]

    @staticmethod
    async def evaluate(definition: AssertionDef, ctx: EvalContext) -> AssertionResult: ...


__all__ = ["EvalContext", "Evaluator", "JudgeCaller"]
