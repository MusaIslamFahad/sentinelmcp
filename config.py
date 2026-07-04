"""
Central configuration for SentinelMCP.

All model access goes through env vars so the whole project can run for
free on Groq's free tier or a local Ollama install — no code changes needed
to switch providers.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str


def _groq_config() -> ProviderConfig:
    return ProviderConfig(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key=os.getenv("GROQ_API_KEY", ""),
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    )


def _ollama_config() -> ProviderConfig:
    return ProviderConfig(
        name="ollama",
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key="ollama",  # Ollama's OpenAI-compat endpoint ignores this but the SDK requires a value
        model=os.getenv("OLLAMA_MODEL", "llama3.1"),
    )


def get_provider_config(role: str) -> ProviderConfig:
    """
    Returns provider config for a given agent role (attacker/target/judge/reporter).

    Lets you deliberately split load across providers so you don't burn one
    provider's free-tier quota on both sides of the red-team exercise, e.g.:
        ATTACKER_PROVIDER=groq
        TARGET_PROVIDER=ollama
        JUDGE_PROVIDER=groq
        REPORTER_PROVIDER=groq
    """
    provider = os.getenv(f"{role.upper()}_PROVIDER", os.getenv("DEFAULT_PROVIDER", "groq")).lower()
    if provider == "ollama":
        return _ollama_config()
    return _groq_config()


# Rate-limit-friendly defaults for Groq's free tier (30 RPM / 6-12K TPM depending on model).
# See README for details — these are conservative on purpose.
REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "2.5"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_BACKOFF_SECONDS = float(os.getenv("RETRY_BACKOFF_SECONDS", "5"))

DB_PATH = os.getenv("SENTINEL_DB_PATH", "sentinel.db")
