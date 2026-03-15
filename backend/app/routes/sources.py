from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import json
import base64
from ..db import get_db
from ..models import Hub, HubMember, Agent, Source, Provenance, Activity
from ..services import ingest
from .auth import get_current_agent

router = APIRouter(prefix="/api/hubs/{hub_id}/sources", tags=["sources"])


class AddSourceRequest(BaseModel):
    source_type: str  # text, url, paper, document
    name: str
    content: str = ""
    url: Optional[str] = None
    metadata: Optional[dict] = None



async def _ingest_background(source_id: str, hub_id: str, source_type: str,
                              name: str, content: str, url: str,
                              metadata: dict, agent_id: str, db_url: str):
    """Background task: ingest a source and update its status."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as AS

    eng = create_async_engine(db_url)
    try:
        result = await ingest.ingest_source(
            hub_id, source_type, name, content=content, url=url, metadata=metadata
        )

        async with AS(eng) as session:
            source = await session.get(Source, source_id)
            if source:
                source.status = "ingested"
                source.entity_count = result.get("entities_new", 0)
                source.edge_count = result.get("edges_new", 0)
                if result.get("error"):
                    source.status = "failed"
                    source.error = result["error"]

                # Create provenance records for new entities/edges
                for uuid in result.get("new_node_uuids", []):
                    session.add(Provenance(
                        hub_id=hub_id, node_uuid=uuid,
                        source_type=f"source_{source_type}",
                        agent_id=agent_id,
                        episode_name=f"Source: {name[:80]}",
                        paper_title=name if source_type == "paper" else None,
                    ))
                for uuid in result.get("new_edge_uuids", []):
                    session.add(Provenance(
                        hub_id=hub_id, edge_uuid=uuid,
                        source_type=f"source_{source_type}",
                        agent_id=agent_id,
                        episode_name=f"Source: {name[:80]}",
                    ))

                session.add(Activity(
                    hub_id=hub_id, agent_id=agent_id, action="added_source",
                    detail=f"{source_type}: {name[:80]} (+{result.get('entities_new', 0)} entities, +{result.get('edges_new', 0)} edges)",
                ))
                await session.commit()
        await eng.dispose()
    except Exception as e:
        print(f"Ingestion failed for source {source_id}: {e}")
        try:
            async with AS(eng) as session:
                source = await session.get(Source, source_id)
                if source:
                    source.status = "failed"
                    source.error = str(e)[:500]
                    await session.commit()
            await eng.dispose()
        except Exception:
            pass



@router.post("")
async def add_source(
    hub_id: str,
    req: AddSourceRequest,
    background: BackgroundTasks,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Add a source to the hub. Triggers background ingestion."""
    member = await db.get(HubMember, (hub_id, agent.id))
    if not member:
        raise HTTPException(403, "Not a member")

    source = Source(
        hub_id=hub_id, source_type=req.source_type, name=req.name,
        content=req.content, url=req.url,
        metadata_json=json.dumps(req.metadata or {}),
        status="ingesting", agent_id=agent.id,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    from ..config import DATABASE_URL
    background.add_task(
        _ingest_background, source.id, hub_id, req.source_type,
        req.name, req.content, req.url or "", req.metadata or {},
        agent.id, DATABASE_URL,
    )

    return {
        "id": source.id, "status": "ingesting",
        "source_type": req.source_type, "name": req.name,
    }


@router.post("/upload")
async def upload_source(
    hub_id: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(None),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file (PDF, DOCX, TXT) as a source."""
    member = await db.get(HubMember, (hub_id, agent.id))
    if not member:
        raise HTTPException(403, "Not a member")

    file_bytes = await file.read()
    file_name = name or file.filename or "uploaded_file"
    mime = file.content_type or ""

    # For text files, store content directly. For binary, base64 encode.
    if mime.startswith("text/") or file_name.endswith(".txt"):
        content = file_bytes.decode("utf-8", errors="replace")
        source_type = "text"
    else:
        content = base64.b64encode(file_bytes).decode("ascii")
        source_type = "document"

    source = Source(
        hub_id=hub_id, source_type=source_type, name=file_name,
        content=content, mime_type=mime,
        metadata_json=json.dumps({"original_filename": file.filename, "size": len(file_bytes)}),
        status="ingesting", agent_id=agent.id,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    from ..config import DATABASE_URL
    background.add_task(
        _ingest_background, source.id, hub_id, source_type,
        file_name, content, "", {"mime_type": mime},
        agent.id, DATABASE_URL,
    )

    return {"id": source.id, "status": "ingesting", "name": file_name, "source_type": source_type}


@router.get("")
async def list_sources(hub_id: str, db: AsyncSession = Depends(get_db)):
    """List all sources for a hub."""
    result = await db.execute(
        select(Source, Agent.name.label("agent_name"))
        .outerjoin(Agent, Agent.id == Source.agent_id)
        .where(Source.hub_id == hub_id)
        .order_by(Source.created_at.desc())
    )
    return [
        {
            "id": s.id, "hub_id": s.hub_id, "source_type": s.source_type,
            "name": s.name, "url": s.url, "status": s.status,
            "error": s.error, "agent_name": name or "",
            "entity_count": s.entity_count, "edge_count": s.edge_count,
            "created_at": s.created_at.isoformat(),
        }
        for s, name in result.all()
    ]
