"""
Reporter agent.

Pure aggregation — no LLM call needed here, which keeps report generation
free and instant. Turns raw per-test-case results into a scorecard the
dashboard and CLI both consume.
"""
from collections import defaultdict


class ReporterAgent:
    def build_scorecard(self, results: list[dict]) -> dict:
        if not results:
            return {"total_tests": 0, "overall_success_rate": 0.0, "by_category": {}, "high_severity_failures": [], "errored_tests": []}

        # Execution errors (API failures, exhausted retries) are NOT evidence
        # the target behaved safely — they mean the test never actually ran.
        # Excluding them from the success-rate denominator keeps the metric
        # honest; they're still surfaced separately so nothing is silently dropped.
        errored = [r for r in results if r.get("error")]
        scored = [r for r in results if not r.get("error")]

        total = len(scored)
        succeeded = sum(1 for r in scored if r["attack_succeeded"])

        by_category = defaultdict(lambda: {"total": 0, "succeeded": 0})
        for r in scored:
            cat = r["category"]
            by_category[cat]["total"] += 1
            if r["attack_succeeded"]:
                by_category[cat]["succeeded"] += 1

        by_category_summary = {
            cat: {
                "total": stats["total"],
                "succeeded": stats["succeeded"],
                "success_rate": round(stats["succeeded"] / stats["total"], 3) if stats["total"] else 0.0,
            }
            for cat, stats in by_category.items()
        }

        high_severity_failures = sorted(
            [r for r in scored if r["attack_succeeded"] and r["severity"] >= 4],
            key=lambda r: -r["severity"],
        )

        return {
            "total_tests": total,
            "attacks_succeeded": succeeded,
            "overall_success_rate": round(succeeded / total, 3) if total else 0.0,
            "by_category": by_category_summary,
            "high_severity_failures": high_severity_failures,
            "errored_tests": errored,
        }

    def format_text_report(self, scorecard: dict, target_name: str) -> str:
        lines = [
            f"SentinelMCP Reliability Report — target: {target_name}",
            "=" * 60,
            f"Total tests run: {scorecard['total_tests']}",
            f"Attacks that succeeded: {scorecard.get('attacks_succeeded', 0)} "
            f"({scorecard['overall_success_rate'] * 100:.1f}% attack success rate)",
            "",
            "By category:",
        ]
        for cat, stats in scorecard["by_category"].items():
            lines.append(f"  {cat:25s} {stats['succeeded']}/{stats['total']} succeeded ({stats['success_rate']*100:.1f}%)")

        if scorecard["high_severity_failures"]:
            lines.append("")
            lines.append("HIGH SEVERITY FAILURES:")
            for f in scorecard["high_severity_failures"]:
                lines.append(f"  [{f['category']}] test {f['test_case_id']} (severity {f['severity']}): {f['judge_reasoning']}")
        else:
            lines.append("")
            lines.append("No high-severity failures detected.")

        if scorecard.get("errored_tests"):
            lines.append("")
            lines.append(f"NOT TESTED ({len(scorecard['errored_tests'])} execution errors — excluded from success rate above, re-run these):")
            for e in scorecard["errored_tests"]:
                lines.append(f"  [{e['category']}] test {e['test_case_id']}: {e['error']}")

        return "\n".join(lines)
