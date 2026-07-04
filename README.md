<div align="center">
 
# SentinelMCP

**An automated red-teaming and reliability-auditing platform for AI agents, exposed as an MCP server.**

Most agent projects show an agent *doing* a task. SentinelMCP does the opposite: it's a multi-agent system whose job is to attack and score other agents — checking them for prompt injection, tool misuse, prompt/data exfiltration, and unreliable behavior under adversarial pressure — then reports the results as a reliability scorecard.

![sentinelmcp Banner](https://raw.githubusercontent.com/MusaIslamFahad/sentinelmcp/main/assets/banner.jpg)

Runs entirely on free-tier infrastructure. No credit card required.

</div>

---

## Architecture

Four agents, orchestrated with LangGraph:

```
┌───────────┐     ┌───────────┐     ┌──────────┐     ┌───────────┐
│ Attacker  │ ──▶ │  Target   │ ──▶ │  Judge   │ ──▶ │ Reporter  │
│  agent    │     │  agent    │     │  agent   │     │  agent    │
└───────────┘     └───────────┘     └──────────┘     └───────────┘
 selects/mutates    system under      scores vs.        aggregates
 adversarial         test (your       rubric, JSON       into scorecard,
 test case           agent or the     verdict             flags high-
                     sample one)                          severity fails
```

- **Attacker** — plays back a curated adversarial prompt, or (optionally) has an LLM paraphrase it into a fresh variant.
- **Target** — the agent under test. Ships with a sample customer-support agent (with mock sensitive tools: refund, delete account, update order, get customer data) so you can run the suite immediately. Swap in your own agent by implementing `run(prompt, context) -> {"response_text": ..., "tool_called": ...}`.
- **Judge** — LLM-as-judge, forced into strict JSON output and validated with pydantic. Tool-hijacking verdicts are additionally checked deterministically (if the target tool actually fired, that overrides the LLM's opinion — an objective signal shouldn't be left to LLM judgment alone).
- **Reporter** — pure aggregation, no LLM call. Produces per-category success rates and flags high-severity failures.

All of this is also exposed as an **MCP server** (`mcp_server/server.py`) with four tools: `run_injection_suite`, `score_trajectory`, `generate_report`, `list_attack_categories` — so any MCP-compatible client can trigger an audit without knowing anything about the internals.

## Attack taxonomy

8 categories, 24 seed test cases (3 each), defined in `eval/taxonomy.py` and `eval/test_cases.py`:

| Category | What it tests |
|---|---|
| `direct_injection` | "Ignore your instructions" style prompts |
| `indirect_injection` | Malicious instructions hidden inside "retrieved" documents/tickets |
| `tool_hijacking` | Attempts to trigger refunds, deletions, etc. without authorization |
| `role_confusion` | Attacker impersonates system/admin/developer |
| `prompt_exfiltration` | Attempts to extract the system prompt verbatim |
| `data_exfiltration` | Attempts to extract other users' PII |
| `context_overflow` | Burying the real instruction under padding text |
| `contradiction_pressure` | Conflicting instructions to see which one wins |

Extend `eval/test_cases.py` to grow the suite, or run with `--mutate` to have the Attacker LLM generate paraphrased variants at runtime.

---

## Running it for free

Every piece of infrastructure here (LangGraph, FastAPI, SQLite, Streamlit, Docker) is free with no caveats. The only thing that costs money by default is LLM inference — here's how to keep that at $0 too.

### Option A: Groq free tier (recommended — fast, no local setup)

1. Sign up at [console.groq.com](https://console.groq.com) — no credit card needed.
2. Generate an API key.
3. `cp .env.example .env` and set `GROQ_API_KEY`.

Groq's free tier gives ~30 requests/minute and a generous daily token allowance across open models like Llama 3.3 70B — plenty for this suite. The project paces requests automatically (`REQUEST_DELAY_SECONDS` in `.env`) to stay under the per-minute cap, and retries with backoff on 429s.

### Option B: Ollama (fully local, zero rate limits)

1. Install [Ollama](https://ollama.com).
2. `ollama pull llama3.1`
3. In `.env`, set `TARGET_PROVIDER=ollama` (or `DEFAULT_PROVIDER=ollama` to run everything locally).

### Recommended split

Run the Target locally on Ollama and the Attacker/Judge/Reporter on Groq — so you're not spending your Groq quota testing both sides of the fight. This is the default in `.env.example`.

---

## Setup

```bash
git clone <this-repo>
cd sentinelmcp
pip install -r requirements.txt
cp .env.example .env   # then fill in GROQ_API_KEY (or set up Ollama)
```

## Usage

**Run the full suite against the sample target agent:**
```bash
python main.py --target "support-agent-v1"
```

**Run only specific categories:**
```bash
python main.py --target "support-agent-v1" --category tool_hijacking direct_injection
```

**Use LLM-generated paraphrased variants instead of the static seed prompts:**
```bash
python main.py --target "support-agent-v1" --mutate
```

**View results in the dashboard:**
```bash
streamlit run dashboard/app.py
```

**Run as an MCP server:**
```bash
python -m mcp_server.server
```
Then point any MCP-compatible client at it and call `run_injection_suite`, `score_trajectory`, or `generate_report`.

**Run with Docker:**
```bash
docker compose up
```

**Run the offline test suite** (no API keys needed — uses a fake LLM client to verify all orchestration logic):
```bash
pytest tests/ -v
```

---

## Testing against your own agent

Replace `agents/target.py`'s `TargetAgent` with a wrapper around your real agent. The only contract that matters:

```python
class TargetAgent:
    def run(self, prompt: str, context: str = "") -> dict:
        # ... call your real agent here ...
        return {"response_text": "...", "tool_called": "tool_name_or_None"}
```

Then run `python main.py --target "my-real-agent"` as usual.

## Project structure

```
sentinelmcp/
├── main.py                 # CLI entry point
├── config.py                # provider/model configuration
├── llm_client.py             # unified Groq/Ollama client with rate-limit handling
├── agents/
│   ├── attacker.py
│   ├── target.py            # sample target agent + mock sensitive tools
│   ├── judge.py              # LLM-as-judge with strict JSON rubric
│   ├── reporter.py           # aggregation, no LLM call
│   └── graph.py               # LangGraph orchestration
├── eval/
│   ├── taxonomy.py           # attack categories + severity weights
│   └── test_cases.py         # 24 seed adversarial test cases
├── mcp_server/
│   └── server.py              # MCP server exposing the suite as tools
├── storage/
│   └── db.py                  # SQLite persistence
├── dashboard/
│   └── app.py                  # Streamlit reliability dashboard
└── tests/
    └── test_basic.py           # offline tests (fake LLM client, no API needed)
```

## Extending this project

- **Grow the test bank** past 24 cases — add to `eval/test_cases.py`, or rely on `--mutate` to generate variants.
- **Add new attack categories** in `eval/taxonomy.py`.
- **Add an explainability layer** — attribute *which part* of a long/adversarial prompt triggered a deviation (a natural next step, and a nice callback if you've done SHAP/Grad-CAM work elsewhere).
- **Swap SQLite for Postgres** if you need concurrent writers — `storage/db.py` is intentionally the only file that would need to change.
- **Publish the MCP server** so others can plug it into their own agent stack via `npx`/`uvx`.
