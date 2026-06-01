"""LLM-as-judge assertion.

The judge model is asked to score the response on a configured rubric and
returns strict JSON. Free-text judges are unreliable; structured outputs are
mandatory. Rubrics may be inlined or referenced via ``@path/to/rubric.md``.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import ClassVar

from reagent.assertions.base import EvalContext
from reagent.models import AssertionResult, LLMJudgeAssertionDef

_log = logging.getLogger(__name__)

# Format instructions appended to the rubric so we can parse the response.
_JUDGE_INSTRUCTIONS = """
You are an impartial evaluator. Read the rubric and the candidate response,
then return your judgment as STRICT JSON on a single line with these fields:

  {{"score": <number {min}..{max}>, "rationale": "<one sentence>", "pass": <true|false>}}

Do not include any text before or after the JSON. Do not wrap it in code fences.
The `pass` field MUST be true iff `score >= {min}`.
"""


_JSON_BLOCK_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _load_rubric(rubric: str) -> str:
    if rubric.startswith("@"):
        path = Path(rubric[1:]).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"rubric file not found: {path}")
        return path.read_text(encoding="utf-8")
    return rubric


def _parse_judge_json(text: str) -> dict[str, object]:
    """Best-effort JSON extraction from the judge's reply.

    Some local models still leak prose around the JSON despite instructions, so
    we fall back to the first balanced ``{...}`` block.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: pull the first JSON object out of the text.
    match = _JSON_BLOCK_RE.search(text)
    if match is None:
        raise ValueError(f"judge did not return JSON; got: {text[:200]!r}")
    return json.loads(match.group(0))


class LLMJudgeAssertion:
    kind: ClassVar[str] = "llm_judge"

    @staticmethod
    async def evaluate(
        definition: LLMJudgeAssertionDef, ctx: EvalContext
    ) -> AssertionResult:
        if ctx.judge_caller is None:
            return AssertionResult(
                kind=definition.kind,
                label=definition.label,
                passed=False,
                error="llm_judge assertion used but runner did not configure a judge caller",
            )

        try:
            rubric = _load_rubric(definition.rubric)
        except FileNotFoundError as exc:
            return AssertionResult(
                kind=definition.kind,
                label=definition.label,
                passed=False,
                error=str(exc),
            )

        instructions = _JUDGE_INSTRUCTIONS.format(
            min=definition.score_min, max=definition.score_max
        )
        system_prompt = rubric.strip() + "\n" + instructions
        user_prompt = (
            f"Candidate response to evaluate:\n---\n{ctx.response_text}\n---\n"
            "Return only the JSON object."
        )

        try:
            raw = await ctx.judge_caller(
                model=definition.judge_model,
                system=system_prompt,
                user=user_prompt,
            )
        except Exception as exc:  # adapter errors bubble up here
            _log.warning("judge call failed for case %s: %s", ctx.case_id, exc)
            return AssertionResult(
                kind=definition.kind,
                label=definition.label,
                passed=False,
                error=f"judge call failed: {exc}",
            )

        try:
            verdict = _parse_judge_json(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            return AssertionResult(
                kind=definition.kind,
                label=definition.label,
                passed=False,
                error=f"could not parse judge output: {exc}",
            )

        try:
            score = float(verdict["score"])  # type: ignore[arg-type]
        except (KeyError, TypeError, ValueError):
            return AssertionResult(
                kind=definition.kind,
                label=definition.label,
                passed=False,
                error=f"judge response missing numeric score: {verdict!r}",
            )

        rationale = str(verdict.get("rationale", "")).strip()
        # Trust the score, not the model's self-reported pass field.
        passed = score >= definition.score_min

        return AssertionResult(
            kind=definition.kind,
            label=definition.label,
            passed=passed,
            score=score,
            detail=f"score={score:.2f} (min={definition.score_min}); {rationale}",
        )


__all__ = ["LLMJudgeAssertion"]
