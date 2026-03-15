import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from pydantic import BaseModel
from typing import Optional
from ..db import get_db
from ..models import Hub, HubMember, Agent, Activity, Provenance, Vote, AgentMessage, EntityAsset, Episode
from ..services import seeder, graph, qa, ingest
from .auth import get_current_agent

router = APIRouter(prefix="/api/hubs", tags=["hubs"])


class CreateHubRequest(BaseModel):
    name: str
    topic: str
    description: str = ""
    seed_type: str = "agents"  # agents (v3 default), paper (legacy), blank, urls
    seed_papers: int = 15
    seed_urls: list[str] = []


class VoteRequest(BaseModel):
    node_uuid: Optional[str] = None
    edge_uuid: Optional[str] = None
    vote: str  # agree, disagree, unsure
    reason: str = ""


class EditEntityRequest(BaseModel):
    summary: Optional[str] = None
    labels: Optional[list[str]] = None
    deprecated: Optional[bool] = None


class EditEdgeRequest(BaseModel):
    fact: Optional[str] = None
    invalid_at: Optional[str] = None  # ISO timestamp to mark superseded


class SendMessageRequest(BaseModel):
    to_agent_id: Optional[str] = None  # null = broadcast to all members
    msg_type: str = "info"  # review_request, task, flag, info, merge_proposal
    subject: str = ""
    body: str = ""
    ref_node_uuid: Optional[str] = None
    ref_edge_uuid: Optional[str] = None


class MergeEntitiesRequest(BaseModel):
    source_uuid: str  # entity to merge FROM (will be removed)
    target_uuid: str  # entity to merge INTO (will be kept)



async def _seed_background(hub_id: str, topic: str, num_papers: int, db_url: str):
    """Background task: seed hub graph with papers, then create provenance records."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as AS
    from sqlalchemy.orm import sessionmaker

    try:
        result = await seeder.seed_hub(hub_id, topic, num_papers)

        # Create DB session for provenance + status update
        eng = create_async_engine(db_url)
        async with AS(eng) as session:
            hub = await session.get(Hub, hub_id)
            if hub:
                stats = await graph.get_graph_stats(hub_id)
                hub.status = "active"
                hub.entity_count = stats["nodes"]
                hub.edge_count = stats["edges"]

                # Create bulk provenance for all seeded entities/edges
                node_uuids = await graph.get_node_uuids(hub_id)
                edge_uuids = await graph.get_edge_uuids(hub_id)

                for uuid in node_uuids:
                    session.add(Provenance(
                        hub_id=hub_id, node_uuid=uuid, source_type="seed_paper",
                        episode_name=f"Seed: {topic}",
                        paper_title=f"{topic} seed corpus ({result.get('papers_found', 0)} papers)",
                        paper_source="semantic_scholar+arxiv",
                    ))
                for uuid in edge_uuids:
                    session.add(Provenance(
                        hub_id=hub_id, edge_uuid=uuid, source_type="seed_paper",
                        episode_name=f"Seed: {topic}",
                        paper_title=f"{topic} seed corpus ({result.get('papers_found', 0)} papers)",
                        paper_source="semantic_scholar+arxiv",
                    ))

                await session.commit()
        await eng.dispose()
    except Exception as e:
        print(f"Seeding failed for {hub_id}: {e}")


async def _seed_urls_background(hub_id: str, urls: list[str], db_url: str):
    """Background task: seed hub from URLs."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as AS

    try:
        for url in urls:
            try:
                await ingest.ingest_source(hub_id, "url", url, url=url)
            except Exception as e:
                print(f"URL ingest failed for {url}: {e}")

        eng = create_async_engine(db_url)
        async with AS(eng) as session:
            hub = await session.get(Hub, hub_id)
            if hub:
                stats = await graph.get_graph_stats(hub_id)
                hub.status = "active"
                hub.entity_count = stats["nodes"]
                hub.edge_count = stats["edges"]
                await session.commit()
        await eng.dispose()
    except Exception as e:
        print(f"URL seeding failed for {hub_id}: {e}")



@router.post("")
async def create_hub(
    req: CreateHubRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """v3: No auth required. Creates hub + auto-spawns agent team."""
    # Auto-create a system agent as hub admin (no auth needed)
    system_agent = Agent(name=f"hub-admin-{req.name[:20]}", agent_type="system")
    db.add(system_agent)
    await db.flush()

    initial_status = "active"
    hub = Hub(
        name=req.name, topic=req.topic, description=req.description,
        admin_id=system_agent.id, graph_id=f"hub_{req.topic.lower().replace(' ', '_')[:30]}",
        status=initial_status,
    )
    db.add(hub)
    await db.flush()
    db.add(HubMember(hub_id=hub.id, agent_id=system_agent.id, role="admin"))
    db.add(Activity(hub_id=hub.id, agent_id=system_agent.id, action="created_hub", detail=hub.name))

    # Auto-provision default skills
    from .skills import auto_provision_skills
    await auto_provision_skills(hub.id, db)

    await db.commit()
    await db.refresh(hub)

    # Legacy seed modes (paper, urls) — still supported
    if req.seed_type == "paper" and req.seed_papers > 0:
        from ..config import DATABASE_URL
        background.add_task(_seed_background, hub.id, req.topic, req.seed_papers, DATABASE_URL)
    elif req.seed_type == "urls" and req.seed_urls:
        from ..config import DATABASE_URL
        background.add_task(_seed_urls_background, hub.id, req.seed_urls, DATABASE_URL)

    # v3: Spawn agent team — they handle all discovery
    try:
        from ..engine.singleton import get_runtime
        rt = get_runtime()
        if rt._started:
            background.add_task(rt.spawn_hub_agents, hub.id, req.name, req.topic)
    except Exception as e:
        print(f"Agent spawn failed (non-critical): {e}")

    return _hub_dict(hub, [{"id": system_agent.id, "name": system_agent.name, "role": "admin"}])


@router.get("")
async def list_hubs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Hub).order_by(Hub.created_at.desc()))
    hubs = result.scalars().all()
    out = []
    for h in hubs:
        try:
            stats = await graph.get_graph_stats(h.id)
            h.entity_count = stats["nodes"]
            h.edge_count = stats["edges"]
        except Exception:
            pass
        members = await _get_members(db, h.id)
        out.append(_hub_dict(h, members))
    await db.commit()
    return out


@router.get("/{hub_id}")
async def get_hub(hub_id: str, db: AsyncSession = Depends(get_db)):
    hub = await db.get(Hub, hub_id)
    if not hub:
        raise HTTPException(404, "Hub not found")
    members = await _get_members(db, hub_id)
    try:
        stats = await graph.get_graph_stats(hub_id)
        hub.entity_count = stats["nodes"]
        hub.edge_count = stats["edges"]
        await db.commit()
    except Exception:
        pass
    return _hub_dict(hub, members)


@router.post("/{hub_id}/join")
async def join_hub(hub_id: str, agent: Agent = Depends(get_current_agent), db: AsyncSession = Depends(get_db)):
    hub = await db.get(Hub, hub_id)
    if not hub:
        raise HTTPException(404, "Hub not found")

    existing = await db.get(HubMember, (hub_id, agent.id))
    if not existing:
        db.add(HubMember(hub_id=hub_id, agent_id=agent.id, role="member"))
        db.add(Activity(hub_id=hub_id, agent_id=agent.id, action="joined"))
        await db.commit()
    return {"status": "joined"}


@router.post("/{hub_id}/leave")
async def leave_hub(hub_id: str, agent: Agent = Depends(get_current_agent), db: AsyncSession = Depends(get_db)):
    hub = await db.get(Hub, hub_id)
    if not hub:
        raise HTTPException(404, "Hub not found")
    if hub.admin_id == agent.id:
        raise HTTPException(400, "Admin cannot leave")
    member = await db.get(HubMember, (hub_id, agent.id))
    if member:
        await db.delete(member)
        db.add(Activity(hub_id=hub_id, agent_id=agent.id, action="left"))
        await db.commit()
    return {"status": "left"}



def _compute_confidence(vote_counts: dict) -> float | None:
    """Compute confidence from vote breakdown: (agree - disagree) / total, mapped to 0-1."""
    total = sum(vote_counts.values())
    if total == 0:
        return None
    agree = vote_counts.get("agree", 0)
    disagree = vote_counts.get("disagree", 0)
    return round(max(0, min(1, (agree - disagree + total) / (2 * total))), 2)


async def _enrich_nodes(nodes: list, hub_id: str, db: AsyncSession) -> list:
    """Add provenance_count, vote_count, confidence to each node."""
    if not nodes:
        return nodes
    uuids = [n["uuid"] for n in nodes]

    # Batch provenance counts
    prov_result = await db.execute(
        select(Provenance.node_uuid, func.count(Provenance.id))
        .where(Provenance.hub_id == hub_id, Provenance.node_uuid.in_(uuids))
        .group_by(Provenance.node_uuid)
    )
    prov_map = dict(prov_result.all())

    # Batch vote stats
    vote_result = await db.execute(
        select(Vote.node_uuid, Vote.vote, func.count(Vote.id))
        .where(Vote.hub_id == hub_id, Vote.node_uuid.in_(uuids))
        .group_by(Vote.node_uuid, Vote.vote)
    )
    vote_map = {}
    for uuid, vote_type, count in vote_result.all():
        vote_map.setdefault(uuid, {})[vote_type] = count

    # Batch asset counts
    asset_result = await db.execute(
        select(EntityAsset.node_uuid, func.count(EntityAsset.id))
        .where(EntityAsset.hub_id == hub_id, EntityAsset.node_uuid.in_(uuids))
        .group_by(EntityAsset.node_uuid)
    )
    asset_map = dict(asset_result.all())

    for node in nodes:
        uid = node["uuid"]
        node["provenance_count"] = prov_map.get(uid, 0)
        vc = vote_map.get(uid, {})
        node["vote_count"] = sum(vc.values())
        node["confidence"] = _compute_confidence(vc)
        node["asset_count"] = asset_map.get(uid, 0)

    return nodes


async def _enrich_edges(edges: list, hub_id: str, db: AsyncSession) -> list:
    """Add provenance_count, vote_count, confidence to each edge."""
    if not edges:
        return edges
    uuids = [e["uuid"] for e in edges]

    prov_result = await db.execute(
        select(Provenance.edge_uuid, func.count(Provenance.id))
        .where(Provenance.hub_id == hub_id, Provenance.edge_uuid.in_(uuids))
        .group_by(Provenance.edge_uuid)
    )
    prov_map = dict(prov_result.all())

    vote_result = await db.execute(
        select(Vote.edge_uuid, Vote.vote, func.count(Vote.id))
        .where(Vote.hub_id == hub_id, Vote.edge_uuid.in_(uuids))
        .group_by(Vote.edge_uuid, Vote.vote)
    )
    vote_map = {}
    for uuid, vote_type, count in vote_result.all():
        vote_map.setdefault(uuid, {})[vote_type] = count

    for edge in edges:
        uid = edge["uuid"]
        edge["provenance_count"] = prov_map.get(uid, 0)
        vc = vote_map.get(uid, {})
        edge["vote_count"] = sum(vc.values())
        edge["confidence"] = _compute_confidence(vc)

    return edges


@router.get("/{hub_id}/graph/nodes")
async def get_nodes(hub_id: str, db: AsyncSession = Depends(get_db)):
    try:
        nodes = await graph.get_all_nodes(hub_id)
    except Exception as e:
        print(f"get_nodes graph error: {e}")
        return []
    try:
        return await _enrich_nodes(nodes, hub_id, db)
    except Exception as e:
        print(f"get_nodes enrich error: {e}")
        return nodes  # Return unenriched nodes rather than empty


@router.get("/{hub_id}/graph/edges")
async def get_edges(hub_id: str, db: AsyncSession = Depends(get_db)):
    try:
        edges = await graph.get_all_edges(hub_id)
    except Exception as e:
        print(f"get_edges graph error: {e}")
        return []
    try:
        return await _enrich_edges(edges, hub_id, db)
    except Exception as e:
        print(f"get_edges enrich error: {e}")
        return edges  # Return unenriched edges rather than empty


@router.get("/{hub_id}/graph/search")
async def search_hub_graph(hub_id: str, q: str, limit: int = 10):
    try:
        return await graph.search_graph(hub_id, q, limit)
    except Exception:
        return []


@router.get("/{hub_id}/graph/nodes/search")
async def search_hub_nodes(hub_id: str, q: str, limit: int = 10):
    try:
        return await graph.search_nodes(hub_id, q, limit)
    except Exception:
        return []



@router.patch("/{hub_id}/graph/entity/{uuid}")
async def edit_entity(
    hub_id: str, uuid: str, req: EditEntityRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Agent directly edits an entity's summary or labels."""
    member = await db.get(HubMember, (hub_id, agent.id))
    if not member:
        raise HTTPException(403, "Not a member")

    labels = req.labels
    if req.deprecated:
        labels = (labels or []) + ["Deprecated"]

    result = await graph.update_node(hub_id, uuid, summary=req.summary, labels=labels)
    if not result:
        raise HTTPException(404, "Entity not found")

    # Track provenance for the edit
    db.add(Provenance(
        hub_id=hub_id, node_uuid=uuid, source_type="agent_edit",
        agent_id=agent.id, episode_name=f"Edited: {result.get('name', uuid[:16])}",
    ))
    db.add(Activity(
        hub_id=hub_id, agent_id=agent.id, action="edited_entity",
        detail=f"Edited {result.get('name', uuid[:16])}",
    ))
    await db.commit()
    return result


@router.patch("/{hub_id}/graph/edge/{uuid}")
async def edit_edge(
    hub_id: str, uuid: str, req: EditEdgeRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Agent directly edits an edge's fact text or marks it invalid."""
    member = await db.get(HubMember, (hub_id, agent.id))
    if not member:
        raise HTTPException(403, "Not a member")

    result = await graph.update_edge(hub_id, uuid, fact=req.fact, invalid_at=req.invalid_at)
    if not result:
        raise HTTPException(404, "Edge not found")

    db.add(Provenance(
        hub_id=hub_id, edge_uuid=uuid, source_type="agent_edit",
        agent_id=agent.id, episode_name=f"Edited: {result.get('name', uuid[:16])}",
    ))
    db.add(Activity(
        hub_id=hub_id, agent_id=agent.id, action="edited_edge",
        detail=f"Edited {result.get('name', uuid[:16])}",
    ))
    await db.commit()
    return result


@router.get("/{hub_id}/graph/entity/{uuid}/neighbors")
async def get_entity_neighbors(hub_id: str, uuid: str):
    """Get an entity and its 1-hop neighborhood."""
    result = await graph.get_node_neighbors(hub_id, uuid)
    if not result:
        raise HTTPException(404, "Entity not found")
    return result



@router.post("/{hub_id}/graph/episodes")
async def add_episode(
    hub_id: str,
    req: dict,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Agent adds an episode with full source tracking.
    Body: {name, content, source_url?, source_title?, source_type?, search_query?, agent_action?, metadata?}
    """
    member = await db.get(HubMember, (hub_id, agent.id))
    if not member:
        raise HTTPException(403, "Not a member")

    name = req.get("name", "Agent contribution")
    content = req.get("content", "")
    if not content:
        raise HTTPException(400, "Content required")

    # Extract rich metadata from request
    source_url = req.get("source_url", "")
    source_title = req.get("source_title", "")
    source_type = req.get("source_type", "text")
    search_query = req.get("search_query", "")
    agent_action = req.get("agent_action", "explore")
    metadata = req.get("metadata", {})

    # Snapshot before (best-effort)
    node_uuids_before = set()
    edge_uuids_before = set()
    try:
        node_uuids_before = await graph.get_node_uuids(hub_id)
        edge_uuids_before = await graph.get_edge_uuids(hub_id)
    except Exception:
        pass

    # Add episode to Graphiti
    from graphiti_core.nodes import EpisodeType
    from datetime import datetime, timezone
    import json as _json

    client = await graph.get_graphiti(hub_id)
    await client.add_episode(
        name=name, episode_body=content, source=EpisodeType.text,
        source_description=f"Agent: {agent.name} | {source_type}: {source_title or source_url or name}",
        group_id=hub_id, reference_time=datetime.now(timezone.utc),
    )

    # Snapshot after — find new extractions
    new_nodes = set()
    new_edges = set()
    try:
        node_uuids_after = await graph.get_node_uuids(hub_id)
        edge_uuids_after = await graph.get_edge_uuids(hub_id)
        new_nodes = node_uuids_after - node_uuids_before
        new_edges = edge_uuids_after - edge_uuids_before

        # Provenance for new entities/edges
        for uuid in new_nodes:
            db.add(Provenance(
                hub_id=hub_id, node_uuid=uuid, source_type=f"agent_{agent_action}",
                agent_id=agent.id, episode_name=name,
                paper_title=source_title or None,
                paper_doi=metadata.get("doi") if isinstance(metadata, dict) else None,
            ))
        for uuid in new_edges:
            db.add(Provenance(
                hub_id=hub_id, edge_uuid=uuid, source_type=f"agent_{agent_action}",
                agent_id=agent.id, episode_name=name,
                paper_title=source_title or None,
            ))
    except Exception:
        pass

    # Save the Episode record with full source tracking
    episode_record = Episode(
        hub_id=hub_id, name=name, content=content[:500],  # Store preview, not full text
        content_length=len(content),
        source_url=source_url or None,
        source_title=source_title or None,
        source_type=source_type,
        search_query=search_query or None,
        agent_id=agent.id,
        agent_action=agent_action,
        entities_extracted=len(new_nodes),
        edges_extracted=len(new_edges),
        metadata_json=_json.dumps(metadata) if isinstance(metadata, dict) else "{}",
    )
    db.add(episode_record)

    db.add(Activity(hub_id=hub_id, agent_id=agent.id, action="added_episode",
                    detail=f"{agent_action}: {name[:80]} (+{len(new_nodes)}e +{len(new_edges)}r)"))
    await db.commit()

    return {
        "status": "added", "name": name, "episode_id": episode_record.id,
        "new_entities": len(new_nodes), "new_relationships": len(new_edges),
    }


@router.get("/{hub_id}/graph/episodes")
async def list_episodes(hub_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    """List all episodes with their source tracking data."""
    result = await db.execute(
        select(Episode, Agent.name.label("agent_name"))
        .outerjoin(Agent, Agent.id == Episode.agent_id)
        .where(Episode.hub_id == hub_id)
        .order_by(Episode.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": e.id, "name": e.name, "content_preview": e.content[:200] if e.content else "",
            "content_length": e.content_length,
            "source_url": e.source_url, "source_title": e.source_title,
            "source_type": e.source_type, "search_query": e.search_query,
            "agent_name": name or "", "agent_action": e.agent_action,
            "entities_extracted": e.entities_extracted, "edges_extracted": e.edges_extracted,
            "created_at": e.created_at.isoformat(),
        }
        for e, name in result.all()
    ]



@router.post("/{hub_id}/graph/vote")
async def vote_on_item(
    hub_id: str,
    req: VoteRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Agent votes on an entity or edge. Upserts — one vote per agent per item."""
    member = await db.get(HubMember, (hub_id, agent.id))
    if not member:
        raise HTTPException(403, "Not a member")

    if not req.node_uuid and not req.edge_uuid:
        raise HTTPException(400, "Must specify node_uuid or edge_uuid")
    if req.vote not in ("agree", "disagree", "unsure"):
        raise HTTPException(400, "Vote must be agree, disagree, or unsure")

    # Check for existing vote (upsert)
    conditions = [Vote.hub_id == hub_id, Vote.agent_id == agent.id]
    if req.node_uuid:
        conditions.append(Vote.node_uuid == req.node_uuid)
    else:
        conditions.append(Vote.edge_uuid == req.edge_uuid)

    result = await db.execute(select(Vote).where(and_(*conditions)))
    existing = result.scalar_one_or_none()

    if existing:
        existing.vote = req.vote
        existing.reason = req.reason
    else:
        db.add(Vote(
            hub_id=hub_id, node_uuid=req.node_uuid, edge_uuid=req.edge_uuid,
            agent_id=agent.id, vote=req.vote, reason=req.reason,
        ))

    db.add(Activity(
        hub_id=hub_id, agent_id=agent.id, action="voted",
        detail=f"{req.vote} on {'entity' if req.node_uuid else 'edge'} {req.node_uuid or req.edge_uuid}",
    ))
    await db.commit()
    return {"status": "voted", "vote": req.vote}


@router.get("/{hub_id}/graph/entity/{uuid}/votes")
async def get_entity_votes(hub_id: str, uuid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Vote, Agent.name.label("agent_name"))
        .outerjoin(Agent, Agent.id == Vote.agent_id)
        .where(Vote.hub_id == hub_id, Vote.node_uuid == uuid)
        .order_by(Vote.created_at.desc())
    )
    rows = result.all()
    votes = [
        {"agent_id": v.agent_id, "agent_name": name or "", "vote": v.vote,
         "reason": v.reason, "created_at": v.created_at.isoformat()}
        for v, name in rows
    ]
    counts = {}
    for v, _ in rows:
        counts[v.vote] = counts.get(v.vote, 0) + 1

    return {
        "uuid": uuid,
        "votes": votes,
        "agree": counts.get("agree", 0),
        "disagree": counts.get("disagree", 0),
        "unsure": counts.get("unsure", 0),
        "confidence": _compute_confidence(counts),
    }


@router.get("/{hub_id}/graph/edge/{uuid}/votes")
async def get_edge_votes(hub_id: str, uuid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Vote, Agent.name.label("agent_name"))
        .outerjoin(Agent, Agent.id == Vote.agent_id)
        .where(Vote.hub_id == hub_id, Vote.edge_uuid == uuid)
        .order_by(Vote.created_at.desc())
    )
    rows = result.all()
    votes = [
        {"agent_id": v.agent_id, "agent_name": name or "", "vote": v.vote,
         "reason": v.reason, "created_at": v.created_at.isoformat()}
        for v, name in rows
    ]
    counts = {}
    for v, _ in rows:
        counts[v.vote] = counts.get(v.vote, 0) + 1

    return {
        "uuid": uuid,
        "votes": votes,
        "agree": counts.get("agree", 0),
        "disagree": counts.get("disagree", 0),
        "unsure": counts.get("unsure", 0),
        "confidence": _compute_confidence(counts),
    }



@router.get("/{hub_id}/graph/entity/{uuid}/provenance")
async def get_entity_provenance(hub_id: str, uuid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Provenance, Agent.name.label("agent_name"))
        .outerjoin(Agent, Agent.id == Provenance.agent_id)
        .where(Provenance.hub_id == hub_id, Provenance.node_uuid == uuid)
        .order_by(Provenance.created_at.desc())
    )
    rows = result.all()
    return {
        "uuid": uuid,
        "provenance": [
            {
                "source_type": p.source_type,
                "agent_id": p.agent_id,
                "agent_name": name or "",
                "episode_name": p.episode_name,
                "paper_title": p.paper_title,
                "paper_doi": p.paper_doi,
                "paper_source": p.paper_source,
                "created_at": p.created_at.isoformat(),
            }
            for p, name in rows
        ],
    }


@router.get("/{hub_id}/graph/edge/{uuid}/provenance")
async def get_edge_provenance(hub_id: str, uuid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Provenance, Agent.name.label("agent_name"))
        .outerjoin(Agent, Agent.id == Provenance.agent_id)
        .where(Provenance.hub_id == hub_id, Provenance.edge_uuid == uuid)
        .order_by(Provenance.created_at.desc())
    )
    rows = result.all()
    return {
        "uuid": uuid,
        "provenance": [
            {
                "source_type": p.source_type,
                "agent_id": p.agent_id,
                "agent_name": name or "",
                "episode_name": p.episode_name,
                "paper_title": p.paper_title,
                "paper_doi": p.paper_doi,
                "paper_source": p.paper_source,
                "created_at": p.created_at.isoformat(),
            }
            for p, name in rows
        ],
    }



@router.post("/{hub_id}/messages")
async def send_message(
    hub_id: str, req: SendMessageRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to another agent (or broadcast to all hub members)."""
    member = await db.get(HubMember, (hub_id, agent.id))
    if not member:
        raise HTTPException(403, "Not a member")

    msg = AgentMessage(
        hub_id=hub_id, from_agent_id=agent.id, to_agent_id=req.to_agent_id,
        msg_type=req.msg_type, subject=req.subject, body=req.body,
        ref_node_uuid=req.ref_node_uuid, ref_edge_uuid=req.ref_edge_uuid,
    )
    db.add(msg)
    db.add(Activity(hub_id=hub_id, agent_id=agent.id, action="sent_message",
                    detail=f"{req.msg_type}: {req.subject[:80]}"))
    await db.commit()
    await db.refresh(msg)
    return {"id": msg.id, "status": "sent"}


@router.get("/{hub_id}/messages/inbox")
async def get_inbox(
    hub_id: str, unread_only: bool = False,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get messages for this agent (direct + broadcasts)."""
    conditions = [
        AgentMessage.hub_id == hub_id,
        or_(AgentMessage.to_agent_id == agent.id, AgentMessage.to_agent_id == None),
    ]
    if unread_only:
        conditions.append(AgentMessage.read == False)

    result = await db.execute(
        select(AgentMessage, Agent.name.label("from_name"))
        .outerjoin(Agent, Agent.id == AgentMessage.from_agent_id)
        .where(and_(*conditions))
        .order_by(AgentMessage.created_at.desc())
        .limit(50)
    )
    return [
        {
            "id": m.id, "hub_id": m.hub_id, "from_agent_id": m.from_agent_id,
            "from_name": name or "", "to_agent_id": m.to_agent_id,
            "msg_type": m.msg_type, "subject": m.subject, "body": m.body,
            "ref_node_uuid": m.ref_node_uuid, "ref_edge_uuid": m.ref_edge_uuid,
            "read": m.read, "created_at": m.created_at.isoformat(),
        }
        for m, name in result.all()
    ]


@router.patch("/{hub_id}/messages/{msg_id}/read")
async def mark_message_read(
    hub_id: str, msg_id: int,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Mark a message as read."""
    result = await db.execute(
        select(AgentMessage).where(AgentMessage.id == msg_id, AgentMessage.hub_id == hub_id)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(404, "Message not found")
    msg.read = True
    await db.commit()
    return {"status": "read"}



@router.post("/{hub_id}/graph/cleanup")
async def cleanup_hub_graph(hub_id: str):
    """Remove garbage entities (navigation elements, handles, orphans)."""
    try:
        return await graph.cleanup_garbage_entities(hub_id)
    except Exception as e:
        return {"deleted": 0, "error": str(e)}


@router.get("/{hub_id}/graph/duplicates")
async def detect_duplicates(hub_id: str, threshold: float = 0.8):
    """Find entity pairs that might be duplicates (similar names)."""
    try:
        nodes = await graph.get_all_nodes(hub_id)
    except Exception:
        return []

    if len(nodes) < 2:
        return []

    import re
    def similarity(a: str, b: str) -> float:
        a_low, b_low = a.lower().strip(), b.lower().strip()
        if a_low == b_low:
            return 1.0
        # Normalize: remove all non-alphanumeric, compare
        a_norm = re.sub(r'[^a-z0-9]', '', a_low)
        b_norm = re.sub(r'[^a-z0-9]', '', b_low)
        if a_norm == b_norm:
            return 1.0  # "NOUS RESEARCH" == "Nous Research" == "NousResearch"
        # One contains the other (after normalization)
        if len(a_norm) > 3 and len(b_norm) > 3:
            if a_norm in b_norm or b_norm in a_norm:
                return 0.9
        # Word overlap (Jaccard)
        a_words = set(a_low.split())
        b_words = set(b_low.split())
        if not a_words or not b_words:
            return 0.0
        intersection = a_words & b_words
        union = a_words | b_words
        return len(intersection) / len(union)

    pairs = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            sim = similarity(nodes[i]["name"], nodes[j]["name"])
            if sim >= threshold:
                pairs.append({
                    "entity_a": {"uuid": nodes[i]["uuid"], "name": nodes[i]["name"], "summary": nodes[i].get("summary", "")},
                    "entity_b": {"uuid": nodes[j]["uuid"], "name": nodes[j]["name"], "summary": nodes[j].get("summary", "")},
                    "similarity": round(sim, 2),
                })
    pairs.sort(key=lambda x: x["similarity"], reverse=True)
    return pairs[:20]


@router.post("/{hub_id}/graph/merge")
async def merge_entities(
    hub_id: str, req: MergeEntitiesRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Merge two entities: redirect edges from source to target, then delete source."""
    member = await db.get(HubMember, (hub_id, agent.id))
    if not member:
        raise HTTPException(403, "Not a member")

    result = await graph.merge_nodes(hub_id, req.source_uuid, req.target_uuid)
    if not result:
        raise HTTPException(400, "Merge failed — entities not found")

    # Update provenance: source entity references now point to target
    await db.execute(
        select(Provenance).where(Provenance.node_uuid == req.source_uuid, Provenance.hub_id == hub_id)
    )
    # Just add a new provenance entry for the merge
    db.add(Provenance(
        hub_id=hub_id, node_uuid=req.target_uuid, source_type="agent_edit",
        agent_id=agent.id, episode_name=f"Merged: {result.get('source_name', '?')} → {result.get('target_name', '?')}",
    ))
    db.add(Activity(
        hub_id=hub_id, agent_id=agent.id, action="merged_entities",
        detail=f"Merged '{result.get('source_name', '?')}' into '{result.get('target_name', '?')}'",
    ))
    await db.commit()
    return result



@router.get("/{hub_id}/graph/path")
async def find_path(hub_id: str, from_uuid: str, to_uuid: str):
    """Find the shortest path between two entities."""
    result = await graph.find_shortest_path(hub_id, from_uuid, to_uuid)
    if not result:
        return {"from_uuid": from_uuid, "to_uuid": to_uuid, "hops": -1, "nodes": [], "edges": [], "message": "No path found"}
    return result


@router.get("/{hub_id}/graph/clusters")
async def get_clusters(hub_id: str, min_size: int = 3):
    """Detect entity clusters (connected components)."""
    try:
        return await graph.detect_clusters(hub_id, min_cluster_size=min_size)
    except Exception:
        return []


@router.get("/{hub_id}/graph/gaps")
async def get_gaps(hub_id: str, limit: int = 20):
    """Find knowledge gaps — under-connected or poorly described entities."""
    try:
        return await graph.find_knowledge_gaps(hub_id, max_results=limit)
    except Exception:
        return []



class AskRequest(BaseModel):
    question: str


@router.post("/{hub_id}/ask")
async def ask_question(hub_id: str, req: AskRequest):
    """Ask a natural language question — answered using the hub's knowledge graph."""
    hub_exists = True  # trust the hub_id for now
    try:
        result = await qa.ask(hub_id, req.question)
        return result
    except Exception as e:
        raise HTTPException(500, f"Q&A failed: {str(e)}")



@router.get("/{hub_id}/timeline")
async def get_timeline(hub_id: str, db: AsyncSession = Depends(get_db)):
    """Get the knowledge evolution timeline — provenance records grouped by time."""
    result = await db.execute(
        select(Provenance, Agent.name.label("agent_name"))
        .outerjoin(Agent, Agent.id == Provenance.agent_id)
        .where(Provenance.hub_id == hub_id)
        .order_by(Provenance.created_at.desc())
        .limit(200)
    )
    rows = result.all()

    # Group by date
    timeline = {}
    for p, agent_name in rows:
        date_key = p.created_at.strftime("%Y-%m-%d")
        if date_key not in timeline:
            timeline[date_key] = {"date": date_key, "events": [], "entity_count": 0, "edge_count": 0}

        event = {
            "source_type": p.source_type,
            "agent_name": agent_name or "",
            "episode_name": p.episode_name,
            "paper_title": p.paper_title,
            "node_uuid": p.node_uuid,
            "edge_uuid": p.edge_uuid,
            "created_at": p.created_at.isoformat(),
        }
        timeline[date_key]["events"].append(event)
        if p.node_uuid:
            timeline[date_key]["entity_count"] += 1
        if p.edge_uuid:
            timeline[date_key]["edge_count"] += 1

    return list(timeline.values())



@router.get("/{hub_id}/activity")
async def get_activity(hub_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Activity, Agent.name.label("agent_name"))
        .outerjoin(Agent, Agent.id == Activity.agent_id)
        .where(Activity.hub_id == hub_id)
        .order_by(Activity.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": a.id, "hub_id": a.hub_id, "agent_id": a.agent_id,
            "agent_name": name or "", "action": a.action,
            "detail": a.detail, "created_at": a.created_at.isoformat(),
        }
        for a, name in result.all()
    ]



async def _get_members(db: AsyncSession, hub_id: str):
    result = await db.execute(
        select(HubMember, Agent.name).join(Agent, Agent.id == HubMember.agent_id)
        .where(HubMember.hub_id == hub_id)
    )
    return [{"id": m.agent_id, "name": name, "role": m.role} for m, name in result.all()]


def _hub_dict(hub: Hub, members: list):
    return {
        "id": hub.id, "name": hub.name, "topic": hub.topic,
        "description": hub.description, "admin_id": hub.admin_id,
        "graph_id": hub.graph_id, "status": hub.status,
        "entity_count": hub.entity_count, "edge_count": hub.edge_count,
        "members": members, "created_at": hub.created_at.isoformat(),
    }
