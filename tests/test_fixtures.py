"""Sanity tests for the 10 issue fixtures.

For every fixture:

* the buggy ``module.py`` must FAIL at least one test (otherwise the bug
  isn't actually demonstrated and an LLM "fixing" nothing would still pass).
* the canonical fix listed in ``CANONICAL_FIXES`` must PASS all tests
  (otherwise our reference solution is wrong).
* pytest must report exactly the top-level test functions the runner finds
  in the source (otherwise a test class or a parametrized test would never
  count as passed).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from swe_mini_bench.issues import load_issues
from swe_mini_bench.runner import _expected_tests, _junit_outcomes


# A minimal known-good patch for each issue. Used by the bench-validation test;
# also useful as a sanity floor — if these break, the issue spec is wrong.
CANONICAL_FIXES = {
    "01_off_by_one_range": """\
def inclusive_range(start: int, end: int) -> list[int]:
    return list(range(start, end + 1))
""",
    "02_mutable_default": """\
def add_item(item, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket
""",
    "03_string_strip_chars": """\
def remove_suffix(text: str, suffix: str) -> str:
    if suffix and text.endswith(suffix):
        return text[: -len(suffix)]
    return text
""",
    "04_dict_get_default": """\
_log: list[str] = []


def _expensive_default_port():
    _log.append("computing default port")
    return 8080


def get_config_value(key: str, config: dict | None = None) -> int:
    config = config or {"port": 9090, "timeout": 30}
    if key in config:
        return config[key]
    return _expensive_default_port()
""",
    "05_int_division": """\
def split_bill(total_cents: int, n: int) -> list[int]:
    per = total_cents // n
    remainder = total_cents - per * n
    return [per + 1 if i < remainder else per for i in range(n)]
""",
    "06_late_binding_closure": """\
from typing import Callable


def make_multipliers(factors: list[int]) -> list[Callable[[int], int]]:
    return [(lambda x, f=f: f * x) for f in factors]
""",
    "07_unicode_normalize": """\
import unicodedata


def is_same_name(a: str, b: str) -> bool:
    return unicodedata.normalize("NFC", a) == unicodedata.normalize("NFC", b)
""",
    "08_recursion_base_case": """\
def recursive_sum(xs: list[int]) -> int:
    if not xs:
        return 0
    return xs[0] + recursive_sum(xs[1:])
""",
    "09_timezone_naive": """\
from datetime import datetime, timezone


def is_in_future(dt: datetime) -> bool:
    return dt > datetime.now(timezone.utc)
""",
    "10_set_membership": """\
def filter_blocked(events: list[dict], blocked_ids: list[int]) -> list[dict]:
    blocked = set(blocked_ids)
    return [e for e in events if e["id"] not in blocked]
""",
}


def _run_pytest(module_src: str, test_src: str) -> tuple[int, str, str, str | None]:
    with tempfile.TemporaryDirectory() as td:
        sandbox = Path(td)
        (sandbox / "module.py").write_text(module_src, encoding="utf-8")
        (sandbox / "test_module.py").write_text(test_src, encoding="utf-8")
        (sandbox / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        report = sandbox / "report.xml"
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=line", f"--junitxml={report}", str(sandbox)],
            cwd=sandbox,
            capture_output=True,
            text=True,
            timeout=60,
        )
        junit = report.read_text(encoding="utf-8") if report.is_file() else None
        return proc.returncode, proc.stdout, proc.stderr, junit


@pytest.mark.parametrize("issue", load_issues(), ids=lambda i: i.id)
def test_buggy_code_fails(issue):
    """The shipped buggy module must fail at least one of its tests."""
    code, _, _, _ = _run_pytest(issue.buggy_code, issue.test_code)
    assert code != 0, (
        f"{issue.id}: buggy module passes its tests — the fixture is broken"
    )


@pytest.mark.parametrize("issue", load_issues(), ids=lambda i: i.id)
def test_canonical_fix_passes(issue):
    """The canonical fix must pass every test, and the runner must see every test."""
    code, stdout, stderr, junit = _run_pytest(CANONICAL_FIXES[issue.id], issue.test_code)
    assert code == 0, (
        f"{issue.id}: canonical fix fails its own tests.\n{stdout}\n{stderr}"
    )
    reported = sorted(
        name for (cls, name) in _junit_outcomes(junit) if cls.split(".")[0] == "test_module"
    )
    assert reported == sorted(_expected_tests(issue.test_code)), (
        f"{issue.id}: pytest reports tests the runner cannot match by name "
        "(use plain top-level test functions, no classes or parametrize)"
    )
