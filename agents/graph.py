"""
LangGraph orchestration for SentinelMCP.

Flow: for each test case -> Attacker selects/mutates prompt -> Target responds
-> Judge scores -> result logged -> loop until test cases exhausted -> Reporter
builds final scorecard.

Kept as an explicit StateGraph (rather than a hidden loop in Python) so the
control flow is inspectable and extensible — e.g. adding a "retry with a
harder mutation if the attack failed" branch later is a one-node change.
"""
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from eval.test_cases import TestCase
from agents.attacker import AttackerAgent
from agents.target import TargetAgent
from agents.judge import JudgeAgent
from agents.reporter import ReporterAgent
from storage.db import log_result


class GraphState(TypedDict):
    test_cases: list[TestCase]
    index: int
    target_name: str
    run_id: str
    use_mutation: bool
    results: list[dict]
    scorecard: Optional[dict]


def build_graph(attacker: AttackerAgent, target: TargetAgent, judge: JudgeAgent, reporter: ReporterAgent):

    def attack_and_score_node(state: GraphState) -> GraphState:
        tc = state["test_cases"][state["index"]]

        # On a rate-limited free tier, a single test case exhausting its
        # retries is expected occasionally over a multi-minute run. Without
        # this try/except, that one failure used to crash the whole suite and
        # every remaining test case went untested. Now it's logged as an
        # execution error (excluded from the success-rate math, since an
        # error is not evidence of safe behavior) and the run continues.
        try:
            prompt = attacker.mutate(tc) if state["use_mutation"] else attacker.from_seed(tc)
            target_result = target.run(prompt, context=tc.context)
            verdict = judge.score(tc, target_result["response_text"], target_result["tool_called"])

            result_row = {
                "test_case_id": tc.id,
                "category": tc.category.value,
                "prompt": prompt,
                "target_response": target_result["response_text"],
                "tool_called": target_result["tool_called"],
                "attack_succeeded": verdict["attack_succeeded"],
                "severity": verdict["severity"],
                "judge_reasoning": verdict["reasoning"],
                "error": None,
            }
            log_result(
                run_id=state["run_id"], test_case_id=tc.id, category=tc.category.value,
                prompt=prompt, target_response=target_result["response_text"],
                attack_succeeded=verdict["attack_succeeded"], severity=verdict["severity"],
                judge_reasoning=verdict["reasoning"], tool_called=target_result["tool_called"],
            )
        except Exception as e:  # noqa: BLE001 - deliberately broad: any failure here must not kill the run
            result_row = {
                "test_case_id": tc.id,
                "category": tc.category.value,
                "prompt": tc.prompt,
                "target_response": "",
                "tool_called": None,
                "attack_succeeded": False,
                "severity": 0,
                "judge_reasoning": f"EXECUTION ERROR (test case not actually evaluated): {e}",
                "error": str(e),
            }
            log_result(
                run_id=state["run_id"], test_case_id=tc.id, category=tc.category.value,
                prompt=tc.prompt, target_response="", attack_succeeded=False, severity=0,
                judge_reasoning=result_row["judge_reasoning"], tool_called=None, error=str(e),
            )

        state["results"].append(result_row)
        state["index"] += 1
        return state

    def should_continue(state: GraphState) -> str:
        return "continue" if state["index"] < len(state["test_cases"]) else "done"

    def report_node(state: GraphState) -> GraphState:
        state["scorecard"] = reporter.build_scorecard(state["results"])
        return state

    graph = StateGraph(GraphState)
    graph.add_node("attack_and_score", attack_and_score_node)
    graph.add_node("report", report_node)

    graph.set_entry_point("attack_and_score")
    graph.add_conditional_edges(
        "attack_and_score",
        should_continue,
        {"continue": "attack_and_score", "done": "report"},
    )
    graph.add_edge("report", END)

    return graph.compile()


def run_eval_suite(
    test_cases: list[TestCase],
    target_name: str,
    run_id: str,
    use_mutation: bool = False,
    target: TargetAgent | None = None,
    attacker: AttackerAgent | None = None,
    judge: JudgeAgent | None = None,
) -> dict:
    """Convenience entry point used by main.py and the MCP server tool."""
    attacker = attacker or AttackerAgent()
    target = target or TargetAgent()
    judge = judge or JudgeAgent()
    reporter = ReporterAgent()

    compiled = build_graph(attacker, target, judge, reporter)
    final_state = compiled.invoke({
        "test_cases": test_cases,
        "index": 0,
        "target_name": target_name,
        "run_id": run_id,
        "use_mutation": use_mutation,
        "results": [],
        "scorecard": None,
    })
    return final_state
