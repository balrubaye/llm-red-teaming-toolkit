"""Smoke-test: every bundled red-team template must load cleanly and have
required taxonomy fields."""

from __future__ import annotations

from reagent.paths import bundled_corpus_dir
from reagent.suites import load_suite


def test_bundled_corpus_loads():
    suite = load_suite(bundled_corpus_dir())
    assert suite.is_redteam(), "bundled corpus must contain OWASP-tagged cases"
    # Every case carries taxonomy and at least one assertion.
    for case in suite.cases:
        assert case.owasp is not None, f"case {case.id} missing owasp"
        assert case.attack_class is not None, f"case {case.id} missing attack_class"
        assert case.severity is not None, f"case {case.id} missing severity"
        assert case.assertions, f"case {case.id} has no assertions"


def test_bundled_corpus_size_matches_readme():
    suite = load_suite(bundled_corpus_dir())
    # The README declared 20 templates at v0.1.
    assert len(suite.cases) >= 20, f"unexpected corpus size: {len(suite.cases)}"


def test_bundled_corpus_owasp_coverage():
    suite = load_suite(bundled_corpus_dir())
    seen = {c.owasp.value.split(":", 1)[0] for c in suite.cases if c.owasp}
    expected_minimum = {"LLM01", "LLM02", "LLM05", "LLM06", "LLM07", "LLM09", "LLM03", "LLM10"}
    assert expected_minimum.issubset(seen), f"OWASP coverage drift: missing={expected_minimum - seen}"
