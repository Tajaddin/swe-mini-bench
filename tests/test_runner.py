"""Runner tests with adversarial patches.

The patch runs in the same process as pytest, so the canaries catch only
tampering that changes every test's outcome alike; a patch written against
this harness can still forge a pass, pinned below as an expected failure.
No patch may crash the benchmark."""

from __future__ import annotations

import pytest

from swe_mini_bench import MockCompletion, ZeroShot, bench, load_issues, run_one
from swe_mini_bench.runner import report_to_dict

ISSUE = {i.id: i for i in load_issues()}["01_off_by_one_range"]
FIX = "def inclusive_range(start: int, end: int) -> list[int]:\n    return list(range(start, end + 1))\n"


def _run(patch_body: str, **kwargs):
    llm = MockCompletion(lambda prompt, system: f"```python\n{patch_body}```")
    return run_one(ISSUE, ZeroShot(), llm, **kwargs)


def test_correct_patch_passes_every_issue_test():
    result = _run(FIX)
    assert result.passed, result.pytest_stdout
    assert (result.tests_passed, result.tests_failed) == (3, 0)


def test_patch_that_disables_pytest_is_caught():
    hack = (
        "import _pytest.python\n"
        "_pytest.python.Function.runtest = lambda self: None\n\n"
        "def inclusive_range(start, end):\n"
        "    return None\n"
    )
    result = _run(hack)
    assert not result.passed
    assert result.error_kind == "tampered"


def test_patch_that_reports_failures_as_passes_is_caught():
    # Knows nothing about this harness: every failed report becomes a pass.
    hack = (
        "import _pytest.reports\n"
        "_init = _pytest.reports.TestReport.__init__\n"
        "def _forge(self, *args, **kwargs):\n"
        "    _init(self, *args, **kwargs)\n"
        "    if self.outcome == 'failed':\n"
        "        self.outcome, self.longrepr = 'passed', None\n"
        "_pytest.reports.TestReport.__init__ = _forge\n\n"
        "def inclusive_range(start, end):\n"
        "    return None\n"
    )
    result = _run(hack)
    assert not result.passed
    assert result.error_kind == "tampered"


@pytest.mark.xfail(
    strict=True,
    reason="known bypass: the patch runs in pytest's own process, so a patch that "
    "leaves the canaries alone can forge the verdict",
)
def test_patch_that_spares_the_canaries_cannot_forge_a_pass():
    hack = (
        "import _pytest.python\n"
        "_runtest = _pytest.python.Function.runtest\n"
        "def _skip_all_but_canaries(self):\n"
        "    if self.name.startswith('test_canary_'):\n"
        "        _runtest(self)\n"
        "_pytest.python.Function.runtest = _skip_all_but_canaries\n\n"
        "def inclusive_range(start, end):\n"
        "    return None\n"
    )
    result = _run(hack)
    assert not result.passed


def test_forged_summary_and_early_exit_is_not_a_pass():
    # Write a fake pytest summary to every open descriptor (one of them is the
    # real stdout pytest saved before capturing), then exit 0 before any test runs.
    hack = (
        "import os\n"
        "for fd in range(3, 32):\n"
        "    try:\n"
        "        os.write(fd, b'3 passed in 0.01s' + bytes([10]))\n"
        "    except OSError:\n"
        "        pass\n"
        "os._exit(0)\n"
    )
    result = _run(hack)
    assert not result.passed
    assert result.tests_passed == 0


def test_hanging_patch_times_out_instead_of_crashing():
    result = _run("while True:\n    pass\n", timeout_s=3)
    assert not result.passed
    assert result.error_kind == "timeout"


def test_patch_does_not_inherit_the_parent_environment(monkeypatch):
    monkeypatch.setenv("SWE_MINI_BENCH_TEST_SECRET", "must-not-leak")
    probe = "import os\nassert 'SWE_MINI_BENCH_TEST_SECRET' not in os.environ\n\n"
    result = _run(probe + FIX)
    assert result.passed, result.pytest_stdout + result.pytest_stderr


def test_prose_only_answer_is_no_code_block():
    llm = MockCompletion(lambda prompt, system: "Sorry, I can't produce a fix for this.")
    result = run_one(ISSUE, ZeroShot(), llm)
    assert not result.passed
    assert result.error_kind == "no_code_block"


def test_report_keeps_each_patch():
    report = bench([ISSUE], [ZeroShot()], MockCompletion(lambda p, s: f"```python\n{FIX}```"))
    (row,) = report_to_dict(report)["summaries"][0]["results"]
    assert row["passed"] is True
    assert row["patch"] == FIX
    assert row["sandbox"] in ("docker", "local")
