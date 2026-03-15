from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/hermes", tags=["hermes"])


class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict = {}


class AgentRequest(BaseModel):
    message: str
    hub_id: str | None = None
    personality: str = "You are a helpful AI agent with access to MobHub knowledge tools. Use tools to research, build, and query knowledge hubs."
    tool_names: list[str] | None = None


@router.get("/tools")
async def list_tools():
    """List all available MobHub tools in Hermes schema format."""
    from ..hermes.tools import get_all_schemas
    return {"tools": get_all_schemas(), "toolset": "mobhub"}


@router.post("/call")
async def call_tool(req: ToolCallRequest):
    """Execute a MobHub tool through the Hermes registry."""
    import json
    from ..hermes.bridge import dispatch_tool

    try:
        result_json = dispatch_tool(req.tool_name, req.arguments)
        return json.loads(result_json) if isinstance(result_json, str) else result_json
    except Exception as e:
        return {"error": str(e)}


@router.post("/agent")
async def run_agent(req: AgentRequest):
    """
    Run a Hermes-style agent conversation.
    The agent uses MobHub tools to fulfill the request autonomously.

    Example:
        POST /api/hermes/agent
        {"message": "Create a hub about Tesla and tell me who the key people are"}
    """
    from ..hermes.agent_loop import create_agent_loop

    loop = await create_agent_loop(
        personality=req.personality,
        hub_id=req.hub_id or "",
        tool_names=req.tool_names,
    )

    result = await loop.run(req.message)
    return result


@router.get("/status")
async def hermes_status():
    """Check MobHub readiness for Hermes integration."""
    from ..hermes.tools import check_mobhub_requirements, get_all_schemas
    from ..engine.singleton import get_runtime

    rt = get_runtime()
    return {
        "ready": check_mobhub_requirements(),
        "engine_running": rt._started,
        "tools_available": len(get_all_schemas()),
        "active_hubs": len(rt._hub_agents),
        "total_agents": len(rt._agents),
    }
