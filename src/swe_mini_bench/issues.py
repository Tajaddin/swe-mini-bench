"""Issue fixtures: 10 small Python bugs.

Each issue is a self-contained module under ``issues/`` with:

* ``module.py`` — the buggy code (small, < 60 lines)
* ``test_module.py`` — pytest tests; ``failing`` ones reproduce the bug
* ``ISSUE.md`` — the user-facing bug report (what an agent sees)

The fixtures are stored as data files inside the ``issues`` package so
``load_issues()`` can return them without filesystem assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Issue:
    """One curated bug + the tests that prove it's fixed."""

    id: str
    title: str
    issue_text: str
    buggy_code: str
    test_code: str
    module_name: str = "module"
    test_module_name: str = "test_module"

    def render_prompt(self) -> str:
        """Format the issue as the prompt-shape the agent sees."""
        return (
            f"# Bug report\n\n## Title\n{self.title}\n\n## Description\n{self.issue_text}\n\n"
            f"## Buggy file ({self.module_name}.py)\n```python\n{self.buggy_code}\n```\n\n"
            f"## Failing tests ({self.test_module_name}.py)\n```python\n{self.test_code}\n```\n\n"
            "Return the corrected contents of "
            f"{self.module_name}.py wrapped in a single ```python``` fenced block. "
            "Do NOT include the tests, explanations, or extra prose outside the fence."
        )


_FIXTURES = [
    ("01_off_by_one_range", "Off-by-one in inclusive range"),
    ("02_mutable_default", "Mutable default arg shares state"),
    ("03_string_strip_chars", "str.strip() treats arg as char set"),
    ("04_dict_get_default", "dict.get default is evaluated eagerly"),
    ("05_int_division", "Integer division truncates fractional cents"),
    ("06_late_binding_closure", "Late-binding loop closures capture last value"),
    ("07_unicode_normalize", "Names compare unequal due to unicode normalization"),
    ("08_recursion_base_case", "Recursive sum misses single-element base case"),
    ("09_timezone_naive", "Naive datetime compared to aware datetime"),
    ("10_set_membership", "List membership is O(n) per call"),
]


def _issues_root() -> Path:
    """Locate the ``issues`` directory by walking up from this module."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "issues"
        if candidate.is_dir() and (candidate / "01_off_by_one_range").is_dir():
            return candidate
    raise FileNotFoundError("issues directory not found relative to swe_mini_bench")


def load_issues() -> list[Issue]:
    """Return all 10 issues with their buggy code + tests."""
    root = _issues_root()
    out: list[Issue] = []
    for slug, title in _FIXTURES:
        sub = root / slug
        bug = (sub / "module.py").read_text(encoding="utf-8")
        tests = (sub / "test_module.py").read_text(encoding="utf-8")
        issue_text = (sub / "ISSUE.md").read_text(encoding="utf-8")
        out.append(
            Issue(
                id=slug,
                title=title,
                issue_text=issue_text.strip(),
                buggy_code=bug,
                test_code=tests,
            )
        )
    return out
