"""Unit tests for assertion evaluators."""

from __future__ import annotations

import pytest

from reagent.assertions import evaluate
from reagent.assertions.base import EvalContext
from reagent.assertions.refusal import detect_refusal
from reagent.models import (
    ContainsAnyAssertionDef,
    LLMJudgeAssertionDef,
    NotContainsAssertionDef,
    RefusalAssertionDef,
    RegexAssertionDef,
)


def ctx(text: str, judge_caller=None) -> EvalContext:
    return EvalContext(case_id="t", response_text=text, judge_caller=judge_caller)


# ---- regex ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_regex_must_match_passes_on_match():
    r = await evaluate(RegexAssertionDef(pattern=r"\bfoo\b"), ctx("the foo bar"))
    assert r.passed


@pytest.mark.asyncio
async def test_regex_must_match_fails_on_no_match():
    r = await evaluate(RegexAssertionDef(pattern=r"zzz"), ctx("the foo bar"))
    assert not r.passed


@pytest.mark.asyncio
async def test_regex_must_not_match_inverted():
    r = await evaluate(
        RegexAssertionDef(pattern=r"\bsecret\b", must_match=False), ctx("hello world")
    )
    assert r.passed


@pytest.mark.asyncio
async def test_regex_flags_case_insensitive():
    r = await evaluate(
        RegexAssertionDef(pattern=r"foo", flags="i"), ctx("FOO bar")
    )
    assert r.passed


@pytest.mark.asyncio
async def test_regex_invalid_pattern_returns_error():
    r = await evaluate(RegexAssertionDef(pattern=r"["), ctx("anything"))
    assert not r.passed
    assert r.error is not None and "invalid regex" in r.error


@pytest.mark.asyncio
async def test_regex_unknown_flag_returns_error():
    r = await evaluate(RegexAssertionDef(pattern=r"foo", flags="z"), ctx("foo"))
    assert not r.passed
    assert r.error is not None


# ---- contains -------------------------------------------------------------


@pytest.mark.asyncio
async def test_contains_any_case_insensitive_by_default():
    r = await evaluate(
        ContainsAnyAssertionDef(values=["hello"]), ctx("HELLO there")
    )
    assert r.passed


@pytest.mark.asyncio
async def test_contains_any_case_sensitive():
    r = await evaluate(
        ContainsAnyAssertionDef(values=["hello"], case_sensitive=True),
        ctx("HELLO there"),
    )
    assert not r.passed


@pytest.mark.asyncio
async def test_not_contains_passes_when_absent():
    r = await evaluate(NotContainsAssertionDef(values=["nope"]), ctx("hello"))
    assert r.passed


@pytest.mark.asyncio
async def test_not_contains_fails_when_present():
    r = await evaluate(NotContainsAssertionDef(values=["leak"]), ctx("we leak data"))
    assert not r.passed
    assert "leak" in (r.detail or "")


# ---- refusal --------------------------------------------------------------


def test_detect_refusal_matches_common_openers():
    assert detect_refusal("I'm sorry, but I can't help with that.") is not None
    assert detect_refusal("I cannot fulfill this request.") is not None
    assert detect_refusal("As an AI, I have to decline.") is not None


def test_detect_refusal_misses_non_refusal_text():
    assert detect_refusal("Sure, here's the answer.") is None
    assert detect_refusal("The answer is 42.") is None


def test_detect_refusal_only_scans_leading_window():
    # Refusal phrase past the window should not match.
    long_prefix = "ok. " * 200
    assert detect_refusal(long_prefix + "I cannot do that") is None


@pytest.mark.asyncio
async def test_refusal_assertion_expected_true_passes_on_refusal():
    r = await evaluate(
        RefusalAssertionDef(expected=True), ctx("I'm sorry, but I cannot.")
    )
    assert r.passed


@pytest.mark.asyncio
async def test_refusal_assertion_expected_false_passes_on_helpful():
    r = await evaluate(
        RefusalAssertionDef(expected=False), ctx("Sure — here's the recipe.")
    )
    assert r.passed


# ---- llm_judge ------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_judge_passes_above_threshold():
    async def judge(model: str, system: str, user: str) -> str:
        return '{"score": 4.5, "rationale": "good", "pass": true}'

    r = await evaluate(
        LLMJudgeAssertionDef(rubric="dummy rubric", judge_model="fake:m"),
        ctx("a response", judge_caller=judge),
    )
    assert r.passed
    assert r.score == 4.5


@pytest.mark.asyncio
async def test_llm_judge_fails_below_threshold():
    async def judge(model: str, system: str, user: str) -> str:
        return '{"score": 2, "rationale": "weak", "pass": false}'

    r = await evaluate(
        LLMJudgeAssertionDef(rubric="dummy rubric", judge_model="fake:m"),
        ctx("a response", judge_caller=judge),
    )
    assert not r.passed
    assert r.score == 2.0


@pytest.mark.asyncio
async def test_llm_judge_recovers_from_prose_wrapped_json():
    async def judge(model: str, system: str, user: str) -> str:
        return 'Here is my judgment:\n{"score": 5, "rationale": "great", "pass": true}\nThanks.'

    r = await evaluate(
        LLMJudgeAssertionDef(rubric="dummy rubric", judge_model="fake:m"),
        ctx("a response", judge_caller=judge),
    )
    assert r.passed


@pytest.mark.asyncio
async def test_llm_judge_errors_when_no_judge_caller():
    r = await evaluate(
        LLMJudgeAssertionDef(rubric="dummy rubric", judge_model="fake:m"),
        ctx("a response", judge_caller=None),
    )
    assert not r.passed
    assert r.error is not None


@pytest.mark.asyncio
async def test_llm_judge_errors_on_unparseable_response():
    async def judge(model: str, system: str, user: str) -> str:
        return "no json here"

    r = await evaluate(
        LLMJudgeAssertionDef(rubric="dummy rubric", judge_model="fake:m"),
        ctx("a response", judge_caller=judge),
    )
    assert not r.passed
    assert r.error is not None
