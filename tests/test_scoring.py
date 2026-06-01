"""Tests for the scoring module that assembles Totals from CaseResults."""

from __future__ import annotations

from decimal import Decimal

from reagent.models import CaseResult, OwaspLLM, Severity
from reagent.runner.scoring import assemble_totals


def make_case(
    *,
    case_id: str,
    passed: bool,
    defended: bool | None,
    owasp: OwaspLLM | None,
    skipped: bool = False,
    error: str | None = None,
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        passed=passed,
        defended=defended,
        skipped=skipped,
        error=error,
        owasp=owasp,
        severity=Severity.HIGH if owasp else None,
        cost_usd=Decimal("0.01"),
        prompt_tokens=10,
        completion_tokens=20,
    )


def test_totals_pass_rate_no_redteam():
    results = [
        make_case(case_id="a", passed=True, defended=None, owasp=None),
        make_case(case_id="b", passed=False, defended=None, owasp=None),
    ]
    t = assemble_totals(results, is_redteam=False, wall_clock_s=1.0,
                        cache_hits=0, cache_misses=2)
    assert t.cases == 2
    assert t.passed == 1
    assert t.failed == 1
    assert t.pass_rate == 0.5
    assert t.defense_rate is None
    assert t.by_owasp == []
    assert t.tokens_in == 20 and t.tokens_out == 40


def test_totals_redteam_defense_rate_and_breakdown():
    results = [
        make_case(case_id="a", passed=True, defended=True, owasp=OwaspLLM.LLM01),
        make_case(case_id="b", passed=False, defended=False, owasp=OwaspLLM.LLM01),
        make_case(case_id="c", passed=True, defended=True, owasp=OwaspLLM.LLM07),
    ]
    t = assemble_totals(results, is_redteam=True, wall_clock_s=1.0,
                        cache_hits=1, cache_misses=2)
    assert t.defense_rate is not None and t.defense_rate == 2 / 3
    assert t.defense_rate_ci_95 is not None
    assert t.defense_rate_ci_95.low < t.defense_rate < t.defense_rate_ci_95.high

    # Per-OWASP breakdown
    by_class = {b.owasp: b for b in t.by_owasp}
    assert by_class[OwaspLLM.LLM01].defended == 1
    assert by_class[OwaspLLM.LLM01].cases == 2
    assert by_class[OwaspLLM.LLM01].defense_rate == 0.5
    assert by_class[OwaspLLM.LLM07].defense_rate == 1.0


def test_totals_skipped_cases_excluded_from_rate():
    results = [
        make_case(case_id="a", passed=True, defended=None, owasp=None),
        make_case(case_id="b", passed=False, defended=None, owasp=None,
                  skipped=True, error="budget_exceeded"),
    ]
    t = assemble_totals(results, is_redteam=False, wall_clock_s=1.0,
                        cache_hits=0, cache_misses=1)
    assert t.skipped == 1
    assert t.passed == 1
    assert t.pass_rate == 1.0  # 1 out of 1 non-skipped


def test_totals_errored_counted_separately():
    results = [
        make_case(case_id="a", passed=False, defended=None, owasp=None,
                  error="boom"),
        make_case(case_id="b", passed=True, defended=None, owasp=None),
    ]
    t = assemble_totals(results, is_redteam=False, wall_clock_s=1.0,
                        cache_hits=0, cache_misses=2)
    assert t.errored == 1
    assert t.failed == 0
    assert t.passed == 1
