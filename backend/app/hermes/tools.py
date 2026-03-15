import json
import asyncio
from typing import Any



SCHEMAS = {
    "mobhub_create_hub": {
        "name": "mobhub_create_hub",
        "description": "Create a new knowledge hub. Autonomous agents will discover, analyze, and build a knowledge graph about the topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Hub name (e.g. 'Nous Research')"},
                "topic": {"type": "string", "description": "Topic to research (e.g. 'Nous Research AI lab and its models')"},
                "description": {"type": "string", "description": "Optional description guiding agent focus"},
            },
            "required": ["name", "topic"],
        },
    },

    "mobhub_list_hubs": {
        "name": "mobhub_list_hubs",
        "description": "List all knowledge hubs with their entity/edge counts and status.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },

    "mobhub_hub_status": {
        "name": "mobhub_hub_status",
        "description": "Get detailed status of a hub: entity count, agent states, recent activity.",
        "parameters": {
            "type": "object",
            "properties": {
                "hub_id": {"type": "string", "description": "Hub ID"},
            },
            "required": ["hub_id"],
        },
    },

    "mobhub_search": {
        "name": "mobhub_search",
        "description": "Search a hub's knowledge graph for facts, entities, and relationships.",
        "parameters": {
            "type": "object",
            "properties": {
                "hub_id": {"type": "string", "description": "Hub ID"},
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results (default 10)"},
            },
            "required": ["hub_id", "query"],
        },
    },

    "mobhub_get_entity": {
        "name": "mobhub_get_entity",
        "description": "Get detailed information about an entity: summary, metadata, social links, connections, provenance.",
        "parameters": {
            "type": "object",
            "properties": {
                "hub_id": {"type": "string", "description": "Hub ID"},
                "entity_name": {"type": "string", "description": "Entity name to look up"},
            },
            "required": ["hub_id", "entity_name"],
        },
    },

    "mobhub_ask": {
        "name": "mobhub_ask",
        "description": "Ask a natural language question about a hub's knowledge. Returns an AI-generated answer with citations from the knowledge graph.",
        "parameters": {
            "type": "object",
            "properties": {
                "hub_id": {"type": "string", "description": "Hub ID"},
                "question": {"type": "string", "description": "Question to ask"},
            },
            "required": ["hub_id", "question"],
        },
    },

    "mobhub_instruct_agents": {
        "name": "mobhub_instruct_agents",
        "description": "Send an instruction to the hub's agent team (e.g. 'focus on finding competitors', 'research the founding team').",
        "parameters": {
            "type": "object",
            "properties": {
                "hub_id": {"type": "string", "description": "Hub ID"},
                "instruction": {"type": "string", "description": "Instruction for agents"},
            },
            "required": ["hub_id", "instruction"],
        },
    },

    "mobhub_list_agents": {
        "name": "mobhub_list_agents",
        "description": "List all agents (including sub-agents) for a hub with their status, event counts, and recent actions.",
        "parameters": {
            "type": "object",
            "properties": {
                "hub_id": {"type": "string", "description": "Hub ID"},
            },
            "required": ["hub_id"],
        },
    },

    "mobhub_agent_control": {
        "name": "mobhub_agent_control",
        "description": "Control hub agents: start, stop, or kill all agents.",
        "parameters": {
            "type": "object",
            "properties": {
                "hub_id": {"type": "string", "description": "Hub ID"},
                "action": {"type": "string", "enum": ["start", "stop", "kill"], "description": "Control action"},
            },
            "required": ["hub_id", "action"],
        },
    },

    "mobhub_add_content": {
        "name": "mobhub_add_content",
        "description": "Add text content to a hub's knowledge graph. The content will be processed by Graphiti to extract entities and relationships.",
        "parameters": {
            "type": "object",
            "properties": {
                "hub_id": {"type": "string", "description": "Hub ID"},
                "name": {"type": "string", "description": "Content title/name"},
                "content": {"type": "string", "description": "Text content to add"},
            },
            "required": ["hub_id", "name", "content"],
        },
    },

    "mobhub_get_graph_stats": {
        "name": "mobhub_get_graph_stats",
        "description": "Get knowledge graph statistics: entity count, edge count, clusters, gaps.",
        "parameters": {
            "type": "object",
            "properties": {
                "hub_id": {"type": "string", "description": "Hub ID"},
            },
            "required": ["hub_id"],
        },
    },
}



def _run_async(coro):
    """Run async function from sync Hermes handler context."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return loop.run_in_executor(pool, asyncio.run, coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _create_hub(args: dict) -> str:
    from ..services import graph
    from ..models import Hub, Agent, HubMember, Activity
    from ..db import async_session

    name = args.get("name", "")
    topic = args.get("topic", "")
    description = args.get("description", "")

    if not name or not topic:
        return json.dumps({"error": "name and topic are required"})

    async with async_session() as session:
        system_agent = Agent(name=f"hermes-{name[:20]}", agent_type="hermes")
        session.add(system_agent)
        await session.flush()

        hub = Hub(
            name=name, topic=topic, description=description,
            admin_id=system_agent.id,
            graph_id=f"hub_{topic.lower().replace(' ', '_')[:30]}",
            status="active",
        )
        session.add(hub)
        await session.flush()
        session.add(HubMember(hub_id=hub.id, agent_id=system_agent.id, role="admin"))
        session.add(Activity(hub_id=hub.id, agent_id=system_agent.id, action="created_hub", detail=name))
        await session.commit()

        hub_id = hub.id

    # Spawn agent team
    try:
        from ..engine.singleton import get_runtime
        rt = get_runtime()
        if rt._started:
            await rt.spawn_hub_agents(hub_id, name, topic)
    except Exception as e:
        return json.dumps({"hub_id": hub_id, "status": "created", "agents": "failed", "error": str(e)})

    return json.dumps({"hub_id": hub_id, "name": name, "topic": topic, "status": "active", "agents": "spawned"})


async def _list_hubs(args: dict) -> str:
    from ..models import Hub
    from ..db import async_session
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(Hub).order_by(Hub.created_at.desc()).limit(20))
        hubs = result.scalars().all()
        return json.dumps([
            {"id": h.id, "name": h.name, "topic": h.topic, "status": h.status,
             "entities": h.entity_count, "edges": h.edge_count}
            for h in hubs
        ])


async def _hub_status(args: dict) -> str:
    hub_id = args.get("hub_id", "")
    if not hub_id:
        return json.dumps({"error": "hub_id required"})

    from ..services import graph
    from ..engine.singleton import get_runtime

    try:
        stats = await graph.get_graph_stats(hub_id)
    except Exception:
        stats = {"nodes": 0, "edges": 0}

    rt = get_runtime()
    agents = rt.get_hub_agents(hub_id)

    return json.dumps({
        "hub_id": hub_id,
        "entities": stats.get("nodes", 0),
        "edges": stats.get("edges", 0),
        "agents": [
            {"name": a.name, "type": a.agent_type, "status": a.status.value,
             "events": a.events_handled, "errors": a.errors}
            for a in agents
        ],
    })


async def _search(args: dict) -> str:
    hub_id = args.get("hub_id", "")
    query = args.get("query", "")
    limit = args.get("limit", 10)

    if not hub_id or not query:
        return json.dumps({"error": "hub_id and query required"})

    from ..services import graph
    try:
        # Search both nodes and edges
        nodes = await graph.search_nodes(hub_id, query, limit=limit)
        edges = await graph.search_graph(hub_id, query, limit=limit)
        return json.dumps({"entities": nodes[:limit], "facts": edges[:limit]})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _get_entity(args: dict) -> str:
    hub_id = args.get("hub_id", "")
    entity_name = args.get("entity_name", "")

    if not hub_id or not entity_name:
        return json.dumps({"error": "hub_id and entity_name required"})

    from ..services import graph
    try:
        # Search by name
        nodes = await graph.search_nodes(hub_id, entity_name, limit=3)
        if not nodes:
            return json.dumps({"error": f"Entity '{entity_name}' not found"})

        # Get the best match
        best = nodes[0]
        uuid = best["uuid"]

        # Get neighbors
        detail = await graph.get_node_neighbors(hub_id, uuid)

        # Get metadata and assets from DB
        from ..db import async_session
        from ..models import EntityMeta, EntityAsset
        from sqlalchemy import select

        async with async_session() as session:
            meta_result = await session.execute(
                select(EntityMeta).where(EntityMeta.hub_id == hub_id, EntityMeta.node_uuid == uuid)
            )
            metadata = {m.key: m.value for m in meta_result.scalars().all()}

            asset_result = await session.execute(
                select(EntityAsset).where(EntityAsset.hub_id == hub_id, EntityAsset.node_uuid == uuid)
            )
            assets = [
                {"type": a.asset_type, "name": a.name, "content": a.content}
                for a in asset_result.scalars().all()
            ]

        return json.dumps({
            "name": best["name"],
            "uuid": uuid,
            "summary": best.get("summary", ""),
            "labels": best.get("labels", []),
            "metadata": metadata,
            "assets": assets,
            "connections": detail.get("neighbors", []) if detail else [],
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _ask(args: dict) -> str:
    hub_id = args.get("hub_id", "")
    question = args.get("question", "")

    if not hub_id or not question:
        return json.dumps({"error": "hub_id and question required"})

    from ..services import qa
    try:
        result = await qa.ask(hub_id, question)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _instruct_agents(args: dict) -> str:
    hub_id = args.get("hub_id", "")
    instruction = args.get("instruction", "")

    if not hub_id or not instruction:
        return json.dumps({"error": "hub_id and instruction required"})

    from ..engine.singleton import get_runtime
    rt = get_runtime()
    await rt.send_instruction(hub_id, instruction)
    return json.dumps({"status": "sent", "instruction": instruction})


async def _list_agents(args: dict) -> str:
    hub_id = args.get("hub_id", "")
    if not hub_id:
        return json.dumps({"error": "hub_id required"})

    from ..engine.singleton import get_runtime
    rt = get_runtime()
    agents = rt.get_hub_agents(hub_id)
    return json.dumps([a.to_dict() for a in agents])


async def _agent_control(args: dict) -> str:
    hub_id = args.get("hub_id", "")
    action = args.get("action", "")

    if not hub_id or not action:
        return json.dumps({"error": "hub_id and action required"})

    from ..engine.singleton import get_runtime
    rt = get_runtime()

    if action == "start":
        await rt.resume_hub(hub_id)
        return json.dumps({"status": "started"})
    elif action == "stop":
        await rt.stop_hub(hub_id)
        return json.dumps({"status": "stopped"})
    elif action == "kill":
        await rt.retire_hub_agents(hub_id)
        return json.dumps({"status": "killed"})
    else:
        return json.dumps({"error": f"Unknown action: {action}"})


async def _add_content(args: dict) -> str:
    hub_id = args.get("hub_id", "")
    name = args.get("name", "")
    content = args.get("content", "")

    if not hub_id or not content:
        return json.dumps({"error": "hub_id and content required"})

    from ..services import graph
    try:
        await graph.add_episode(hub_id, name or "Hermes content", content)
        return json.dumps({"status": "added", "name": name})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _get_graph_stats(args: dict) -> str:
    hub_id = args.get("hub_id", "")
    if not hub_id:
        return json.dumps({"error": "hub_id required"})

    from ..services import graph
    try:
        stats = await graph.get_graph_stats(hub_id)
        gaps = await graph.find_knowledge_gaps(hub_id, max_results=5)
        return json.dumps({
            "entities": stats.get("nodes", 0),
            "edges": stats.get("edges", 0),
            "gaps": [{"name": g["name"], "reasons": g["reasons"]} for g in gaps[:5]],
        })
    except Exception as e:
        return json.dumps({"error": str(e)})



_HANDLERS = {
    "mobhub_create_hub": _create_hub,
    "mobhub_list_hubs": _list_hubs,
    "mobhub_hub_status": _hub_status,
    "mobhub_search": _search,
    "mobhub_get_entity": _get_entity,
    "mobhub_ask": _ask,
    "mobhub_instruct_agents": _instruct_agents,
    "mobhub_list_agents": _list_agents,
    "mobhub_agent_control": _agent_control,
    "mobhub_add_content": _add_content,
    "mobhub_get_graph_stats": _get_graph_stats,
}


def _make_sync_handler(async_handler):
    """Wrap async handler for Hermes sync tool calling convention."""
    def handler(args, **kwargs):
        return asyncio.run(async_handler(args))
    return handler



def check_mobhub_requirements() -> bool:
    """Check if MobHub backend is available."""
    try:
        from ..config import DATABASE_URL
        return bool(DATABASE_URL)
    except Exception:
        return False


def register_mobhub_tools(registry):
    """
    Register all MobHub tools with a Hermes tool registry.

    Usage:
        from tools.registry import registry
        from app.hermes.tools import register_mobhub_tools
        register_mobhub_tools(registry)
    """
    for tool_name, schema in SCHEMAS.items():
        handler = _HANDLERS.get(tool_name)
        if not handler:
            continue

        registry.register(
            name=tool_name,
            toolset="mobhub",
            schema=schema,
            handler=_make_sync_handler(handler),
            check_fn=check_mobhub_requirements,
        )


def get_all_schemas() -> list[dict]:
    """Get all MobHub tool schemas (for standalone use without Hermes registry)."""
    return list(SCHEMAS.values())


def get_handler(tool_name: str):
    """Get an async handler by name (for direct use)."""
    return _HANDLERS.get(tool_name)
