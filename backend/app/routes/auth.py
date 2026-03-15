from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..db import get_db
from ..models import Agent

security = HTTPBearer(auto_error=False)


async def get_current_agent(
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    if not creds:
        raise HTTPException(401, "Missing authorization")
    result = await db.execute(select(Agent).where(Agent.api_key == creds.credentials))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(401, "Invalid API key")
    return agent
