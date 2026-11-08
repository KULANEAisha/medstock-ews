"""Run the assistant on the evaluation set and report accuracy and failure cases.

Run:  python -m evaluation.run_eval            (uses cached answers where available)
      python -m evaluation.run_eval --no-cache --delay 15
"""
import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

from medstock.llm import ask
from .scoring import score

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=12.0, help="seconds between uncached questions (free-tier limits)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    qs = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    results = []
    for q in qs:
        r = ask(q["question"], use_cache=not args.no_cache)
        if r["error"]:
            ok, why = False, f"API/tool error: {r['error']}"
        else:
            ok, why = score(q, r["answer"])
        results.append({**q, "answer": r["answer"], "passed": ok, "reason": why, "error": r["error"],
                        "tools_called": [t["tool"] for t in r["tool_calls"]], "model": r["model"]})
        print(f"{q['id']} {'PASS' if ok else 'FAIL'}  {q['category']}")
        if not r.get("cached") and not r["error"]:
            time.sleep(args.delay)
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    n, p = len(results), sum(r["passed"] for r in results)
    errs = sum(1 for r in results if r["error"])
    print(f"\nAccuracy: {p}/{n} = {p / n:.0%}   (API errors counted as failures: {errs})")
    by = defaultdict(lambda: [0, 0])
    for r in results:
        by[r["category"]][1] += 1
        by[r["category"]][0] += r["passed"]
    for k, (a, b) in by.items():
        print(f"  {k:16s} {a}/{b}")
    fails = [r for r in results if not r["passed"]]
    if fails:
        print("\nFAILURES (read each one: is it a model error, a scoring quirk, or a tool bug?)")
        for r in fails:
            print(f"\n{r['id']} [{r['category']}] {r['question']}\n  why: {r['reason']}\n"
                  f"  tools: {r['tools_called']}\n  answer: {r['answer'][:300]!r}")


if __name__ == "__main__":
    main()
