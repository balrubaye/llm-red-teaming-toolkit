"""Reagent command-line interface."""

from __future__ import annotations

import asyncio
import logging
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from reagent import __version__
from reagent.adapters import available_adapters
from reagent.models import OwaspLLM, Scorecard, Severity, Suite
from reagent.paths import bundled_corpus_dir
from reagent.reporters import dump_json, load_json, render_html, render_markdown
from reagent.runner import RunConfig, run_suite
from reagent.suites import SuiteLoadError, load_suite

# --- Exit codes (documented in spec §10). ---
EXIT_OK = 0
EXIT_CONFIG_ERROR = 1
EXIT_ASSERTIONS_FAILED = 10
EXIT_BUDGET_ABORTED = 11

_console = Console()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.DEBUG if verbose else logging.WARNING,
        stream=sys.stderr,
    )


def _parse_csv(values: tuple[str, ...] | None) -> list[str]:
    """Click's multiple=True flag may include comma-separated values."""
    out: list[str] = []
    for raw in values or ():
        out.extend(x.strip() for x in raw.split(",") if x.strip())
    return out


def _filter_suite(
    suite: Suite,
    *,
    owasp: list[str],
    severity: list[str],
    tag: list[str],
) -> Suite:
    """Return a new Suite restricted to cases matching the given filters."""
    owasp_set = {o.upper() for o in owasp}
    sev_set = {s.lower() for s in severity}
    tag_set = set(tag)

    def keep(case) -> bool:
        if owasp_set:
            c_class = case.owasp.value.split(":", 1)[0].upper() if case.owasp else ""
            if c_class not in owasp_set:
                return False
        if sev_set:
            if not case.severity or case.severity.value not in sev_set:
                return False
        if tag_set and not tag_set.intersection(case.tags):
            return False
        return True

    filtered = [c for c in suite.cases if keep(c)]
    return suite.model_copy(update={"cases": filtered})


def _write_outputs(scorecard: Scorecard, out_dir: Path, formats: list[str]) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    base = f"scorecard-{scorecard.run_id[:10]}"
    for fmt in formats:
        if fmt == "json":
            p = out_dir / f"{base}.json"
            dump_json(scorecard, p)
        elif fmt == "md":
            p = out_dir / f"{base}.md"
            render_markdown(scorecard, p)
        elif fmt == "html":
            p = out_dir / f"{base}.html"
            render_html(scorecard, p)
        else:
            raise click.BadParameter(f"unknown format {fmt!r}; expected json|md|html")
        written.append(p)
    return written


def _print_summary(scorecard: Scorecard) -> None:
    t = scorecard.totals
    table = Table(title=f"Run {scorecard.run_id[:10]}  ·  {scorecard.suite.name}", show_lines=False)
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Model", f"{scorecard.model.provider}:{scorecard.model.name}")
    table.add_row("Cases", str(t.cases))
    table.add_row("Passed / Failed / Errored / Skipped",
                  f"{t.passed} / {t.failed} / {t.errored} / {t.skipped}")
    table.add_row("Pass rate", f"{t.pass_rate * 100:.1f}%  "
                                f"(95% CI [{t.pass_rate_ci_95.low * 100:.1f}%, "
                                f"{t.pass_rate_ci_95.high * 100:.1f}%])")
    if scorecard.is_redteam and t.defense_rate is not None and t.defense_rate_ci_95 is not None:
        table.add_row("Defense rate", f"{t.defense_rate * 100:.1f}%  "
                                       f"(95% CI [{t.defense_rate_ci_95.low * 100:.1f}%, "
                                       f"{t.defense_rate_ci_95.high * 100:.1f}%])")
    table.add_row("Wall clock", f"{t.wall_clock_s:.1f}s")
    table.add_row("Tokens (in/out)", f"{t.tokens_in} / {t.tokens_out}")
    table.add_row("Cache (hits/misses)", f"{t.cache_hits} / {t.cache_misses}")
    if t.cost_usd:
        table.add_row("Cost", f"${t.cost_usd}")
    _console.print(table)

    if scorecard.is_redteam and t.by_owasp:
        bt = Table(title="Defense rate by OWASP class")
        bt.add_column("Class"); bt.add_column("Cases", justify="right")
        bt.add_column("Defended", justify="right"); bt.add_column("Defense rate", justify="right")
        for b in t.by_owasp:
            bt.add_row(
                b.owasp.value, str(b.cases), str(b.defended),
                f"{b.defense_rate * 100:.1f}%",
            )
        _console.print(bt)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="reagent")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """Reagent — open-source LLM evaluation and red-teaming toolkit."""
    _setup_logging(verbose)
    ctx.ensure_object(dict)


@main.command()
@click.argument("suite_path", type=click.Path(exists=True, path_type=Path))
@click.option("--model", required=True, help="e.g. ollama:llama3.1:8b")
@click.option("--concurrency", type=int, default=5, show_default=True,
              help="Max concurrent model calls.")
@click.option("--budget", type=str, default=None,
              help="Hard USD budget; aborts when exceeded (e.g. 5.00).")
@click.option("--no-cache", is_flag=True, help="Disable the response cache.")
@click.option("--out-dir", type=click.Path(path_type=Path), default=Path("reports"),
              show_default=True, help="Directory to write outputs to.")
@click.option("--format", "formats", multiple=True, default=("json", "md"),
              type=click.Choice(["json", "md", "html"]),
              help="Output formats (repeatable).")
@click.option("--judge-model", default=None,
              help="Default judge model for llm_judge assertions that don't pin one.")
def run(
    suite_path: Path,
    model: str,
    concurrency: int,
    budget: str | None,
    no_cache: bool,
    out_dir: Path,
    formats: tuple[str, ...],
    judge_model: str | None,
) -> None:
    """Run an eval or red-team suite."""
    _run_impl(
        suite_path=suite_path, model=model, concurrency=concurrency,
        budget=budget, no_cache=no_cache, out_dir=out_dir,
        formats=formats, judge_model=judge_model,
        filter_owasp=(), filter_severity=(), filter_tag=(),
        is_redteam_cmd=False,
    )


@main.command()
@click.option("--corpus", type=click.Path(path_type=Path), default=None,
              help="Override the bundled red-team corpus path.")
@click.option("--model", required=True, help="e.g. ollama:llama3.1:8b")
@click.option("--owasp", multiple=True,
              help="Filter by OWASP class (e.g. LLM01). Repeatable / comma-separated.")
@click.option("--severity", multiple=True,
              help="Filter by severity. Repeatable / comma-separated.")
@click.option("--tag", multiple=True, help="Filter by tag. Repeatable.")
@click.option("--concurrency", type=int, default=5, show_default=True)
@click.option("--budget", type=str, default=None)
@click.option("--no-cache", is_flag=True)
@click.option("--out-dir", type=click.Path(path_type=Path), default=Path("reports"),
              show_default=True)
@click.option("--format", "formats", multiple=True, default=("json", "md"),
              type=click.Choice(["json", "md", "html"]))
@click.option("--judge-model", default=None)
def redteam(
    corpus: Path | None,
    model: str,
    owasp: tuple[str, ...],
    severity: tuple[str, ...],
    tag: tuple[str, ...],
    concurrency: int,
    budget: str | None,
    no_cache: bool,
    out_dir: Path,
    formats: tuple[str, ...],
    judge_model: str | None,
) -> None:
    """Run the bundled red-team corpus against a model.

    Examples
    --------
    $ reagent redteam --model ollama:llama3.1:8b --owasp LLM01,LLM07
    """
    suite_path = corpus or bundled_corpus_dir()
    _run_impl(
        suite_path=suite_path, model=model, concurrency=concurrency,
        budget=budget, no_cache=no_cache, out_dir=out_dir,
        formats=formats, judge_model=judge_model,
        filter_owasp=owasp, filter_severity=severity, filter_tag=tag,
        is_redteam_cmd=True,
    )


def _run_impl(
    *,
    suite_path: Path,
    model: str,
    concurrency: int,
    budget: str | None,
    no_cache: bool,
    out_dir: Path,
    formats: tuple[str, ...],
    judge_model: str | None,
    filter_owasp: tuple[str, ...],
    filter_severity: tuple[str, ...],
    filter_tag: tuple[str, ...],
    is_redteam_cmd: bool,
) -> None:
    try:
        suite = load_suite(suite_path)
    except SuiteLoadError as exc:
        _console.print(f"[red]suite load failed:[/red] {exc}")
        sys.exit(EXIT_CONFIG_ERROR)

    if filter_owasp or filter_severity or filter_tag:
        suite = _filter_suite(
            suite,
            owasp=_parse_csv(filter_owasp),
            severity=_parse_csv(filter_severity),
            tag=_parse_csv(filter_tag),
        )
        if not suite.cases:
            _console.print("[red]no cases matched the provided filters[/red]")
            sys.exit(EXIT_CONFIG_ERROR)

    if is_redteam_cmd and not suite.is_redteam():
        _console.print(
            "[yellow]warning:[/yellow] no OWASP-tagged cases in this suite; "
            "running but defense_rate will not be reported"
        )

    budget_dec: Decimal | None = None
    if budget is not None:
        try:
            budget_dec = Decimal(budget)
        except InvalidOperation:
            _console.print(f"[red]invalid --budget value: {budget!r}[/red]")
            sys.exit(EXIT_CONFIG_ERROR)

    # Validate the model adapter exists before doing work.
    from reagent.adapters import resolve_adapter
    try:
        adapter = resolve_adapter(model)
    except ValueError as exc:
        _console.print(f"[red]{exc}[/red]")
        sys.exit(EXIT_CONFIG_ERROR)

    # We resolved one to validate; close it. The runner constructs its own.
    asyncio.run(adapter.aclose())

    config = RunConfig(
        model=model,
        concurrency=concurrency,
        use_cache=not no_cache,
        budget_usd=budget_dec,
        default_judge_model=judge_model,
    )

    _console.print(
        f"Running [bold]{suite.name}[/bold] ({len(suite.cases)} cases) "
        f"against [bold]{model}[/bold]…"
    )

    result = asyncio.run(run_suite(suite, config))
    _print_summary(result.scorecard)

    written = _write_outputs(result.scorecard, out_dir, list(formats))
    for p in written:
        _console.print(f"wrote [cyan]{p}[/cyan]")

    if result.aborted_on_budget:
        _console.print("[yellow]run aborted on budget[/yellow]")
        sys.exit(EXIT_BUDGET_ABORTED)

    t = result.scorecard.totals
    if t.failed > 0 or t.errored > 0:
        sys.exit(EXIT_ASSERTIONS_FAILED)
    sys.exit(EXIT_OK)


@main.command()
@click.argument("scorecard_path", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "fmt", type=click.Choice(["md", "html"]), default="html",
              show_default=True)
@click.option("--out", type=click.Path(path_type=Path), default=None,
              help="Output file. Defaults to <scorecard>.<ext>.")
def report(scorecard_path: Path, fmt: str, out: Path | None) -> None:
    """Render a scorecard JSON to Markdown or HTML."""
    try:
        scorecard = load_json(scorecard_path)
    except Exception as exc:
        _console.print(f"[red]could not load scorecard:[/red] {exc}")
        sys.exit(EXIT_CONFIG_ERROR)

    target = out or scorecard_path.with_suffix(f".{fmt}")
    if fmt == "md":
        render_markdown(scorecard, target)
    else:
        render_html(scorecard, target)
    _console.print(f"wrote [cyan]{target}[/cyan]")


@main.group()
def suites() -> None:
    """Suite-management commands."""


@suites.command("validate")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def validate_suite(path: Path) -> None:
    """Load a suite and report any schema errors."""
    try:
        suite = load_suite(path)
    except SuiteLoadError as exc:
        _console.print(f"[red]invalid:[/red] {exc}")
        sys.exit(EXIT_CONFIG_ERROR)
    _console.print(
        f"[green]ok[/green]: {suite.name} ({len(suite.cases)} cases, "
        f"sha256={suite.content_sha256[:12] if suite.content_sha256 else '—'})"
    )


@main.group()
def providers() -> None:
    """Inspect registered model providers."""


@providers.command("list")
def providers_list() -> None:
    """List registered model adapters."""
    names = available_adapters()
    if not names:
        _console.print("[yellow]no adapters registered[/yellow]")
        return
    for name in names:
        _console.print(f"- {name}")


@main.command()
def taxonomy() -> None:
    """Print the OWASP / Severity / AttackClass values Reagent recognizes."""
    table = Table(title="OWASP LLM Top 10 (prompt-testable)")
    table.add_column("Code"); table.add_column("Class")
    for o in OwaspLLM:
        code, name = o.value.split(":", 1)
        table.add_row(code, name)
    _console.print(table)

    sev = Table(title="Severity")
    sev.add_column("Value")
    for s in Severity:
        sev.add_row(s.value)
    _console.print(sev)


if __name__ == "__main__":  # pragma: no cover
    main()
