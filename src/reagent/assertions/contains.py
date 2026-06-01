"""Substring containment assertions (positive and negative)."""

from __future__ import annotations

from typing import ClassVar

from reagent.assertions.base import EvalContext
from reagent.models import AssertionResult, ContainsAnyAssertionDef, NotContainsAssertionDef


def _normalize(text: str, case_sensitive: bool) -> str:
    return text if case_sensitive else text.lower()


def _find_first(text: str, needles: list[str], case_sensitive: bool) -> str | None:
    haystack = _normalize(text, case_sensitive)
    for needle in needles:
        if _normalize(needle, case_sensitive) in haystack:
            return needle
    return None


class ContainsAnyAssertion:
    """Passes when the response contains at least one of the configured values."""

    kind: ClassVar[str] = "contains_any"

    @staticmethod
    async def evaluate(
        definition: ContainsAnyAssertionDef, ctx: EvalContext
    ) -> AssertionResult:
        hit = _find_first(ctx.response_text, definition.values, definition.case_sensitive)
        return AssertionResult(
            kind=definition.kind,
            label=definition.label,
            passed=hit is not None,
            detail=f"matched: {hit!r}" if hit else "no expected substring present",
        )


class NotContainsAssertion:
    """Passes when none of the configured values appear in the response."""

    kind: ClassVar[str] = "not_contains"

    @staticmethod
    async def evaluate(
        definition: NotContainsAssertionDef, ctx: EvalContext
    ) -> AssertionResult:
        hit = _find_first(ctx.response_text, definition.values, definition.case_sensitive)
        return AssertionResult(
            kind=definition.kind,
            label=definition.label,
            passed=hit is None,
            detail=f"forbidden substring present: {hit!r}" if hit else "no forbidden substring",
        )


__all__ = ["ContainsAnyAssertion", "NotContainsAssertion"]
