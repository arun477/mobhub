import logging
from typing import Any

logger = logging.getLogger("engine.tools")


class Tool:
    """A tool an agent can use."""

    def __init__(self, name: str, description: str, fn):
        self.name = name
        self.description = description
        self.fn = fn

    async def __call__(self, **kwargs) -> Any:
        return await self.fn(**kwargs)


class ToolRegistry:
    """Central registry of all tools agents can access."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, fn):
        self._tools[name] = Tool(name, description, fn)
        logger.info(f"Tool registered: {name}")

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]

    def get_tools(self, names: list[str]) -> dict[str, Tool]:
        """Get a subset of tools by name."""
        return {n: self._tools[n] for n in names if n in self._tools}


async def build_default_tools() -> ToolRegistry:
    """Build the default tool registry with all platform capabilities."""
    from ..services import graph, websearch, ingest, search as paper_search
    from ..services.browser import fetch_page
    from ..services.llm import chat as llm_chat

    registry = ToolRegistry()

    registry.register("web_search", "Search the web via SearXNG", websearch.search)
    registry.register("news_search", "Search news articles", websearch.search_news)

    registry.register("browse_url", "Fetch and extract text from a URL", fetch_page)

    async def smart_add_episode(hub_id: str, name: str, content: str, source_desc: str = ""):
        """Add episode, detect new entities, emit events."""
        nodes_before = await graph.get_node_uuids(hub_id)
        edges_before = await graph.get_edge_uuids(hub_id)

        await graph.add_episode(hub_id, name, content, source_desc)

        nodes_after = await graph.get_node_uuids(hub_id)
        edges_after = await graph.get_edge_uuids(hub_id)

        new_nodes = nodes_after - nodes_before
        new_edges = edges_after - edges_before

        if new_nodes or new_edges:
            from .singleton import get_runtime
            from .events import Event, EventType
            rt = get_runtime()

            if new_nodes:
                all_nodes = await graph.get_all_nodes(hub_id)
                new_node_map = {n["uuid"]: n for n in all_nodes if n["uuid"] in new_nodes}

                for uuid in new_nodes:
                    node_data = new_node_map.get(uuid, {"uuid": uuid, "name": "unknown", "labels": []})
                    await rt.event_bus.emit(Event(
                        type=EventType.ENTITY_CREATED,
                        hub_id=hub_id,
                        data={
                            "uuid": node_data.get("uuid", uuid),
                            "name": node_data.get("name", "unknown"),
                            "labels": node_data.get("labels", []),
                            "summary": node_data.get("summary", ""),
                        },
                    ))

            for uuid in new_edges:
                await rt.event_bus.emit(Event(
                    type=EventType.FACT_CREATED,
                    hub_id=hub_id,
                    data={"edge_uuid": uuid},
                ))

            logger.info(f"Episode '{name[:40]}' created {len(new_nodes)} entities, {len(new_edges)} edges")

        return {
            "new_entities": len(new_nodes),
            "new_edges": len(new_edges),
            "new_node_uuids": list(new_nodes),
        }

    registry.register("graph_add_episode", "Add content to the knowledge graph (emits entity events)", smart_add_episode)
    registry.register("graph_search", "Search the knowledge graph for facts/edges", graph.search_graph)
    registry.register("graph_search_nodes", "Search for entity nodes", graph.search_nodes)
    registry.register("graph_get_nodes", "Get all nodes in hub", graph.get_all_nodes)
    registry.register("graph_get_edges", "Get all edges in hub", graph.get_all_edges)
    registry.register("graph_get_stats", "Get node/edge counts", graph.get_graph_stats)
    registry.register("graph_update_node", "Update a node's summary or labels", graph.update_node)
    registry.register("graph_neighbors", "Get a node's 1-hop neighborhood", graph.get_node_neighbors)
    registry.register("graph_merge_nodes", "Merge two entities", graph.merge_nodes)
    registry.register("graph_find_gaps", "Find under-connected entities", graph.find_knowledge_gaps)
    registry.register("graph_cleanup", "Remove garbage entities", graph.cleanup_garbage_entities)

    registry.register("search_papers", "Search Semantic Scholar for papers", paper_search.search_papers)
    registry.register("search_arxiv", "Search arXiv for papers", paper_search.search_arxiv)

    registry.register("ingest_source", "Ingest a source into the knowledge graph", ingest.ingest_source)

    registry.register("llm_chat", "Send messages to an LLM", llm_chat)

    async def save_entity_meta(hub_id: str, node_uuid: str, key: str, value: str):
        """Save structured metadata on an entity (upsert)."""
        from sqlalchemy import select as sa_select
        from ..db import async_session
        from ..models import EntityMeta

        async with async_session() as session:
            result = await session.execute(
                sa_select(EntityMeta).where(
                    EntityMeta.hub_id == hub_id,
                    EntityMeta.node_uuid == node_uuid,
                    EntityMeta.key == key,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.value = value
            else:
                session.add(EntityMeta(hub_id=hub_id, node_uuid=node_uuid, key=key, value=value))
            await session.commit()
        return {"status": "saved", "key": key, "value": value}

    async def save_entity_asset(hub_id: str, node_uuid: str, asset_type: str, name: str, content: str, mime_type: str = None):
        """Save an asset (image URL, social link, note, etc.) on an entity."""
        from ..db import async_session
        from ..models import EntityAsset

        async with async_session() as session:
            asset = EntityAsset(
                hub_id=hub_id, node_uuid=node_uuid,
                asset_type=asset_type, name=name, content=content,
                mime_type=mime_type, size_bytes=len(content.encode()) if content else 0,
            )
            session.add(asset)
            await session.commit()
            await session.refresh(asset)
        return {"id": asset.id, "status": "saved"}

    registry.register("save_entity_meta", "Save structured metadata on an entity", save_entity_meta)
    registry.register("save_entity_asset", "Save an asset (image, link, note) on an entity", save_entity_asset)

    return registry
