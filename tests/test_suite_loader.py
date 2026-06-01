"""Suite-loader tests."""

from __future__ import annotations

import pytest

from reagent.suites import SuiteLoadError, load_suite


def write(p, content: str):
    p.write_text(content, encoding="utf-8")
    return p


def test_load_suite_file(tmp_path):
    suite_yaml = """
name: smoke
description: minimal
cases:
  - id: a
    input: hello
    assert:
      - regex:
          pattern: "."
"""
    f = write(tmp_path / "smoke.yaml", suite_yaml)
    s = load_suite(f)
    assert s.name == "smoke"
    assert len(s.cases) == 1
    assert s.content_sha256 is not None and len(s.content_sha256) == 64


def test_load_single_case_file_wraps_in_synthetic_suite(tmp_path):
    case_yaml = """
id: my-case
input: hello
owasp: "LLM01:PromptInjection"
attack_class: instruction-override
severity: high
attack_succeeded_means: model_failed
assert:
  - regex:
      pattern: foo
"""
    f = write(tmp_path / "my-case.yaml", case_yaml)
    s = load_suite(f)
    assert s.name == "my-case"
    assert s.is_redteam() is True


def test_load_directory_aggregates_cases(tmp_path):
    write(tmp_path / "a.yaml", "id: a\ninput: x\nassert: []\n")
    write(tmp_path / "b.yaml", "id: b\ninput: y\nassert: []\n")
    s = load_suite(tmp_path)
    assert sorted(c.id for c in s.cases) == ["a", "b"]
    assert s.content_sha256 is not None  # combined hash present


def test_directory_rejects_suite_file(tmp_path):
    write(
        tmp_path / "looks-like-suite.yaml",
        "name: nope\ncases:\n  - id: a\n    input: x\n    assert: []\n",
    )
    with pytest.raises(SuiteLoadError, match="case files"):
        load_suite(tmp_path)


def test_invalid_yaml_raises(tmp_path):
    write(tmp_path / "broken.yaml", "id: a\n  : bad indent\n")
    with pytest.raises(SuiteLoadError):
        load_suite(tmp_path / "broken.yaml")


def test_unrecognized_shape_raises(tmp_path):
    write(tmp_path / "noidea.yaml", "foo: bar\n")
    with pytest.raises(SuiteLoadError, match="unrecognized"):
        load_suite(tmp_path / "noidea.yaml")


def test_missing_path_raises(tmp_path):
    with pytest.raises(SuiteLoadError, match="does not exist"):
        load_suite(tmp_path / "absent.yaml")


def test_duplicate_case_ids_raise(tmp_path):
    write(
        tmp_path / "dup.yaml",
        """
name: dup
cases:
  - id: a
    input: x
    assert: []
  - id: a
    input: y
    assert: []
""",
    )
    with pytest.raises(SuiteLoadError, match="duplicate"):
        load_suite(tmp_path / "dup.yaml")


def test_input_xor_messages_required(tmp_path):
    write(tmp_path / "nope.yaml", "id: a\nassert: []\n")
    with pytest.raises(SuiteLoadError):
        load_suite(tmp_path / "nope.yaml")
