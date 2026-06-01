"""Markdown reporter — designed for PR comments and CI logs."""

from __future__ import annotations

from pathlib import Path

from reagent.models import CaseResult, IntervalCI, Scorecard


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _fmt_ci(ci: IntervalCI) -> str:
    return f"[{_fmt_pct(ci.low)}, {_fmt_pct(ci.high)}]"


def _summary_line(scorecard: Scorecard) -> str:
    t = scorecard.totals
    if scorecard.is_redteam and t.defense_rate is not None and t.defense_rate_ci_95 is not None:
        return (
            f"**Defense rate: {_fmt_pct(t.defense_rate)}** "
            f"({t.cases - t.skipped} cases, 95% CI {_fmt_ci(t.defense_rate_ci_95)})"
        )
    return (
        f"**Pass rate: {_fmt_pct(t.pass_rate)}** "
        f"({t.passed}/{t.cases - t.skipped} cases, 95% CI {_fmt_ci(t.pass_rate_ci_95)})"
    )


def _truncate(text: str | None, limit: int = 280) -> str:
    if not text:
        return ""
    text = text.strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _failed_cases_table(cases: list[CaseResult], limit: int = 20) -> str:
    failed = [c for c in cases if not c.passed and not c.skipped]
    if not failed:
        return "_All cases passed._\n"

    lines = [
        f"### Failures ({len(failed)} total" + (f", showing first {limit})" if len(failed) > limit else ")"),
        "",
        "| Case | OWASP | Severity | Reason |",
        "|------|-------|----------|--------|",
    ]
    for c in failed[:limit]:
        owasp = c.owasp.value if c.owasp else "—"
        sev = c.severity.value if c.severity else "—"
        if c.error:
            reason = f"error: {c.error}"
        else:
            # Highlight the first failing assertion.
            failing = next((a for a in c.assertion_results if not a.passed), None)
            if failing is not None:
                reason = f"`{failing.kind}` failed — {failing.detail or failing.error or ''}"
            else:
                reason = "—"
        lines.append(f"| `{c.case_id}` | {owasp} | {sev} | {_truncate(reason, 160)} |")
    lines.append("")
    return "\n".join(lines)


def _owasp_table(scorecard: Scorecard) -> str:
    if not scorecard.totals.by_owasp:
        return ""
    lines = [
        "### Defense rate by OWASP class",
        "",
        "| Class | Cases | Defended | Defense rate | 95% CI |",
        "|-------|-------|----------|--------------|--------|",
    ]
    for b in scorecard.totals.by_owasp:
        lines.append(
            f"| {b.owasp.value} | {b.cases} | {b.defended} | "
            f"{_fmt_pct(b.defense_rate)} | {_fmt_ci(b.defense_rate_ci_95)} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_markdown(scorecard: Scorecard, path: str | Path | None = None) -> str:
    t = scorecard.totals
    parts: list[str] = []

    title = "🧪 Reagent red-team scorecard" if scorecard.is_redteam else "🧪 Reagent scorecard"
    parts.append(f"# {title}")
    parts.append("")
    parts.append(f"- **Model**: `{scorecard.model.provider}:{scorecard.model.name}`")
    parts.append(f"- **Suite**: `{scorecard.suite.name}` (v{scorecard.suite.version})")
    if scorecard.judge:
        parts.append(f"- **Judge**: `{scorecard.judge.model}`")
    parts.append(f"- **Run ID**: `{scorecard.run_id}`")
    parts.append("")
    parts.append(_summary_line(scorecard))
    parts.append("")

    parts.append("## Aggregate")
    parts.append("")
    parts.append(
        f"- Cases: {t.cases} (passed: {t.passed}, failed: {t.failed}, "
        f"errored: {t.errored}, skipped: {t.skipped})"
    )
    parts.append(f"- Wall clock: {t.wall_clock_s:.1f}s · Tokens in/out: {t.tokens_in}/{t.tokens_out}")
    parts.append(f"- Cache hits: {t.cache_hits} · misses: {t.cache_misses}")
    if t.cost_usd:
        parts.append(f"- Cost: ${t.cost_usd}")
    parts.append("")

    if scorecard.is_redteam:
        parts.append(_owasp_table(scorecard))

    parts.append(_failed_cases_table(scorecard.cases))

    text = "\n".join(parts)
    if path is not None:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return text


__all__ = ["render_markdown"]
