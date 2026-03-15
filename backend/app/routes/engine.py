from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/engine", tags=["engine"])



def _runtime():
    from ..engine.singleton import get_runtime
    return get_runtime()



class SpawnHubRequest(BaseModel):
    hub_id: str
    hub_name: str
    topic: str = ""


class InstructionRequest(BaseModel):
    text: str
    target_agent_id: str | None = None



@router.post("/hubs/{hub_id}/spawn")
async def spawn_hub_agents(hub_id: str, req: SpawnHubRequest):
    rt = _runtime()
    agents = await rt.spawn_hub_agents(hub_id, req.hub_name, req.topic)
    return {"agents": [a.to_dict() for a in agents]}


@router.delete("/hubs/{hub_id}/agents")
async def retire_hub_agents(hub_id: str):
    rt = _runtime()
    await rt.retire_hub_agents(hub_id)
    return {"status": "retired"}


@router.get("/hubs/{hub_id}/agents")
async def get_hub_agents(hub_id: str):
    rt = _runtime()
    agents = rt.get_hub_agents(hub_id)
    return {"agents": [a.to_dict() for a in agents]}



@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    rt = _runtime()
    agent = rt.get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent.to_dict()


@router.post("/agents/{agent_id}/pause")
async def pause_agent(agent_id: str):
    rt = _runtime()
    await rt.pause_agent(agent_id)
    return {"status": "paused"}


@router.post("/agents/{agent_id}/resume")
async def resume_agent(agent_id: str):
    rt = _runtime()
    await rt.resume_agent(agent_id)
    return {"status": "resumed"}


@router.post("/hubs/{hub_id}/pause")
async def pause_hub(hub_id: str):
    rt = _runtime()
    await rt.pause_hub(hub_id)
    return {"status": "paused"}


@router.post("/hubs/{hub_id}/resume")
async def resume_hub(hub_id: str):
    rt = _runtime()
    await rt.resume_hub(hub_id)
    return {"status": "resumed"}


@router.post("/hubs/{hub_id}/stop")
async def stop_hub(hub_id: str):
    """Hard stop — pause all agents and drain the event queue for this hub."""
    rt = _runtime()
    await rt.stop_hub(hub_id)
    agents = rt.get_hub_agents(hub_id)
    return {
        "status": "stopped",
        "agents_paused": len(agents),
    }


@router.delete("/hubs/{hub_id}/kill")
async def kill_hub_agents(hub_id: str):
    """Kill — unregister all agents, remove all subscriptions. Nuclear option."""
    rt = _runtime()
    agents = rt.get_hub_agents(hub_id)
    count = len(agents)
    await rt.retire_hub_agents(hub_id)
    return {
        "status": "killed",
        "agents_removed": count,
    }



@router.post("/hubs/{hub_id}/instruct")
async def send_instruction(hub_id: str, req: InstructionRequest):
    rt = _runtime()
    await rt.send_instruction(hub_id, req.text, req.target_agent_id)
    return {"status": "sent"}



@router.get("/hubs/{hub_id}/actions")
async def get_action_log(hub_id: str, limit: int = 50):
    rt = _runtime()
    return {"actions": rt.get_action_log(hub_id, limit)}


@router.get("/hubs/{hub_id}/events")
async def get_event_history(hub_id: str, limit: int = 50):
    rt = _runtime()
    return {"events": rt.event_bus.get_history(hub_id, limit)}



@router.get("/status")
async def engine_status():
    rt = _runtime()
    return {
        "started": rt._started,
        "total_agents": len(rt._agents),
        "hubs_active": len(rt._hub_agents),
        "events_pending": rt.event_bus.pending,
        "tools_available": rt.tools.list_tools() if rt.tools else [],
    }



@router.websocket("/hubs/{hub_id}/ws")
async def websocket_live_log(websocket: WebSocket, hub_id: str):
    """WebSocket endpoint for real-time agent action stream."""
    rt = _runtime()
    await websocket.accept()
    rt.add_ws_connection(hub_id, websocket)

    try:
        # Send current agent state on connect
        agents = rt.get_hub_agents(hub_id)
        await websocket.send_json({
            "type": "init",
            "agents": [a.to_dict() for a in agents],
        })

        # Keep connection alive, handle incoming messages
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "instruction":
                await rt.send_instruction(hub_id, data.get("text", ""), data.get("target_agent_id"))
            elif msg_type == "pause_agent":
                await rt.pause_agent(data.get("agent_id", ""))
            elif msg_type == "resume_agent":
                await rt.resume_agent(data.get("agent_id", ""))
            elif msg_type == "pause_all":
                await rt.pause_hub(hub_id)
            elif msg_type == "resume_all":
                await rt.resume_hub(hub_id)
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        rt.remove_ws_connection(hub_id, websocket)
    except Exception:
        rt.remove_ws_connection(hub_id, websocket)
