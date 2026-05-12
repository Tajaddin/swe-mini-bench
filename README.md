# swe-mini-bench

> Lightweight code-patch eval. 10 curated Python bugs, 3 agent strategies (zero-shot → scratchpad → scratchpad+self-critique), real Claude Haiku 4.5 numbers. Each strategy's failures are categorised by **error kind** (`syntax_error`, `test_failure`, `no_code_block`) so the gain from extra scaffolding is auditable.

[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE) [![Tests](https://img.shields.io/badge/tests-31%20passing-brightgreen)](#tests) [![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()

## Why

SWE-bench is excellent but heavyweight: docker-pinned Python versions per repo, long-running container builds, often days of compute to evaluate one model. **swe-mini-bench is the opposite end of the trade-off**: ten self-contained Python bugs (~30 lines of code each), one pytest run per attempt, full benchmark in about a minute on a CPU.

Use it to:

* Compare two LLMs *qualitatively* on code-patching before paying for a SWE-bench run.
* Validate a new agent strategy (scratchpad? self-critique? tool use?) end-to-end on the same denominator.
* Diagnose **why** patches fail — the runner classifies every failure as `syntax_error`, `test_failure`, `no_code_block`, or `import_error`.

It is not a replacement for SWE-bench. The bugs are small and self-contained; an LLM that aces this can still fail at large-repo navigation.

## Hero benchmark

`python bench/run_anthropic.py` against `claude-haiku-4-5-20251001`, 10 issues, 3 strategies, 40 LLM calls total, ~5 minutes wall clock:

| Strategy | pass@1 | Calls per fix | Notes |
|---|---:|---:|---|
| `zero_shot` | **10/10 (100%)** | 1 | Single call, "return the fixed file." |
| `scratchpad` | **9/10 (90%)** | 1 | Regressed on `06_late_binding_closure` — the model talked itself into a wrong fix while writing reasoning. |
| `scratchpad_critique` | **10/10 (100%)** | 2 | Self-review catches the scratchpad regression, but doubles cost. |

The surprise is the **scratchpad regression**: adding a reasoning slot caused Haiku to fail a problem it solved cleanly zero-shot. Self-critique recovers it, but only by paying for a second LLM call.

For 10/10 baseline, the takeaway is that Haiku 4.5 is genuinely strong on small, well-described single-file bugs. **The discriminator isn't the headline pass rate — it's the failure-mode evidence that more scaffolding ≠ always better.** A larger fixture set (50+) would tighten the interval; on this corpus, scratchpad alone is strictly dominated by zero-shot at 1× cost and by scratchpad+critique at 2× cost.

Raw output: [`bench/anthropic_results.json`](bench/anthropic_results.json). Reproduce with the command above. Cost per full run: under $0.05 on Haiku.

## The 10 issues

| # | Slug | Bug kind |
|---|---|---|
| 1 | `01_off_by_one_range` | Inclusive vs exclusive range |
| 2 | `02_mutable_default` | Mutable default argument leaks state across calls |
| 3 | `03_string_strip_chars` | `str.rstrip(suffix)` strips a char *set*, not a literal suffix |
| 4 | `04_dict_get_default` | `dict.get(key, expensive())` evaluates default eagerly |
| 5 | `05_int_division` | `total // n` drops the remainder; split must reconcile |
| 6 | `06_late_binding_closure` | Lambdas in a loop all capture the final loop value |
| 7 | `07_unicode_normalize` | Equal-looking unicode strings compare unequal without NFC |
| 8 | `08_recursion_base_case` | Recursive sum misses single-element base case |
| 9 | `09_timezone_naive` | `datetime.utcnow()` vs aware datetime → `TypeError` |
| 10 | `10_set_membership` | Membership against a list is O(n*m); must be a set |

Each fixture is sanity-checked by `tests/test_fixtures.py`:
1. The shipped buggy module must FAIL at least one test (proving the bug is real).
2. A hand-written canonical fix must PASS every test (proving the spec is achievable).

If either invariant breaks, the fixture is wrong and the bench is invalid — and the build fails loudly.

## The 3 strategies

```python
from swe_mini_bench import ZeroShot, Scratchpad, ScratchpadCritique
```

| Strategy | Calls | What it does |
|---|---:|---|
| `ZeroShot` | 1 | Sends the issue + buggy file + failing tests. Asks for a single ```python``` block. |
| `Scratchpad` | 1 | Same prompt + a system message and inline instruction to write reasoning before the code block. |
| `ScratchpadCritique` | 2 | First call = scratchpad. Second call shows the model its own first attempt and asks it to review against the failing tests, returning only the corrected file. |

All three end with `extract_python_block(text)` which pulls the first ```` ```python ```` fence (or falls back to raw text if the model forgot).

### Why three strategies, not fifteen

Each extra strategy needs to be defensible. The three here cover the canonical scaffolding ladder:

* **Zero-shot** is the lower bound — what the model can do with no help.
* **Scratchpad** isolates the "think then write" prior. Same model, same context, just a reasoning slot.
* **Scratchpad + critique** doubles the inference cost. The cost-quality trade-off vs scratchpad alone is the headline number — if it's small, scaffold complexity isn't paying its way.

## Quickstart

```bash
pip install -e ".[anthropic,dev]"
export ANTHROPIC_API_KEY=sk-ant-...

# Validate the fixtures (no LLM calls):
pytest

# Run the real benchmark:
python bench/run_anthropic.py
# or via CLI:
swe-mini-bench run --out bench/results.json
```

Or programmatically:

```python
from swe_mini_bench import (
    AnthropicCompletion, load_issues, bench,
    ZeroShot, Scratchpad, ScratchpadCritique,
)

llm = AnthropicCompletion(model="claude-haiku-4-5-20251001")
report = bench(load_issues(), [ZeroShot(), Scratchpad(), ScratchpadCritique()], llm)
for s in report.summaries:
    print(s.strategy, s.pass_rate)
```

## How the runner works

For one `(strategy, issue)` pair:

1. Strategy returns a string (the patched file body).
2. Runner writes the body to `<tmp>/module.py` and the issue's tests to `<tmp>/test_module.py`.
3. Runs `pytest -q --tb=short` in the tempdir.
4. Parses `=== N passed, M failed ===`, classifies the failure (if any), and records the exit code.

A `PatchResult` looks like:

```python
PatchResult(
    strategy="scratchpad_critique",
    issue_id="06_late_binding_closure",
    passed=True,
    tests_passed=3, tests_failed=0,
    error_kind=None,
    pytest_stdout="...", pytest_stderr="...",
    pytest_exitcode=0,
    patch="from typing import Callable\n\ndef make_multipliers...",
)
```

`error_kind` is `"syntax_error" | "import_error" | "test_failure" | "no_code_block" | None`. This lets you distinguish "model produced unparseable code" from "model produced runnable but wrong code" — those are different failure modes with different fixes.

## Tests

```bash
pytest
```

Two suites:

* **`tests/test_fixtures.py`** — for each of the 10 issues, runs pytest against the buggy code (must fail) and the canonical fix (must pass). 20 parameterised cases.
* **`tests/test_strategies.py`** — covers the prompt extractor, all 3 strategies with mock LLMs, and the runner's failure-classification logic. 7 unit cases.

```
27 passed in 40.6s
```

## Bring-your-own LLM

Implement the `Completion` protocol:

```python
class Completion(Protocol):
    model: str
    def complete(self, prompt: str, *, system: str | None = None) -> str: ...
```

Wrap OpenAI / Groq / Bedrock / vLLM with a similar adapter and pass it to `bench()`. The strategies don't know which backend you're on.

## Project layout

```
.
├── src/swe_mini_bench/
│   ├── __init__.py
│   ├── issues.py        # Issue dataclass + load_issues()
│   ├── strategies.py    # ZeroShot / Scratchpad / ScratchpadCritique + Completion protocol
│   ├── runner.py        # PatchResult, run_one, run_strategy, bench, report_to_dict
│   └── cli.py           # `swe-mini-bench {list,run}` Click CLI
├── issues/              # 10 fixture subdirs (ISSUE.md + module.py + test_module.py)
├── tests/               # fixture sanity + strategy unit tests
└── bench/
    ├── run_anthropic.py
    └── anthropic_results.json
```

## Limitations

**Single-file bugs only.** Every issue lives in one ~30-line `module.py`. Real-world refactors span files, and an LLM that aces this can still fail on cross-file changes. Use SWE-bench Lite or Verified for cross-file evaluation.

**No tool use.** The strategies are all "read prompt → write code." Adding a strategy with file-read / file-grep tools is a few dozen lines, but it isn't shipped here — the comparison between three text-only strategies stays clean.

**Bench size is 10.** Confidence intervals on 10 are wide. The headline is the per-strategy *direction of change*, not a calibrated point estimate. For statistical claims, expand to several hundred fixtures.

**Patch parsing assumes ```python``` fences.** Models that emit unfenced code (rare on Haiku and above) are handled by a fallback that uses the raw text, but error-checked structures (diff format, line-anchored patches) would need a different extractor.

## License

MIT — see [LICENSE](LICENSE).
