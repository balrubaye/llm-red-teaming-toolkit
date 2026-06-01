"""Regex assertion — pattern match against the model output."""

from __future__ import annotations

import re
from typing import ClassVar

from reagent.assertions.base import EvalContext
from reagent.models import AssertionResult, RegexAssertionDef

_FLAG_MAP = {
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "s": re.DOTALL,
    "x": re.VERBOSE,
}


def _compile_flags(spec: str) -> int:
    flags = 0
    for ch in spec.lower():
        try:
            flags |= _FLAG_MAP[ch]
        except KeyError as exc:
            raise ValueError(
                f"unknown regex flag {ch!r}; supported: {''.join(_FLAG_MAP)}"
            ) from exc
    return flags


class RegexAssertion:
    kind: ClassVar[str] = "regex"

    @staticmethod
    async def evaluate(definition: RegexAssertionDef, ctx: EvalContext) -> AssertionResult:
        try:
            pattern = re.compile(definition.pattern, _compile_flags(definition.flags))
        except re.error as exc:
            return AssertionResult(
                kind=definition.kind,
                label=definition.label,
                passed=False,
                error=f"invalid regex {definition.pattern!r}: {exc}",
            )
        except ValueError as exc:
            # Raised by _compile_flags on unknown flag chars.
            return AssertionResult(
                kind=definition.kind,
                label=definition.label,
                passed=False,
                error=str(exc),
            )

        match = pattern.search(ctx.response_text)
        matched = match is not None
        passed = matched if definition.must_match else not matched

        detail: str
        if matched and match is not None:
            snippet = match.group(0)
            if len(snippet) > 200:
                snippet = snippet[:200] + "…"
            detail = f"matched: {snippet!r}"
        else:
            detail = "no match"

        return AssertionResult(
            kind=definition.kind,
            label=definition.label,
            passed=passed,
            detail=detail,
        )


__all__ = ["RegexAssertion"]
