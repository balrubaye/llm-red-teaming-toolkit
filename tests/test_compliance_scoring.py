from decimal import Decimal
from reagent.models import CaseResult, Severity, OwaspLLM
from reagent.runner.scoring import assemble_totals


def test_compliance_scoring_aggregates_properly():
    # Setup results with various compliance tags
    results = [
        CaseResult(
            case_id="case1",
            passed=True,
            defended=True,
            owasp=OwaspLLM.LLM01,
            severity=Severity.HIGH,
            atlas=["AML.T0051.001", "AML.T0058"],
            nist_ai_rmf=["MEASURE-2.4"],
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=Decimal("0"),
        ),
        CaseResult(
            case_id="case2",
            passed=False,
            defended=False,
            owasp=OwaspLLM.LLM01,
            severity=Severity.MEDIUM,
            atlas=["AML.T0051.001", "UNKNOWN.ATLAS.TAG"],
            nist_ai_rmf=["MEASURE-2.4", "GOVERN"],
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=Decimal("0"),
        ),
    ]

    totals = assemble_totals(
        results,
        is_redteam=True,
        wall_clock_s=1.0,
        cache_hits=0,
        cache_misses=2,
    )

    # 1. Total checks
    assert totals.cases == 2
    assert totals.passed == 1
    assert totals.failed == 1

    # 2. ATLAS checks
    # Sort order of tags: AML.T0051.001, AML.T0058, UNKNOWN.ATLAS.TAG
    assert len(totals.by_atlas) == 3
    
    # AML.T0051.001 should have 2 cases, 1 defended
    assert totals.by_atlas[0].id == "AML.T0051.001"
    assert totals.by_atlas[0].name == "Indirect Prompt Injection"
    assert totals.by_atlas[0].cases == 2
    assert totals.by_atlas[0].defended == 1
    assert totals.by_atlas[0].defense_rate == 0.5

    # AML.T0058 should have 1 case, 1 defended
    assert totals.by_atlas[1].id == "AML.T0058"
    assert totals.by_atlas[1].name == "Adversarial Fuzzing"
    assert totals.by_atlas[1].cases == 1
    assert totals.by_atlas[1].defended == 1
    assert totals.by_atlas[1].defense_rate == 1.0

    # UNKNOWN.ATLAS.TAG should fall back gracefully
    assert totals.by_atlas[2].id == "UNKNOWN.ATLAS.TAG"
    assert totals.by_atlas[2].name == "Unknown Technique"
    assert totals.by_atlas[2].cases == 1
    assert totals.by_atlas[2].defended == 0
    assert totals.by_atlas[2].defense_rate == 0.0

    # 3. NIST checks
    # Sort order of tags: GOVERN, MEASURE-2.4
    assert len(totals.by_nist) == 2

    # GOVERN should have 1 case, 0 defended
    assert totals.by_nist[0].id == "GOVERN"
    assert totals.by_nist[0].name == "Govern Function"
    assert totals.by_nist[0].cases == 1
    assert totals.by_nist[0].defended == 0
    assert totals.by_nist[0].defense_rate == 0.0

    # MEASURE-2.4 should have 2 cases, 1 defended
    assert totals.by_nist[1].id == "MEASURE-2.4"
    assert totals.by_nist[1].name == "Vulnerability & Robustness Auditing"
    assert totals.by_nist[1].cases == 2
    assert totals.by_nist[1].defended == 1
    assert totals.by_nist[1].defense_rate == 0.5
