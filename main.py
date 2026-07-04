"""
CLI entry point for SentinelMCP.

Usage:
    python main.py --target "support-agent-v1"
    python main.py --target "support-agent-v1" --category tool_hijacking direct_injection
    python main.py --target "support-agent-v1" --mutate

Free-tier note: each test case costs 2 LLM calls (Target + Judge), or 3 if
--mutate is set (adds an Attacker call). The 24-case seed suite at default
settings is ~48 calls — well within Groq's free daily quota, but the built-in
delay between calls (see config.REQUEST_DELAY_SECONDS) means a full run takes
a few minutes. That's intentional: it's what keeps this free.
"""
import argparse
import logging
import sys

from storage.db import init_db, create_run, finish_run
from eval.test_cases import get_all_test_cases, get_test_cases_by_category
from eval.taxonomy import AttackCategory
from agents.graph import run_eval_suite
from agents.reporter import ReporterAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Run the SentinelMCP adversarial eval suite against a target agent.")
    parser.add_argument("--target", required=True, help="Label for the target agent under test")
    parser.add_argument("--category", nargs="*", default=None, help="Restrict to specific attack categories (default: all)")
    parser.add_argument("--mutate", action="store_true", help="Use the Attacker LLM to paraphrase seed cases into fresh variants")
    args = parser.parse_args()

    init_db()

    if args.category:
        try:
            categories = [AttackCategory(c) for c in args.category]
        except ValueError as e:
            print(f"Invalid category: {e}")
            print(f"Valid categories: {[c.value for c in AttackCategory]}")
            sys.exit(1)
        test_cases = []
        for c in categories:
            test_cases.extend(get_test_cases_by_category(c))
    else:
        test_cases = get_all_test_cases()

    if not test_cases:
        print("No test cases matched the given categories.")
        sys.exit(1)

    print(f"Running {len(test_cases)} test cases against target '{args.target}' "
          f"(mutation={'on' if args.mutate else 'off'})...")

    run_id = create_run(target_name=args.target, notes=f"{len(test_cases)} cases, mutate={args.mutate}")

    try:
        final_state = run_eval_suite(test_cases, target_name=args.target, run_id=run_id, use_mutation=args.mutate)
    finally:
        finish_run(run_id)

    scorecard = final_state["scorecard"]
    report = ReporterAgent().format_text_report(scorecard, args.target)
    print("\n" + report)
    print(f"\nRun ID: {run_id}")
    print("View full results with: streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
