import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import Optional
from ..db import get_db
from ..models import Agent, AgentMemory, HubSkill, HubMember
from ..services import llm
from .auth import get_current_agent

router = APIRouter(prefix="/api/agents", tags=["agents"])


class RegisterRequest(BaseModel):
    name: str
    agent_type: str = "custom"
    description: str = ""
    llm_provider: str = "openai"
    llm_model: str = ""
    required_skills: list[str] = []


class AuthRequest(BaseModel):
    api_key: str


class UpdateProfileRequest(BaseModel):
    description: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    required_skills: Optional[list[str]] = None


class MemoryWriteRequest(BaseModel):
    hub_id: str
    key: str
    value: dict | list | str | int | float | bool


class SpawnRequest(BaseModel):
    name: str
    agent_type: str = "sub_agent"
    description: str = ""



@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    agent = Agent(
        name=req.name, agent_type=req.agent_type, description=req.description,
        llm_provider=req.llm_provider, llm_model=req.llm_model,
        required_skills_json=json.dumps(req.required_skills),
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return _agent_dict(agent, include_key=True)


@router.post("/auth")
async def auth(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.api_key == req.api_key))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(401, "Invalid API key")
    return _agent_dict(agent)



@router.get("/me")
async def get_profile(agent: Agent = Depends(get_current_agent)):
    return _agent_dict(agent)


@router.patch("/me")
async def update_profile(
    req: UpdateProfileRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    if req.description is not None:
        agent.description = req.description
    if req.llm_provider is not None:
        agent.llm_provider = req.llm_provider
    if req.llm_model is not None:
        agent.llm_model = req.llm_model
    if req.required_skills is not None:
        agent.required_skills_json = json.dumps(req.required_skills)
    await db.commit()
    return _agent_dict(agent)


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return _agent_dict(agent)



@router.post("/me/spawn")
async def spawn_agent(
    req: SpawnRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Spawn a sub-agent. Returns the new agent's credentials."""
    child = Agent(
        name=req.name, agent_type=req.agent_type, description=req.description,
        llm_provider=agent.llm_provider, llm_model=agent.llm_model,
        parent_agent_id=agent.id,
    )
    db.add(child)
    await db.commit()
    await db.refresh(child)
    return _agent_dict(child, include_key=True)


@router.get("/me/children")
async def list_children(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.parent_agent_id == agent.id))
    return [_agent_dict(a) for a in result.scalars().all()]



@router.get("/providers")
async def get_providers():
    """List available LLM providers."""
    return llm.list_providers()



@router.get("/me/memory")
async def get_memory(
    hub_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentMemory)
        .where(AgentMemory.agent_id == agent.id, AgentMemory.hub_id == hub_id)
        .order_by(AgentMemory.key)
    )
    memory = {}
    for r in result.scalars().all():
        try:
            memory[r.key] = json.loads(r.value)
        except (json.JSONDecodeError, TypeError):
            memory[r.key] = r.value
    return {"agent_id": agent.id, "hub_id": hub_id, "memory": memory}


@router.get("/me/memory/{key}")
async def get_memory_key(
    key: str, hub_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentMemory).where(
            AgentMemory.agent_id == agent.id, AgentMemory.hub_id == hub_id, AgentMemory.key == key,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Memory key not found")
    try:
        value = json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        value = row.value
    return {"key": key, "value": value, "updated_at": row.updated_at.isoformat()}


@router.put("/me/memory")
async def write_memory(
    req: MemoryWriteRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentMemory).where(
            AgentMemory.agent_id == agent.id, AgentMemory.hub_id == req.hub_id, AgentMemory.key == req.key,
        )
    )
    existing = result.scalar_one_or_none()
    serialized = json.dumps(req.value)
    if existing:
        existing.value = serialized
    else:
        db.add(AgentMemory(agent_id=agent.id, hub_id=req.hub_id, key=req.key, value=serialized))
    await db.commit()
    return {"status": "saved", "key": req.key}


@router.delete("/me/memory/{key}")
async def delete_memory_key(
    key: str, hub_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentMemory).where(
            AgentMemory.agent_id == agent.id, AgentMemory.hub_id == hub_id, AgentMemory.key == key,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
    return {"status": "deleted", "key": key}



def _agent_dict(agent: Agent, include_key: bool = False) -> dict:
    d = {
        "id": agent.id, "name": agent.name,
        "agent_type": agent.agent_type, "description": agent.description,
        "llm_provider": agent.llm_provider, "llm_model": agent.llm_model,
        "parent_agent_id": agent.parent_agent_id,
        "required_skills": json.loads(agent.required_skills_json) if agent.required_skills_json else [],
        "created_at": agent.created_at.isoformat(),
    }
    if include_key:
        d["api_key"] = agent.api_key
    return d
