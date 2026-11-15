"""Optional OpenAI-compatible LLM, used only when OpenHome is unreachable.

Same persona and the same context as OpenHome. The key never leaves the server.
"""

from __future__ import annotations

import logging

import requests

from config import BASE_DIR, Config

log = logging.getLogger(__name__)
TIMEOUT_S = 20


def persona() -> str:
    return (BASE_DIR / "config" / "dr_nova_persona.md").read_text(encoding="utf-8")


def available(config: Config) -> bool:
    return bool(config.fallback_llm_api_key and config.fallback_llm_base_url and config.fallback_llm_model)


def chat(config: Config, message: str, context_text: str, history: list[dict]) -> str | None:
    """Ask the fallback model. Returns None on any failure (the caller moves on to the rules)."""
    if not available(config):
        return None
    messages = [{"role": "system", "content": persona() + "\n\nThis is TEXT chat.\n\n" + context_text}]
    messages += [{"role": item["role"], "content": item["content"]} for item in history[-10:]]
    messages.append({"role": "user", "content": message})
    try:
        response = requests.post(
            f"{config.fallback_llm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {config.fallback_llm_api_key}"},
            json={"model": config.fallback_llm_model, "messages": messages, "temperature": 0.3, "max_tokens": 400},
            timeout=TIMEOUT_S,
        )
        if response.status_code != 200:
            log.warning("Fallback LLM answered %s", response.status_code)
            return None
        return response.json()["choices"][0]["message"]["content"].strip() or None
    except (requests.RequestException, KeyError, IndexError, ValueError):
        log.warning("Fallback LLM unreachable")
        return None
