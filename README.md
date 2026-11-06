# swe-mini-bench

> Lightweight code-patch eval. 10 curated Python bugs, 3 agent strategies (zero-shot → scratchpad → scratchpad+self-critique), real Claude Haiku 4.5 numbers. Each strategy's failures are categorised by **error kind** (`syntax_error`, `test_failure`, `no_code_block`) so the gain from extra scaffolding is auditable.

[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE) [![Tests](https://img.shields.io/badge/tests-40%20passing-brightgreen)](#tests) [![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()

## Why

SWE-bench is excellent but heavyweight: docker-pinned Python versions per repo, long-running container builds, often days of compute to evaluate one model. **swe-mini-bench is the opposite end of the trade-off**: ten self-contained Python bugs (~30 lines of code each), one pytest run per attempt, full benchmark in about a minute on a CPU.

Use it to:

* Compare two LLMs *qualitatively* on code-patching before paying for a SWE-bench run.
* Validate a new agent strategy (scratchpad? self-critique? tool use?) end-to-end on the same denominator.
* Diagnose **why** patches fail — the runner classifies every failure as `syntax_error`, `import_error`, `test_failure`, `no_code_block`, `timeout`, or `tampered`.

It is not a replacement for SWE-bench. The bugs are small and self-contained; an LLM that aces this can still fail at large-repo navigation.

## Hero benchmark

`python bench/run_anthropic.py` against `claude-haiku-4-5-20251001`, 10 issues, 3 strategies, 40 LLM calls total, ~5 minutes wall clock:

| Strategy | pass@1 | Calls per fix | Notes |
|---|---:|---:|---|
| `zero_shot` | **10/10 (100%)** | 1 | Single call, "return the fixed file." |
| `scratchpad` | **9/10 (90%)** | 1 | Missed `06_late_binding_closure` with 0 tests passed and 0 failed, so its tests never ran. See the note below. |
| `scratchpad_critique` | **10/10 (100%)** | 2 | Self-review catches the scratchpad regression, but doubles cost. |

**Note on these numbers.** They come from the runner as it was before 2026-11-06, which graded the *first* code block of each answer. Scratchpad answers write reasoning before the code and can quote snippets in it, and a quoted snippet that fails at import (say, one using a name defined elsewhere in the file) gives exactly this 0-passed, 0-failed result, so the `06` miss may be the extractor, not the model. The run did not save patches, so this cannot be checked, and the table has not been re-run since the runner was fixed (last code block, sandboxed run, parent-side verdict, saved patches). Re-run `python bench/run_anthropic.py` before drawing conclusions about scratchpad vs zero-shot.

What the run does show: Haiku 4.5 is strong on small, well-described single-file bugs (10/10 zero-shot). A larger fixture set (50+) would be needed to separate the strategies.

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

All three end with `extract_python_block(text)`, which takes the last ```` ```python ```` fence, so code quoted in the reasoning is skipped. Without a fence it uses the raw text only if it parses as Python; otherwise the patch is empty and graded `no_code_block`.

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

# Optional, untested: build the sandbox image so patches run in Docker with no network:
docker build -t swe-mini-bench-sandbox sandbox/

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

1. Strategy returns a string (the patched file body). An empty patch is graded `no_code_block` without running anything.
2. Runner writes the body to `module.py`, the issue's tests to `test_module.py`, a canary test, and an empty `pytest.ini` into a fresh directory.
3. Runs `pytest -q --tb=short` there in a separate process, with a 60 s timeout:
   * **Docker** when the `swe-mini-bench-sandbox` image is built: `--network none`, read-only root filesystem and inputs, all capabilities dropped, memory and process limits, unprivileged user. **Untested:** the image has not been built or run as part of this project; only the `docker run` command line is unit-tested. It is meant to protect the host (network, files, environment), not the verdict: the patch still runs inside pytest, which writes its report to a writable mount.
   * **Local subprocess** otherwise: same interpreter, with network and file access, and an environment stripped to `PATH`, temp-dir and a few OS variables, so `ANTHROPIC_API_KEY` is not passed to the child. That is not isolation: the patch runs as your user, so it can still read the key from the parent's `/proc/<pid>/environ` on Linux or from files in your home directory. Choose with `--sandbox auto|docker|local`.
4. Decides the verdict in the parent process from pytest's JUnit report, not from the exit code or printed summary: every test function the parent finds in the trusted `test_module.py` must be reported passed, and two canary tests must keep their outcome, a plain failing test reported as failed and a strict `xfail` test as xfailed. A patch that stops tests from running, or that rewrites every failure as a pass, flips a canary and is graded `tampered`.

**The verdict is not tamper-proof.** The patch runs in the same interpreter as the tests that call it, and that process writes the JUnit report the parent reads. The canaries only catch tampering that changes every test's outcome alike. A patch written against this harness can still score a pass: one that runs the canaries and skips every other test (kept in `tests/test_runner.py` as an expected failure), or one that returns objects whose `__eq__` is always true. Neither sandbox changes this, so read the saved patches before trusting a pass from a model you do not trust.

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
    sandbox="docker",
    patch="from typing import Callable\n\ndef make_multipliers...",
)
```

`error_kind` is `"syntax_error" | "import_error" | "test_failure" | "no_code_block" | "timeout" | "tampered" | None`. The JSON report keeps each patch, so any failure can be inspected after the run. This lets you distinguish "model produced unparseable code" from "model produced runnable but wrong code" — those are different failure modes with different fixes.

## Tests

```bash
pytest
```

Four files:

* **`tests/test_fixtures.py`** — for each of the 10 issues, runs pytest against the buggy code (must fail) and the canonical fix (must pass). 20 parameterised cases.
* **`tests/test_strategies.py`** — covers the prompt extractor, all 3 strategies with mock LLMs, and the runner's failure-classification logic. 9 unit cases.
* **`tests/test_runner.py`** — adversarial patches: one that disables pytest, one that rewrites failures as passes, one that forges a summary and exits early, one that hangs, one that reads the environment, a prose-only answer, plus a correct patch and the saved patch. 8 cases, and the known bypass above pinned as an expected failure.
* **`tests/test_sandbox.py`** — the Docker command line and the local fallback. 3 cases.

```
40 passed, 1 xfailed
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
│   ├── sandbox.py       # runs pytest in Docker (no network) or a stripped local subprocess
│   └── cli.py           # `swe-mini-bench {list,run}` Click CLI
├── issues/              # 10 fixture subdirs (ISSUE.md + module.py + test_module.py)
├── tests/               # fixture sanity, strategy, runner and sandbox tests
├── sandbox/Dockerfile   # image for the Docker sandbox
└── bench/
    ├── run_anthropic.py
    └── anthropic_results.json
```

## Limitations

**Single-file bugs only.** Every issue lives in one ~30-line `module.py`. Real-world refactors span files, and an LLM that aces this can still fail on cross-file changes. Use SWE-bench Lite or Verified for cross-file evaluation.

**No tool use.** The strategies are all "read prompt → write code." Adding a strategy with file-read / file-grep tools is a few dozen lines, but it isn't shipped here — the comparison between three text-only strategies stays clean.

**Bench size is 10.** Confidence intervals on 10 are wide. The headline is the per-strategy *direction of change*, not a calibrated point estimate. For statistical claims, expand to several hundred fixtures.

**Patch parsing assumes ```python``` fences.** Models that emit unfenced code (rare on Haiku and above) are handled by a fallback that uses the raw text when it parses as Python, but error-checked structures (diff format, line-anchored patches) would need a different extractor.

## License

MIT — see [LICENSE](LICENSE).
