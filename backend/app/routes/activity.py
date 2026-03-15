from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..db import get_db
from ..models import Activity, Agent, Hub

router = APIRouter(prefix="/api", tags=["activity"])


@router.get("/activity")
async def global_activity(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Activity, Agent.name.label("agent_name"))
        .outerjoin(Agent, Agent.id == Activity.agent_id)
        .order_by(Activity.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": a.id,
            "hub_id": a.hub_id,
            "agent_id": a.agent_id,
            "agent_name": name or "",
            "action": a.action,
            "detail": a.detail,
            "created_at": a.created_at.isoformat(),
        }
        for a, name in result.all()
    ]


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    agents = (await db.execute(func.count(Agent.id))).scalar() or 0
    hubs = (await db.execute(func.count(Hub.id))).scalar() or 0
    events = (await db.execute(func.count(Activity.id))).scalar() or 0
    return {"agents": agents, "hubs": hubs, "events": events}
