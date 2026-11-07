"""``swe-mini-bench`` CLI."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from swe_mini_bench.issues import load_issues
from swe_mini_bench.runner import bench, report_to_dict
from swe_mini_bench.strategies import (
    AnthropicCompletion,
    ScratchpadCritique,
    Scratchpad,
    ZeroShot,
)


@click.group()
def cli():
    """swe-mini-bench commands."""


@cli.command(name="list")
def list_issues_cmd():
    """List all built-in issue fixtures."""
    for i in load_issues():
        click.echo(f"{i.id}\t{i.title}")


@cli.command()
@click.option(
    "--model",
    default=None,
    help="Anthropic model (defaults to claude-haiku-4-5-20251001).",
)
@click.option("--out", default="bench/results.json", help="Output JSON path.")
@click.option(
    "--strategy",
    multiple=True,
    type=click.Choice(["zero_shot", "scratchpad", "scratchpad_critique"]),
    default=("zero_shot", "scratchpad", "scratchpad_critique"),
)
@click.option(
    "--sandbox",
    type=click.Choice(["auto", "docker", "local"]),
    default="auto",
    help="Where patches run: docker (no network), local, or auto (docker once the image is built).",
)
def run(model, out, strategy, sandbox):
    """Run the full benchmark with Anthropic Haiku 4.5."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo("ANTHROPIC_API_KEY not set", err=True)
        sys.exit(2)

    llm = AnthropicCompletion(model=model)
    issues = load_issues()
    strategy_map = {
        "zero_shot": ZeroShot(),
        "scratchpad": Scratchpad(),
        "scratchpad_critique": ScratchpadCritique(),
    }
    strategies = [strategy_map[s] for s in strategy]
    click.echo(
        f"Running {len(strategies)} strategies × {len(issues)} issues on {llm.model}..."
    )
    report = bench(issues, strategies, llm, sandbox=sandbox)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report_to_dict(report), indent=2), encoding="utf-8")
    click.echo(f"\nResults written to {out_path}\n")
    for s in report.summaries:
        click.echo(
            f"  {s.strategy:24s} pass@1 = {s.pass_count}/{s.n} ({s.pass_rate * 100:.1f}%)"
        )


if __name__ == "__main__":
    cli()
