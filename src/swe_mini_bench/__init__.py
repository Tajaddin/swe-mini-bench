"""swe-mini-bench — lightweight code-patch evaluation.

Exports:

* :class:`Issue` — one curated bug fixture
* :class:`PatchResult` — outcome of running an agent against an issue
* :class:`AgentStrategy`, :class:`ZeroShot`, :class:`Scratchpad`,
  :class:`ScratchpadCritique` — three agent strategies, increasing scaffolding
* :func:`load_issues`, :func:`run_strategy`, :func:`bench`
"""

from swe_mini_bench.issues import Issue, load_issues
from swe_mini_bench.runner import PatchResult, bench, run_one, run_strategy
from swe_mini_bench.strategies import (
    AgentStrategy,
    AnthropicCompletion,
    Completion,
    MockCompletion,
    ScratchpadCritique,
    Scratchpad,
    ZeroShot,
)

__all__ = [
    "AgentStrategy",
    "AnthropicCompletion",
    "Completion",
    "Issue",
    "MockCompletion",
    "PatchResult",
    "ScratchpadCritique",
    "Scratchpad",
    "ZeroShot",
    "bench",
    "load_issues",
    "run_one",
    "run_strategy",
]
