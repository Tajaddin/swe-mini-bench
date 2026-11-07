"""Unit tests for strategies, the extractor, and the runner with a mock LLM."""

from __future__ import annotations

import re

from swe_mini_bench import (
    MockCompletion,
    ScratchpadCritique,
    Scratchpad,
    ZeroShot,
    load_issues,
    run_one,
)
from swe_mini_bench.strategies import extract_python_block


def test_extract_python_block_with_fence():
    text = "Reasoning here.\n\n```python\nprint('hi')\n```\nTrailing"
    assert extract_python_block(text).strip() == "print('hi')"


def test_extract_python_block_without_fence():
    # Models that forget the fence should still get their text through.
    text = "print('hi')\n"
    assert extract_python_block(text).strip() == "print('hi')"


def test_zero_shot_uses_canonical_fix_passes():
    issues = {i.id: i for i in load_issues()}
    issue = issues["01_off_by_one_range"]
    fixed = (
        "```python\n"
        "def inclusive_range(start: int, end: int) -> list[int]:\n"
        "    return list(range(start, end + 1))\n"
        "```"
    )
    llm = MockCompletion(lambda prompt, system: fixed)
    result = run_one(issue, ZeroShot(), llm)
    assert result.passed, result.pytest_stdout


def test_scratchpad_handles_reasoning_prefix():
    issues = {i.id: i for i in load_issues()}
    issue = issues["02_mutable_default"]
    fixed = (
        "Step 1: identify the mutable default.\n"
        "Step 2: replace with None sentinel.\n\n"
        "```python\n"
        "def add_item(item, bucket=None):\n"
        "    if bucket is None:\n"
        "        bucket = []\n"
        "    bucket.append(item)\n"
        "    return bucket\n"
        "```"
    )
    llm = MockCompletion(lambda prompt, system: fixed)
    result = run_one(issue, Scratchpad(), llm)
    assert result.passed, result.pytest_stdout


def test_scratchpad_critique_does_two_calls_and_uses_second():
    """First call gives a wrong patch; the critique pass corrects it."""
    issues = {i.id: i for i in load_issues()}
    issue = issues["01_off_by_one_range"]
    wrong = (
        "```python\n"
        "def inclusive_range(start, end):\n"
        "    return list(range(start, end))   # still wrong\n"
        "```"
    )
    correct = (
        "```python\n"
        "def inclusive_range(start, end):\n"
        "    return list(range(start, end + 1))\n"
        "```"
    )

    calls = {"n": 0}

    def responder(prompt, system):
        calls["n"] += 1
        return wrong if calls["n"] == 1 else correct

    llm = MockCompletion(responder)
    result = run_one(issue, ScratchpadCritique(), llm)
    assert calls["n"] == 2
    assert result.passed, result.pytest_stdout


def test_runner_marks_failed_patch():
    issues = {i.id: i for i in load_issues()}
    issue = issues["01_off_by_one_range"]
    no_op = (
        "```python\n" + issue.buggy_code + "```"
    )
    llm = MockCompletion(lambda prompt, system: no_op)
    result = run_one(issue, ZeroShot(), llm)
    assert not result.passed
    assert result.error_kind == "test_failure"


def test_runner_marks_syntax_error():
    issues = {i.id: i for i in load_issues()}
    issue = issues["01_off_by_one_range"]
    broken = "```python\nthis is not valid python (syntax error\n```"
    llm = MockCompletion(lambda prompt, system: broken)
    result = run_one(issue, ZeroShot(), llm)
    assert not result.passed
    assert result.error_kind in {"syntax_error", "import_error"}


def test_extract_python_block_takes_the_last_fence():
    # Reasoning often quotes a line of the buggy file before the final answer.
    text = (
        "The bug is here:\n```python\nreturn list(range(start, end))\n```\n"
        "Fixed file:\n```python\ndef f():\n    return 1\n```\n"
    )
    assert extract_python_block(text) == "def f():\n    return 1\n"


def test_extract_python_block_drops_prose_without_a_fence():
    assert extract_python_block("Sorry, I can't produce a fix for this.") == ""
