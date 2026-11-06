"""Three agent strategies + the LLM completion protocol they call.

Strategies, from least to most scaffolding:

1. :class:`ZeroShot` — single LLM call, "here is the bug, return the fixed file."
2. :class:`Scratchpad` — single LLM call, "think step by step before writing code."
3. :class:`ScratchpadCritique` — two LLM calls; the second asks the model to
   review its own first answer against the failing tests and rewrite if needed.

All strategies return a string (the patched file body). The runner is what
executes the patched body against the tests.
"""

from __future__ import annotations

import ast
import os
import re
from typing import Protocol

from swe_mini_bench.issues import Issue


class Completion(Protocol):
    """Minimal LLM-completion interface used by the strategies."""

    model: str

    def complete(self, prompt: str, *, system: str | None = None) -> str: ...


# ---------------------------------------------------------------------------
# Completion backends
# ---------------------------------------------------------------------------


class MockCompletion:
    """Deterministic completion. ``responder`` returns the model output."""

    def __init__(self, responder, model: str = "mock") -> None:
        self.model = model
        self.responder = responder
        self.calls: list[dict] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls.append({"prompt": prompt, "system": system})
        return self.responder(prompt, system)


class AnthropicCompletion:
    """Synchronous Anthropic ``messages.create`` wrapper."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 2048,
    ) -> None:
        from anthropic import Anthropic  # lazy

        self.model = model or os.environ.get(
            "SWE_MINI_MODEL", "claude-haiku-4-5-20251001"
        )
        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.max_tokens = max_tokens

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        resp = self.client.messages.create(**kwargs)
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(
    r"```(?:python)?\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def extract_python_block(text: str) -> str:
    """Pull the last ```python ... ``` block out of a model response.

    The last block, because reasoning before the answer often quotes snippets.
    Without a fence, the raw text is used if it parses as Python (some models
    forget the fence); otherwise the result is empty, which the runner reports
    as ``no_code_block``.
    """
    blocks = _FENCE_RE.findall(text)
    if blocks:
        return blocks[-1].rstrip() + "\n"
    try:
        ast.parse(text)
    except SyntaxError:
        return ""
    return text.strip() + "\n"


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


class AgentStrategy(Protocol):
    name: str

    def solve(self, issue: Issue, llm: Completion) -> str: ...


class ZeroShot:
    """Minimal scaffolding: send the issue, parse the code block."""

    name = "zero_shot"

    def solve(self, issue: Issue, llm: Completion) -> str:
        prompt = issue.render_prompt()
        out = llm.complete(prompt, system=None)
        return extract_python_block(out)


class Scratchpad:
    """Ask the model to think step by step before writing the patch."""

    name = "scratchpad"

    SYSTEM = (
        "You are a careful Python engineer. Before writing any code, think "
        "through the bug and the failing tests. Identify the minimal change "
        "needed. Then return the corrected file body wrapped in a single "
        "```python``` block."
    )

    def solve(self, issue: Issue, llm: Completion) -> str:
        prompt = (
            issue.render_prompt()
            + "\n\nFirst, briefly write your reasoning in plain text. "
            "Then output the corrected file in a single ```python``` block."
        )
        out = llm.complete(prompt, system=self.SYSTEM)
        return extract_python_block(out)


class ScratchpadCritique:
    """Scratchpad pass, then a second pass that critiques and patches."""

    name = "scratchpad_critique"

    SYSTEM = Scratchpad.SYSTEM

    CRITIQUE_SYSTEM = (
        "You are reviewing your own first attempt at a bug fix. The first "
        "attempt is shown below. Check it against the failing tests. If it "
        "is correct, return it unchanged. If not, return a corrected version. "
        "Output ONLY a single ```python``` block with the final file body."
    )

    def solve(self, issue: Issue, llm: Completion) -> str:
        first_prompt = (
            issue.render_prompt()
            + "\n\nFirst, briefly write your reasoning. Then output the "
            "corrected file in a single ```python``` block."
        )
        first = llm.complete(first_prompt, system=self.SYSTEM)
        first_code = extract_python_block(first)

        critique_prompt = (
            f"## Original buggy file ({issue.module_name}.py)\n"
            f"```python\n{issue.buggy_code}\n```\n\n"
            f"## Failing tests ({issue.test_module_name}.py)\n"
            f"```python\n{issue.test_code}\n```\n\n"
            f"## First attempt\n```python\n{first_code}```\n\n"
            "Review the first attempt against the failing tests. Return the "
            "final correct file body in a single ```python``` block."
        )
        second = llm.complete(critique_prompt, system=self.CRITIQUE_SYSTEM)
        return extract_python_block(second)
