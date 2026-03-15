import os
import sys
import json
import asyncio
import logging
import importlib.util
from pathlib import Path

logger = logging.getLogger("hermes.bridge")

# Path to the cloned hermes-agent repo
HERMES_REPO = os.environ.get(
    "HERMES_AGENT_PATH",
    str(Path(__file__).resolve().parents[4] / "hermes-agent-src")
)

_hermes_registry = None


def _import_hermes_registry():
    """Import Hermes ToolRegistry directly from the repo (bypasses heavy deps)."""
    registry_path = os.path.join(HERMES_REPO, "tools", "registry.py")
    if not os.path.exists(registry_path):
        raise ImportError(f"Hermes registry not found at {registry_path}. Set HERMES_AGENT_PATH env var.")

    spec = importlib.util.spec_from_file_location("hermes_tools_registry", registry_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ToolRegistry, mod.registry


def get_hermes_registry():
    """Get the Hermes ToolRegistry singleton with MobHub tools registered."""
    global _hermes_registry
    if _hermes_registry is None:
        ToolRegistry, registry = _import_hermes_registry()
        _hermes_registry = registry
        _register_all_mobhub_tools(_hermes_registry)
        logger.info(f"Hermes registry loaded from {HERMES_REPO}")
        logger.info(f"MobHub tools registered: {_hermes_registry.get_all_tool_names()}")
    return _hermes_registry


def _run_async_handler(coro):
    """Bridge async MobHub handlers to sync Hermes handler contract."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=60)
    except RuntimeError:
        return asyncio.run(coro)


def _register_all_mobhub_tools(registry):
    """Register all MobHub tools into the Hermes registry."""
    from .tools import SCHEMAS, _HANDLERS, check_mobhub_requirements

    for tool_name, schema in SCHEMAS.items():
        async_handler = _HANDLERS.get(tool_name)
        if not async_handler:
            continue

        # Wrap async handler for Hermes sync dispatch
        def make_sync_handler(ah):
            def handler(args, **kwargs):
                return _run_async_handler(ah(args))
            return handler

        registry.register(
            name=tool_name,
            toolset="mobhub",
            schema=schema,
            handler=make_sync_handler(async_handler),
            check_fn=check_mobhub_requirements,
            is_async=False,
            description=schema.get("description", ""),
        )

    logger.info(f"Registered {len(SCHEMAS)} MobHub tools into Hermes registry")


def get_tool_definitions() -> list:
    """Get MobHub tool definitions in Hermes/OpenAI format."""
    from .tools import SCHEMAS
    # Build definitions directly from schemas (bypasses check_fn for dev)
    return [
        {"type": "function", "function": schema}
        for schema in SCHEMAS.values()
    ]


def dispatch_tool(tool_name: str, args: dict) -> str:
    """Dispatch a tool call through the Hermes registry."""
    registry = get_hermes_registry()
    return registry.dispatch(tool_name, args)
