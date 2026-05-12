"""Real Anthropic Haiku 4.5 benchmark across all 3 strategies × 10 issues."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from swe_mini_bench import (
    AnthropicCompletion,
    ScratchpadCritique,
    Scratchpad,
    ZeroShot,
    bench,
    load_issues,
)
from swe_mini_bench.runner import report_to_dict

OUT = Path(__file__).resolve().parent / "anthropic_results.json"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    llm = AnthropicCompletion()
    issues = load_issues()
    strategies = [ZeroShot(), Scratchpad(), ScratchpadCritique()]
    print(f"model={llm.model}, issues={len(issues)}, strategies={len(strategies)}")

    report = bench(issues, strategies, llm)
    OUT.write_text(json.dumps(report_to_dict(report), indent=2), encoding="utf-8")

    print(f"\nResults written to {OUT}\n")
    for s in report.summaries:
        print(f"  {s.strategy:24s} pass@1 = {s.pass_count}/{s.n} ({s.pass_rate * 100:.1f}%)")
        for r in s.results:
            status = "OK" if r.passed else r.error_kind or "FAIL"
            print(f"    - {r.issue_id:32s} {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
