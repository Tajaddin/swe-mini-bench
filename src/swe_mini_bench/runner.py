"""Patch executor + benchmark loop.

``run_one`` writes the agent's patch to a scratch tempdir, drops the test
file next to it, runs pytest, and parses the output. ``bench`` runs every
strategy over every issue and returns aggregated pass@1.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from swe_mini_bench.issues import Issue
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
    pytest_exitcode: int
    tests_passed: int = 0
    tests_failed: int = 0
    error_kind: str | None = None  # syntax_error, no_code_block, test_failure, ok


_PASSED_RE = re.compile(r"(\d+)\s+passed")
_FAILED_RE = re.compile(r"(\d+)\s+failed")


def _parse_pytest_summary(stdout: str) -> tuple[int, int]:
    """Parse the trailing 'N passed, M failed in ...s' line.

    Works for both ``-q`` ("3 passed in 0.02s") and the default banner format
    ("===== 3 passed in 0.02s =====").
    """
    passed = failed = 0
    for line in stdout.splitlines():
        stripped = line.strip().strip("=").strip()
        if "in " not in stripped or "passed" not in stripped and "failed" not in stripped:
            continue
        if "passed" in stripped or "failed" in stripped:
            p = _PASSED_RE.search(stripped)
            f = _FAILED_RE.search(stripped)
            if p:
                passed = int(p.group(1))
            if f:
                failed = int(f.group(1))
    return passed, failed


def _classify_error(patch: str, exitcode: int, stdout: str, stderr: str) -> str | None:
    if exitcode == 0:
        return None
    if "SyntaxError" in stderr or "SyntaxError" in stdout:
        return "syntax_error"
    if "ImportError" in stderr or "ImportError" in stdout:
        return "import_error"
    if not patch.strip():
        return "no_code_block"
    return "test_failure"


def run_one(
    issue: Issue,
    strategy: AgentStrategy,
    llm: Completion,
    *,
    pytest_args: Iterable[str] = (),
) -> PatchResult:
    """Run ``strategy`` against ``issue``, return the verdict."""
    patch = strategy.solve(issue, llm)

    with tempfile.TemporaryDirectory(prefix=f"swe_{issue.id}_") as td:
        sandbox = Path(td)
        (sandbox / f"{issue.module_name}.py").write_text(patch, encoding="utf-8")
        (sandbox / f"{issue.test_module_name}.py").write_text(
            issue.test_code, encoding="utf-8"
        )
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--tb=short",
                *pytest_args,
                str(sandbox),
            ],
            cwd=sandbox,
            capture_output=True,
            text=True,
            timeout=60,
        )
        passed_n, failed_n = _parse_pytest_summary(proc.stdout)
        err_kind = _classify_error(patch, proc.returncode, proc.stdout, proc.stderr)
        return PatchResult(
            strategy=strategy.name,
            issue_id=issue.id,
            passed=(proc.returncode == 0 and failed_n == 0 and passed_n > 0),
            patch=patch,
            pytest_stdout=proc.stdout,
            pytest_stderr=proc.stderr,
            pytest_exitcode=proc.returncode,
            tests_passed=passed_n,
            tests_failed=failed_n,
            error_kind=err_kind,
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
) -> StrategySummary:
    results: list[PatchResult] = []
    n_pass = 0
    for issue in issues:
        result = run_one(issue, strategy, llm)
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
) -> BenchReport:
    summaries: list[StrategySummary] = []
    for strategy in strategies:
        summaries.append(run_strategy(issues, strategy, llm))
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
                    }
                    for r in s.results
                ],
            }
            for s in report.summaries
        ],
    }
