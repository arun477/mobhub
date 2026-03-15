from .runtime import AgentRuntime

_runtime: AgentRuntime | None = None


def get_runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AgentRuntime()
    return _runtime


async def start_runtime():
    rt = get_runtime()
    await rt.start()
    return rt


async def stop_runtime():
    global _runtime
    if _runtime:
        await _runtime.stop()
        _runtime = None
