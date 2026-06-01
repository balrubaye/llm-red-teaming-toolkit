"""Smoke tests for the reporters — render and roundtrip."""

from __future__ import annotations

import json
from decimal import Decimal

from reagent.models import (
    AssertionResult,
    CaseResult,
    ClassBreakdown,
    Environment,
    IntervalCI,
    ModelMeta,
    OwaspLLM,
    Scorecard,
    Severity,
    SuiteMeta,
    Totals,
)
from reagent.models import ChatParams as _ChatParams  # alias to keep imports tidy
from reagent.reporters import dump_json, load_json, render_html, render_markdown


def make_scorecard(*, is_redteam: bool = True) -> Scorecard:
    case = CaseResult(
        case_id="rt1",
        passed=False,
        defended=False,
        assertion_results=[
            AssertionResult(kind="regex", passed=True, detail="matched: 'PWNED'"),
        ],
        response_text="sure: PWNED",
        owasp=OwaspLLM.LLM01,
        severity=Severity.HIGH,
        prompt_tokens=10,
        completion_tokens=20,
        cost_usd=Decimal("0"),
    )
    totals = Totals(
        cases=1, passed=0, failed=1, skipped=0, errored=0,
        pass_rate=0.0,
        pass_rate_ci_95=IntervalCI(low=0.0, high=1.0),
        defense_rate=0.0,
        defense_rate_ci_95=IntervalCI(low=0.0, high=1.0),
        by_owasp=[
            ClassBreakdown(
                owasp=OwaspLLM.LLM01, cases=1, defended=0,
                defense_rate=0.0,
                defense_rate_ci_95=IntervalCI(low=0.0, high=1.0),
            )
        ],
        cost_usd=Decimal("0"), tokens_in=10, tokens_out=20,
        wall_clock_s=0.1, cache_hits=0, cache_misses=1,
    )
    return Scorecard(
        model=ModelMeta(provider="fake", name="m", params=_ChatParams()),
        suite=SuiteMeta(path=None, name="t", version=1, sha256="abc"),
        is_redteam=is_redteam,
        totals=totals,
        cases=[case],
        environment=Environment(
            reagent_version="0.0.0", python_version="3.11", platform="test"
        ),
    )


def test_json_roundtrip(tmp_path):
    sc = make_scorecard()
    path = tmp_path / "sc.json"
    dump_json(sc, path)
    loaded = load_json(path)
    assert loaded.run_id == sc.run_id
    assert loaded.totals.cases == sc.totals.cases
    assert loaded.cases[0].defended is False


def test_json_is_valid_json(tmp_path):
    text = dump_json(make_scorecard())
    parsed = json.loads(text)
    assert parsed["schema_version"]
    assert parsed["totals"]["defense_rate"] == 0.0


def test_markdown_renders_summary():
    md = render_markdown(make_scorecard())
    assert "Defense rate" in md
    assert "LLM01" in md
    assert "rt1" in md  # failed case row


def test_html_self_contained():
    html = render_html(make_scorecard())
    assert "<!doctype html>" in html.lower()
    # Scorecard JSON embedded for downstream tooling.
    assert "window.SCORECARD" in html
    assert "rt1" in html
    # No external <script src=…> assets.
    assert "src=\"http" not in html and "src='http" not in html


def test_html_quality_eval_summary():
    sc = make_scorecard(is_redteam=False)
    # Patch defense fields off to mimic a quality-eval scorecard.
    sc = sc.model_copy(update={"is_redteam": False})
    sc.totals.defense_rate = None
    sc.totals.defense_rate_ci_95 = None
    sc.totals.by_owasp = []
    html = render_html(sc)
    assert "Pass rate" in html
