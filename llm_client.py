"""
Unified LLM client wrapper.

Both Groq and Ollama expose OpenAI-compatible endpoints, so a single client
class handles both — only base_url/api_key/model differ. This is also where
free-tier rate-limit handling lives: a fixed delay between calls plus
exponential backoff on 429s, so the eval suite never needs a paid tier.
"""
import time
import logging
from openai import OpenAI, APIStatusError

from config import get_provider_config, REQUEST_DELAY_SECONDS, MAX_RETRIES, RETRY_BACKOFF_SECONDS

logger = logging.getLogger("sentinelmcp.llm")


class LLMClient:
    def __init__(self, role: str):
        """role: one of 'attacker', 'target', 'judge', 'reporter' — controls which
        provider/model is used for this agent, per config.get_provider_config."""
        self.role = role
        self.cfg = get_provider_config(role)
        # Explicit timeout: the SDK default is several minutes, which is too
        # long to hang on a single call in a suite meant to run unattended.
        self.client = OpenAI(base_url=self.cfg.base_url, api_key=self.cfg.api_key or "unset", timeout=30.0)

    def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 1024) -> str:
        """Send a chat completion request with free-tier-friendly retry/backoff.
        Returns the response text, or raises after exhausting retries."""
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                time.sleep(REQUEST_DELAY_SECONDS)  # pace requests to stay under RPM caps
                resp = self.client.chat.completions.create(
                    model=self.cfg.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return resp.choices[0].message.content or ""
            except APIStatusError as e:
                last_error = e
                if e.status_code == 429:
                    wait = RETRY_BACKOFF_SECONDS * attempt
                    logger.warning(f"[{self.role}] rate limited (attempt {attempt}/{MAX_RETRIES}), backing off {wait}s")
                    time.sleep(wait)
                    continue
                raise
            except Exception as e:  # noqa: BLE001 - surfaced to caller after retries
                last_error = e
                logger.warning(f"[{self.role}] request failed (attempt {attempt}/{MAX_RETRIES}): {e}")
                time.sleep(RETRY_BACKOFF_SECONDS)
        raise RuntimeError(f"[{self.role}] exhausted {MAX_RETRIES} retries: {last_error}")


class FakeLLMClient:
    """Deterministic stand-in used by tests and offline dry-runs so the graph
    logic can be verified without hitting a real API (useful since this sandbox
    can't reach Groq/Ollama, and useful for the user's own CI later)."""

    def __init__(self, role: str, canned_response: str = ""):
        self.role = role
        self.canned_response = canned_response
        self.calls = []

    def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 1024) -> str:
        self.calls.append(messages)
        return self.canned_response
