"""Patch executor + benchmark loop.

``run_one`` asks a strategy for a patch, runs the issue's tests against it in a
separate process (a network-less container when available, see
:mod:`swe_mini_bench.sandbox`), and decides the verdict here, in the parent,
from the per-test JUnit report. ``bench`` runs every strategy over every issue
and returns aggregated pass@1.

Every test the parent finds in the trusted test source must be reported as
passed, and two canary tests must keep their outcome: a plain failing test must
be reported failed and a strict xfail test xfailed. That catches a patch that
changes every test's outcome alike, such as disabling test execution or
rewriting failures as passes.

It does not make the verdict tamper-proof. The patch's code runs in the same
interpreter as the tests that call it, and that process writes the JUnit
report, so a patch written against this harness (one that leaves the canaries
alone, say) can still forge a pass.
"""

from __future__ import annotations

import ast
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Iterable

from swe_mini_bench.issues import Issue
from swe_mini_bench.sandbox import execute
from swe_mini_bench.strategies import AgentStrategy, Completion


@dataclass
class PatchResult:
    """Outcome of running one (strategy, issue) pair."""

    strategy: str
    issue_id: str
    passed: bool
    patch: str
    pytest_stdout: str
    pytest_stderr: str
    pytest_exitcode: int | None  # None when the run was killed at the timeout
    tests_passed: int = 0
    tests_failed: int = 0
    # syntax_error, import_error, test_failure, no_code_block, timeout, tampered
    error_kind: str | None = None
    sandbox: str = ""


_CANARY_SOURCE = """\
import pytest


def {name}_fail():
    assert False, "canary: must be reported as failed"


@pytest.mark.xfail(strict=True)
def {name}_xfail():
    assert False
"""


def _expected_tests(test_code: str) -> list[str]:
    """Top-level test functions in the issue's test file, read without running it."""
    return [
        node.name
        for node in ast.parse(test_code).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")
    ]


def _junit_outcomes(junit_xml: str | None) -> dict[tuple[str, str], str]:
    """Map (classname, name) to passed / failed / error / skipped / xfailed."""
    if not junit_xml:
        return {}
    try:
        root = ET.fromstring(junit_xml)
    except ET.ParseError:
        return {}
    outcomes: dict[tuple[str, str], str] = {}
    for case in root.iter("testcase"):
        tags = {child.tag: child for child in case}
        if "failure" in tags:
            outcome = "failed"
        elif "error" in tags:
            outcome = "error"
        elif "skipped" in tags:
            outcome = "xfailed" if tags["skipped"].get("type") == "pytest.xfail" else "skipped"
        else:
            outcome = "passed"
        outcomes[(case.get("classname", ""), case.get("name", ""))] = outcome
    return outcomes


def run_one(
    issue: Issue,
    strategy: AgentStrategy,
    llm: Completion,
    *,
    pytest_args: Iterable[str] = (),
    sandbox: str = "auto",
    timeout_s: float = 60,
) -> PatchResult:
    """Run ``strategy`` against ``issue``, return the verdict."""
    patch = strategy.solve(issue, llm)
    expected = _expected_tests(issue.test_code)

    if not patch.strip():
        return PatchResult(
            strategy=strategy.name,
            issue_id=issue.id,
            passed=False,
            patch=patch,
            pytest_stdout="",
            pytest_stderr="",
            pytest_exitcode=None,
            tests_failed=len(expected),
            error_kind="no_code_block",
        )

    canary = f"test_canary_{uuid.uuid4().hex}"
    run = execute(
        {
            f"{issue.module_name}.py": patch,
            f"{issue.test_module_name}.py": issue.test_code,
            f"{canary}.py": _CANARY_SOURCE.format(name=canary),
            # Stops pytest from picking up config or conftest files above the run directory.
            "pytest.ini": "[pytest]\n",
        },
        sandbox=sandbox,
        timeout_s=timeout_s,
        pytest_args=pytest_args,
    )

    outcomes = _junit_outcomes(run.junit_xml)
    n_passed = sum(outcomes.get((issue.test_module_name, t)) == "passed" for t in expected)
    canaries = (
        outcomes.get((canary, f"{canary}_fail")),
        outcomes.get((canary, f"{canary}_xfail")),
    )
    canaries_held = canaries == ("failed", "xfailed")
    passed = (
        not run.timed_out
        and bool(expected)
        and n_passed == len(expected)
        and canaries_held
    )

    output = run.stdout + run.stderr
    if passed:
        error_kind = None
    elif run.timed_out:
        error_kind = "timeout"
    elif "SyntaxError" in output:
        error_kind = "syntax_error"
    elif "ImportError" in output:
        error_kind = "import_error"
    elif canaries != (None, None) and not canaries_held:
        error_kind = "tampered"
    else:
        error_kind = "test_failure"

    return PatchResult(
        strategy=strategy.name,
        issue_id=issue.id,
        passed=passed,
        patch=patch,
        pytest_stdout=run.stdout,
        pytest_stderr=run.stderr,
        pytest_exitcode=run.exitcode,
        tests_passed=n_passed,
        tests_failed=len(expected) - n_passed,
        error_kind=error_kind,
        sandbox=run.sandbox,
    )


@dataclass
class StrategySummary:
    strategy: str
    pass_rate: float
    pass_count: int
    n: int
    results: list[PatchResult] = field(default_factory=list)


def run_strategy(
    issues: list[Issue],
    strategy: AgentStrategy,
    llm: Completion,
    *,
    sandbox: str = "auto",
) -> StrategySummary:
    results: list[PatchResult] = []
    n_pass = 0
    for issue in issues:
        result = run_one(issue, strategy, llm, sandbox=sandbox)
        results.append(result)
        if result.passed:
            n_pass += 1
    return StrategySummary(
        strategy=strategy.name,
        pass_rate=round(n_pass / max(len(issues), 1), 4),
        pass_count=n_pass,
        n=len(issues),
        results=results,
    )


@dataclass
class BenchReport:
    """Full benchmark output across all strategies."""

    model: str
    summaries: list[StrategySummary]
    issue_ids: list[str]


def bench(
    issues: list[Issue],
    strategies: list[AgentStrategy],
    llm: Completion,
    *,
    sandbox: str = "auto",
) -> BenchReport:
    summaries: list[StrategySummary] = []
    for strategy in strategies:
        summaries.append(run_strategy(issues, strategy, llm, sandbox=sandbox))
    return BenchReport(
        model=llm.model,
        summaries=summaries,
        issue_ids=[i.id for i in issues],
    )


def report_to_dict(report: BenchReport) -> dict:
    return {
        "model": report.model,
        "issue_ids": report.issue_ids,
        "summaries": [
            {
                "strategy": s.strategy,
                "pass_rate": s.pass_rate,
                "pass_count": s.pass_count,
                "n": s.n,
                "results": [
                    {
                        "issue_id": r.issue_id,
                        "passed": r.passed,
                        "tests_passed": r.tests_passed,
                        "tests_failed": r.tests_failed,
                        "error_kind": r.error_kind,
                        "sandbox": r.sandbox,
                        "patch": r.patch,
                    }
                    for r in s.results
                ],
            }
            for s in report.summaries
        ],
    }
