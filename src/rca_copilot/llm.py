"""LLM client for diagnosis reasoning, behind a small mockable interface.

The rest of the app depends on the LLMClient protocol, never on Anthropic
directly — so tests inject a fake and never call a real model (no key, no
cost, deterministic). If no ANTHROPIC_API_KEY is configured, get_llm_client()
returns None and /diagnose falls back to the deterministic baseline.
"""

import os
from functools import lru_cache
from typing import Any, Protocol, cast

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Tool forcing is how we get reliable structured output: the model is required
# to call this tool, so its response conforms to the schema instead of being
# free prose we would have to parse.
_DIAGNOSIS_TOOL: dict[str, Any] = {
    "name": "submit_diagnosis",
    "description": "Submit the root-cause diagnosis for the incident.",
    "input_schema": {
        "type": "object",
        "properties": {
            "root_cause": {
                "type": "string",
                "description": (
                    "The single root-cause label best supported by the evidence, "
                    "chosen from the causes in the retrieved incidents, or "
                    "'insufficient_evidence' if none is justified."
                ),
            },
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "reasoning": {
                "type": "string",
                "description": "1-3 sentences citing the specific evidence behind the call.",
            },
        },
        "required": ["root_cause", "confidence", "reasoning"],
    },
}


class LLMClient(Protocol):
    """Given system + user prompts, return a structured diagnosis dict."""

    async def diagnose(self, *, system: str, user: str) -> dict[str, Any]: ...


class AnthropicClient:
    """LLMClient backed by the Anthropic Messages API using forced tool use."""

    def __init__(self, api_key: str, model: str) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def diagnose(self, *, system: str, user: str) -> dict[str, Any]:
        from anthropic.types import ToolUseBlock

        message = await self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[cast(Any, _DIAGNOSIS_TOOL)],
            tool_choice={"type": "tool", "name": "submit_diagnosis"},
        )
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                return cast(dict[str, Any], block.input)
        return {
            "root_cause": "insufficient_evidence",
            "confidence": "low",
            "reasoning": "The model returned no structured diagnosis.",
        }


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient | None:
    """Return a configured client, or None when no API key is set (use baseline)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return AnthropicClient(api_key=api_key, model=os.environ.get("RCA_LLM_MODEL", _DEFAULT_MODEL))