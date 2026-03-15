from ..config import OPENAI_API_KEY, OPENAI_MODEL


async def chat(
    messages: list[dict],
    provider: str = "openai",
    model: str = "",
    max_tokens: int = 800,
    api_key: str = None,
) -> str:
    """
    Send messages to an LLM and return the response text.
    Supports openai, anthropic, ollama providers.
    """
    if provider == "openai":
        return await _openai_chat(messages, model or OPENAI_MODEL, max_tokens, api_key or OPENAI_API_KEY)
    elif provider == "anthropic":
        return await _anthropic_chat(messages, model or "claude-sonnet-4-20250514", max_tokens, api_key)
    elif provider == "ollama":
        return await _ollama_chat(messages, model or "llama3", max_tokens)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


async def _openai_chat(messages: list[dict], model: str, max_tokens: int, api_key: str) -> str:
    from openai import AsyncOpenAI
    if not api_key:
        raise ValueError("OpenAI API key not configured")
    client = AsyncOpenAI(api_key=api_key)
    resp = await client.chat.completions.create(model=model, max_tokens=max_tokens, messages=messages)
    return resp.choices[0].message.content


async def _anthropic_chat(messages: list[dict], model: str, max_tokens: int, api_key: str) -> str:
    try:
        import anthropic
    except ImportError:
        raise ValueError("anthropic package not installed. Run: pip install anthropic")

    if not api_key:
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("Anthropic API key not configured")

    client = anthropic.AsyncAnthropic(api_key=api_key)

    system = ""
    chat_messages = []
    for m in messages:
        if m["role"] == "system":
            system += m["content"] + "\n"
        else:
            chat_messages.append({"role": m["role"], "content": m["content"]})

    if not chat_messages or chat_messages[0]["role"] != "user":
        chat_messages.insert(0, {"role": "user", "content": "Hello"})

    resp = await client.messages.create(
        model=model, max_tokens=max_tokens,
        system=system.strip() if system else "You are a helpful assistant.",
        messages=chat_messages,
    )
    return resp.content[0].text


async def _ollama_chat(messages: list[dict], model: str, max_tokens: int) -> str:
    import httpx
    import os
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{ollama_url}/api/chat", json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        })
        resp.raise_for_status()
        return resp.json()["message"]["content"]


def list_providers() -> list[dict]:
    """List available LLM providers and their status."""
    import os
    return [
        {"provider": "openai", "configured": bool(OPENAI_API_KEY), "default_model": OPENAI_MODEL or "gpt-4o-mini"},
        {"provider": "anthropic", "configured": bool(os.environ.get("ANTHROPIC_API_KEY", "")), "default_model": "claude-sonnet-4-20250514"},
        {"provider": "ollama", "configured": True, "default_model": "llama3"},
    ]
