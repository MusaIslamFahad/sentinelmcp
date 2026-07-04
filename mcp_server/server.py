"""
SentinelMCP MCP server.

Exposes the red-teaming suite as MCP tools so any MCP-compatible client
(Claude, another agent framework, a CI pipeline) can trigger an audit against
a target agent and pull back results, without needing to know anything about
LangGraph internally.

Run with:  python -m mcp_server.server
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from eval.test_cases import get_all_test_cases, get_test_cases_by_category
from eval.taxonomy import AttackCategory
from agents.graph import run_eval_suite
from agents.reporter import ReporterAgent
from storage.db import init_db, create_run, finish_run, get_run_results, get_run

server = Server("sentinelmcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="run_injection_suite",
            description="Run the SentinelMCP adversarial test suite against the target agent and return a run_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "target_name": {"type": "string", "description": "Label for the target being tested"},
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of attack categories to restrict to (e.g. ['tool_hijacking']). Omit to run all.",
                    },
                    "use_mutation": {
                        "type": "boolean",
                        "description": "If true, the Attacker LLM paraphrases each seed case into a fresh variant (uses extra API calls).",
                    },
                },
                "required": ["target_name"],
            },
        ),
        Tool(
            name="score_trajectory",
            description="Retrieve the scored results for a previously run test suite.",
            inputSchema={
                "type": "object",
                "properties": {"run_id": {"type": "string"}},
                "required": ["run_id"],
            },
        ),
        Tool(
            name="generate_report",
            description="Generate a human-readable reliability scorecard for a completed run.",
            inputSchema={
                "type": "object",
                "properties": {"run_id": {"type": "string"}},
                "required": ["run_id"],
            },
        ),
        Tool(
            name="list_attack_categories",
            description="List all attack categories supported by SentinelMCP.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    init_db()

    if name == "list_attack_categories":
        return [TextContent(type="text", text=json.dumps([c.value for c in AttackCategory]))]

    if name == "run_injection_suite":
        target_name = arguments["target_name"]
        categories = arguments.get("categories")
        use_mutation = arguments.get("use_mutation", False)

        if categories:
            test_cases = []
            for c in categories:
                test_cases.extend(get_test_cases_by_category(AttackCategory(c)))
        else:
            test_cases = get_all_test_cases()

        run_id = create_run(target_name=target_name, notes=f"{len(test_cases)} test cases, mutation={use_mutation}")
        # run_eval_suite is synchronous and paces requests with time.sleep()
        # to respect free-tier rate limits, which can take minutes for a full
        # suite. Running it directly here would block the entire asyncio event
        # loop for that whole duration. asyncio.to_thread offloads it to a
        # worker thread so the server stays responsive.
        await asyncio.to_thread(run_eval_suite, test_cases, target_name=target_name, run_id=run_id, use_mutation=use_mutation)
        finish_run(run_id)

        return [TextContent(type="text", text=json.dumps({"run_id": run_id, "tests_run": len(test_cases)}))]

    if name == "score_trajectory":
        results = get_run_results(arguments["run_id"])
        return [TextContent(type="text", text=json.dumps(results, default=str))]

    if name == "generate_report":
        run_id = arguments["run_id"]
        run = get_run(run_id)
        results = get_run_results(run_id)
        scorecard = ReporterAgent().build_scorecard(results)
        text_report = ReporterAgent().format_text_report(scorecard, run["target_name"] if run else "unknown")
        return [TextContent(type="text", text=text_report)]

    raise ValueError(f"Unknown tool: {name}")


async def main():
    init_db()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
