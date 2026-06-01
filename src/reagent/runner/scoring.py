"""Assemble :class:`Totals` from a list of :class:`CaseResult`s."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from reagent.models import CaseResult, ClassBreakdown, OwaspLLM, Totals
from reagent.stats import proportion, wilson_interval


def assemble_totals(
    results: list[CaseResult],
    *,
    is_redteam: bool,
    wall_clock_s: float,
    cache_hits: int,
    cache_misses: int,
) -> Totals:
    cases = len(results)
    passed = sum(1 for r in results if r.passed and not r.skipped)
    failed = sum(1 for r in results if (not r.passed) and not r.skipped and r.error is None)
    skipped = sum(1 for r in results if r.skipped)
    errored = sum(1 for r in results if r.error is not None and not r.skipped)

    pass_rate = proportion(passed, cases - skipped)
    pass_ci = wilson_interval(passed, cases - skipped) if (cases - skipped) > 0 else wilson_interval(0, 0)

    cost = sum((r.cost_usd for r in results), Decimal("0"))
    tokens_in = sum(r.prompt_tokens for r in results)
    tokens_out = sum(r.completion_tokens for r in results)

    defense_rate: float | None = None
    defense_ci = None
    by_owasp: list[ClassBreakdown] = []

    if is_redteam:
        # `defended` is True/False on red-team cases (None on others). We
        # restrict aggregates to cases that actually carry the field.
        rt = [r for r in results if r.defended is not None and not r.skipped]
        defended_count = sum(1 for r in rt if r.defended)
        defense_rate = proportion(defended_count, len(rt))
        defense_ci = wilson_interval(defended_count, len(rt))

        buckets: dict[OwaspLLM, list[CaseResult]] = defaultdict(list)
        for r in rt:
            if r.owasp is not None:
                buckets[r.owasp].append(r)

        for owasp in sorted(buckets, key=lambda x: x.value):
            bucket = buckets[owasp]
            defended_in_bucket = sum(1 for r in bucket if r.defended)
            by_owasp.append(
                ClassBreakdown(
                    owasp=owasp,
                    cases=len(bucket),
                    defended=defended_in_bucket,
                    defense_rate=proportion(defended_in_bucket, len(bucket)),
                    defense_rate_ci_95=wilson_interval(defended_in_bucket, len(bucket)),
                )
            )

    return Totals(
        cases=cases,
        passed=passed,
        failed=failed,
        skipped=skipped,
        errored=errored,
        pass_rate=pass_rate,
        pass_rate_ci_95=pass_ci,
        defense_rate=defense_rate,
        defense_rate_ci_95=defense_ci,
        by_owasp=by_owasp,
        cost_usd=cost,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        wall_clock_s=wall_clock_s,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
    )


__all__ = ["assemble_totals"]
