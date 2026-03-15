import json
import time
import logging
from typing import Any

logger = logging.getLogger("hermes.agent_loop")


class HermesAgentLoop:
    """
    Lightweight Hermes-compatible agent loop.
    Same LLM+tool pattern as AIAgent.run_conversation() but without
    the full Hermes CLI dependencies.
    """

    def __init__(
        self,
        system_prompt: str,
        tool_definitions: list[dict],  # OpenAI format: [{"type": "function", "function": {...}}]
        max_iterations: int = 15,
        model: str = "",
        provider: str = "openai",
    ):
        self.system_prompt = system_prompt
        self.tool_definitions = tool_definitions
        self.max_iterations = max_iterations
        self.model = model
        self.provider = provider

    async def run(self, user_message: str) -> dict:
        """
        Run a complete conversation with tool calling until the LLM
        produces a final text response (no more tool calls).

        Returns: {"response": str, "tool_calls": list, "iterations": int}
        """
        from ..config import OPENAI_API_KEY, OPENAI_MODEL
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        model = self.model or OPENAI_MODEL or "gpt-4o-mini"

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

        tool_calls_log = []
        iterations = 0

        while iterations < self.max_iterations:
            iterations += 1

            try:
                # Call LLM with function calling tools
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": 1500,
                }
                if self.tool_definitions:
                    kwargs["tools"] = self.tool_definitions
                    kwargs["tool_choice"] = "auto"

                response = await client.chat.completions.create(**kwargs)
                choice = response.choices[0]
                message = choice.message

            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                return {"response": f"LLM error: {e}", "tool_calls": tool_calls_log, "iterations": iterations}

            # Check if the model wants to call tools
            if message.tool_calls:
                # Append the assistant message with tool calls
                messages.append(message.model_dump())

                # Execute each tool call via Hermes registry
                for tool_call in message.tool_calls:
                    fn_name = tool_call.function.name
                    try:
                        fn_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        fn_args = {}

                    logger.info(f"Tool call: {fn_name}({json.dumps(fn_args)[:80]})")

                    # Dispatch through the real Hermes registry
                    start_time = time.time()
                    try:
                        from .bridge import dispatch_tool
                        result = dispatch_tool(fn_name, fn_args)
                    except Exception as e:
                        result = json.dumps({"error": str(e)})
                    duration = time.time() - start_time

                    tool_calls_log.append({
                        "tool": fn_name,
                        "args": fn_args,
                        "result_preview": str(result)[:200],
                        "duration_ms": int(duration * 1000),
                    })

                    # Append tool result to conversation
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(result)[:3000],
                    })
            else:
                # No tool calls — final text response
                return {
                    "response": message.content or "",
                    "tool_calls": tool_calls_log,
                    "iterations": iterations,
                }

        return {
            "response": "Max iterations reached",
            "tool_calls": tool_calls_log,
            "iterations": iterations,
        }


async def create_agent_loop(
    personality: str,
    hub_id: str = "",
    tool_names: list[str] = None,
    model: str = "",
) -> HermesAgentLoop:
    """
    Create a Hermes-style agent loop with MobHub tools
    dispatched through the real Hermes ToolRegistry.
    """
    from .bridge import get_hermes_registry, get_tool_definitions

    # Get tool definitions in OpenAI format from Hermes registry
    defs = get_tool_definitions()

    if tool_names:
        defs = [d for d in defs if d["function"]["name"] in tool_names]

    return HermesAgentLoop(
        system_prompt=personality,
        tool_definitions=defs,
        model=model,
    )
