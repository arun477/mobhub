import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from ..db import get_db
from ..models import Hub, HubMember, HubSkill, SkillExecution, Agent, Activity
from ..services import skills as skill_service
from .auth import get_current_agent

router = APIRouter(prefix="/api/hubs/{hub_id}/skills", tags=["skills"])


class AddSkillRequest(BaseModel):
    skill_type: str
    name: Optional[str] = None
    config: Optional[dict] = None


class UpdateSkillRequest(BaseModel):
    enabled: Optional[bool] = None
    config: Optional[dict] = None


class ExecuteSkillRequest(BaseModel):
    input: dict



@router.get("")
async def list_skills(hub_id: str, db: AsyncSession = Depends(get_db)):
    """List all skills for this hub."""
    result = await db.execute(
        select(HubSkill).where(HubSkill.hub_id == hub_id).order_by(HubSkill.created_at)
    )
    skills = result.scalars().all()

    # Also include available skill types for reference
    available = skill_service.list_available_skills()
    available_types = {s["skill_type"] for s in available}
    installed_types = {s.skill_type for s in skills}

    return {
        "installed": [
            {
                "id": s.id, "skill_type": s.skill_type, "name": s.name,
                "description": s.description, "enabled": s.enabled,
                "config": json.loads(s.config_json) if s.config_json else {},
                "created_at": s.created_at.isoformat(),
            }
            for s in skills
        ],
        "available": [s for s in available if s["skill_type"] not in installed_types],
    }


@router.post("")
async def add_skill(
    hub_id: str, req: AddSkillRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Add a skill to the hub."""
    member = await db.get(HubMember, (hub_id, agent.id))
    if not member:
        raise HTTPException(403, "Not a member")

    handler = skill_service.get_skill_handler(req.skill_type)
    if not handler:
        raise HTTPException(400, f"Unknown skill type: {req.skill_type}")

    skill = HubSkill(
        hub_id=hub_id, skill_type=req.skill_type,
        name=req.name or handler.name,
        description=handler.description,
        config_json=json.dumps(req.config or {}),
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)

    return {"id": skill.id, "skill_type": skill.skill_type, "name": skill.name, "status": "added"}


@router.patch("/{skill_id}")
async def update_skill(
    hub_id: str, skill_id: str, req: UpdateSkillRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Update skill config or enabled status."""
    skill = await db.get(HubSkill, skill_id)
    if not skill or skill.hub_id != hub_id:
        raise HTTPException(404, "Skill not found")

    if req.enabled is not None:
        skill.enabled = req.enabled
    if req.config is not None:
        skill.config_json = json.dumps(req.config)

    await db.commit()
    return {"id": skill.id, "enabled": skill.enabled, "status": "updated"}


@router.delete("/{skill_id}")
async def remove_skill(
    hub_id: str, skill_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Remove a skill from the hub."""
    skill = await db.get(HubSkill, skill_id)
    if not skill or skill.hub_id != hub_id:
        raise HTTPException(404, "Skill not found")
    await db.delete(skill)
    await db.commit()
    return {"status": "removed"}



@router.post("/{skill_id}/execute")
async def execute_skill(
    hub_id: str, skill_id: str, req: ExecuteSkillRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Execute a skill and return results."""
    member = await db.get(HubMember, (hub_id, agent.id))
    if not member:
        raise HTTPException(403, "Not a member")

    skill = await db.get(HubSkill, skill_id)
    if not skill or skill.hub_id != hub_id:
        raise HTTPException(404, "Skill not found")
    if not skill.enabled:
        raise HTTPException(400, "Skill is disabled")

    # Merge skill config with hub_id for skills that need it
    config = json.loads(skill.config_json) if skill.config_json else {}
    config["hub_id"] = hub_id

    # Execute
    result = await skill_service.execute_skill(skill.skill_type, req.input, config)

    # Track execution
    duration = result.pop("_duration_ms", None)
    has_error = "error" in result and result["error"]

    execution = SkillExecution(
        hub_id=hub_id, skill_id=skill_id, agent_id=agent.id,
        input_json=json.dumps(req.input), output_json=json.dumps(result),
        status="failed" if has_error else "completed",
        error=result.get("error") if has_error else None,
        duration_ms=duration,
    )
    db.add(execution)
    await db.commit()

    return {
        "execution_id": execution.id,
        "skill_type": skill.skill_type,
        "status": execution.status,
        "duration_ms": duration,
        "result": result,
    }


@router.get("/executions")
async def list_executions(
    hub_id: str, limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List recent skill executions."""
    result = await db.execute(
        select(SkillExecution, HubSkill.name.label("skill_name"), Agent.name.label("agent_name"))
        .join(HubSkill, HubSkill.id == SkillExecution.skill_id)
        .outerjoin(Agent, Agent.id == SkillExecution.agent_id)
        .where(SkillExecution.hub_id == hub_id)
        .order_by(SkillExecution.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": e.id, "skill_name": sname, "agent_name": aname or "",
            "status": e.status, "duration_ms": e.duration_ms,
            "input": json.loads(e.input_json) if e.input_json else {},
            "error": e.error,
            "created_at": e.created_at.isoformat(),
        }
        for e, sname, aname in result.all()
    ]



async def auto_provision_skills(hub_id: str, db: AsyncSession):
    """Add default skills to a newly created hub."""
    for skill_type in skill_service.DEFAULT_SKILLS:
        handler = skill_service.get_skill_handler(skill_type)
        if handler:
            db.add(HubSkill(
                hub_id=hub_id, skill_type=skill_type,
                name=handler.name, description=handler.description,
            ))
