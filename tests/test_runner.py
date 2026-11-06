"""Runner tests with adversarial patches: the verdict must not be forgeable
by the patch's own process, and no patch may crash the benchmark."""

from __future__ import annotations

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
