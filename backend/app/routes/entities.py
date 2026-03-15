import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from pydantic import BaseModel
from typing import Optional
from ..db import get_db
from ..models import EntityAsset, EntityMeta, HubMember, Agent, Provenance, Vote
from ..services import graph
from .auth import get_current_agent

router = APIRouter(prefix="/api/hubs/{hub_id}/graph/entity/{node_uuid}", tags=["entities"])


class AddAssetRequest(BaseModel):
    asset_type: str  # file, url, image, code_snippet, note
    name: str
    content: str = ""
    mime_type: Optional[str] = None


class SetMetaRequest(BaseModel):
    key: str
    value: str



@router.get("/detail")
async def get_entity_detail(hub_id: str, node_uuid: str, db: AsyncSession = Depends(get_db)):
    """Get full entity detail: neighbors, assets, metadata, provenance, votes."""
    # Node + neighbors from Neo4j
    node_data = await graph.get_node_neighbors(hub_id, node_uuid)
    if not node_data:
        raise HTTPException(404, "Entity not found")

    # Assets
    asset_result = await db.execute(
        select(EntityAsset).where(EntityAsset.hub_id == hub_id, EntityAsset.node_uuid == node_uuid)
        .order_by(EntityAsset.created_at.desc())
    )
    assets = [
        {"id": a.id, "asset_type": a.asset_type, "name": a.name,
         "content": a.content[:200] if a.asset_type == "note" else a.content,
         "mime_type": a.mime_type, "size_bytes": a.size_bytes,
         "created_at": a.created_at.isoformat()}
        for a in asset_result.scalars().all()
    ]

    # Metadata
    meta_result = await db.execute(
        select(EntityMeta).where(EntityMeta.hub_id == hub_id, EntityMeta.node_uuid == node_uuid)
        .order_by(EntityMeta.key)
    )
    metadata = {m.key: m.value for m in meta_result.scalars().all()}

    # Provenance
    prov_result = await db.execute(
        select(Provenance, Agent.name.label("agent_name"))
        .outerjoin(Agent, Agent.id == Provenance.agent_id)
        .where(Provenance.hub_id == hub_id, Provenance.node_uuid == node_uuid)
        .order_by(Provenance.created_at.desc())
    )
    provenance = [
        {"source_type": p.source_type, "agent_name": name or "", "episode_name": p.episode_name,
         "paper_title": p.paper_title, "created_at": p.created_at.isoformat()}
        for p, name in prov_result.all()
    ]

    # Votes
    vote_result = await db.execute(
        select(Vote, Agent.name.label("agent_name"))
        .outerjoin(Agent, Agent.id == Vote.agent_id)
        .where(Vote.hub_id == hub_id, Vote.node_uuid == node_uuid)
    )
    votes_raw = vote_result.all()
    votes = [
        {"agent_name": name or "", "vote": v.vote, "reason": v.reason, "created_at": v.created_at.isoformat()}
        for v, name in votes_raw
    ]
    vote_counts = {}
    for v, _ in votes_raw:
        vote_counts[v.vote] = vote_counts.get(v.vote, 0) + 1
    total = sum(vote_counts.values())
    confidence = None
    if total > 0:
        confidence = round(max(0, min(1, (vote_counts.get("agree", 0) - vote_counts.get("disagree", 0) + total) / (2 * total))), 2)

    return {
        **node_data,
        "assets": assets,
        "asset_count": len(assets),
        "metadata": metadata,
        "provenance": provenance,
        "provenance_count": len(provenance),
        "votes": votes,
        "vote_counts": vote_counts,
        "confidence": confidence,
    }



@router.get("/assets")
async def list_assets(hub_id: str, node_uuid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EntityAsset, Agent.name.label("created_by_name"))
        .outerjoin(Agent, Agent.id == EntityAsset.created_by)
        .where(EntityAsset.hub_id == hub_id, EntityAsset.node_uuid == node_uuid)
        .order_by(EntityAsset.created_at.desc())
    )
    return [
        {"id": a.id, "asset_type": a.asset_type, "name": a.name, "content": a.content,
         "mime_type": a.mime_type, "size_bytes": a.size_bytes,
         "created_by": name or "", "created_at": a.created_at.isoformat()}
        for a, name in result.all()
    ]


@router.post("/assets")
async def add_asset(
    hub_id: str, node_uuid: str, req: AddAssetRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(HubMember, (hub_id, agent.id))
    if not member:
        raise HTTPException(403, "Not a member")

    asset = EntityAsset(
        hub_id=hub_id, node_uuid=node_uuid,
        asset_type=req.asset_type, name=req.name, content=req.content,
        mime_type=req.mime_type, size_bytes=len(req.content.encode()) if req.content else 0,
        created_by=agent.id,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return {"id": asset.id, "status": "added"}


@router.delete("/assets/{asset_id}")
async def remove_asset(
    hub_id: str, node_uuid: str, asset_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(EntityAsset, asset_id)
    if not asset or asset.hub_id != hub_id or asset.node_uuid != node_uuid:
        raise HTTPException(404, "Asset not found")
    await db.delete(asset)
    await db.commit()
    return {"status": "removed"}



@router.get("/meta")
async def get_meta(hub_id: str, node_uuid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EntityMeta)
        .where(EntityMeta.hub_id == hub_id, EntityMeta.node_uuid == node_uuid)
        .order_by(EntityMeta.key)
    )
    return {m.key: m.value for m in result.scalars().all()}


@router.put("/meta")
async def set_meta(
    hub_id: str, node_uuid: str, req: SetMetaRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(HubMember, (hub_id, agent.id))
    if not member:
        raise HTTPException(403, "Not a member")

    # Upsert
    result = await db.execute(
        select(EntityMeta).where(
            EntityMeta.hub_id == hub_id, EntityMeta.node_uuid == node_uuid, EntityMeta.key == req.key
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = req.value
    else:
        db.add(EntityMeta(hub_id=hub_id, node_uuid=node_uuid, key=req.key, value=req.value))
    await db.commit()
    return {"status": "saved", "key": req.key}


@router.delete("/meta/{key}")
async def delete_meta(
    hub_id: str, node_uuid: str, key: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EntityMeta).where(
            EntityMeta.hub_id == hub_id, EntityMeta.node_uuid == node_uuid, EntityMeta.key == key
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.commit()
    return {"status": "deleted", "key": key}
