from datetime import datetime, timezone
from graphiti_core import Graphiti
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode, EpisodeType
from graphiti_core.search.search_config_recipes import (
    NODE_HYBRID_SEARCH_RRF,
    EDGE_HYBRID_SEARCH_RRF,
)
from ..config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


_clients: dict[str, Graphiti] = {}
_indices_built = False


async def get_graphiti(hub_id: str) -> Graphiti:
    """Get or create a Graphiti instance for a hub. Indices built once globally."""
    global _indices_built
    if hub_id not in _clients:
        client = Graphiti(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        if not _indices_built:
            try:
                await client.build_indices_and_constraints()
                _indices_built = True
            except Exception as e:
                print(f"Warning: build_indices_and_constraints failed (may already exist): {e}")
                _indices_built = True  # Don't retry on every call
        _clients[hub_id] = client
    return _clients[hub_id]


async def _get_driver(hub_id: str):
    """Get the Neo4j driver for direct Cypher queries."""
    client = await get_graphiti(hub_id)
    return client.driver



async def add_episode(hub_id: str, name: str, content: str, source_desc: str = ""):
    """Add an episode (text) to the hub's graph."""
    client = await get_graphiti(hub_id)
    await client.add_episode(
        name=name, episode_body=content, source=EpisodeType.text,
        source_description=source_desc or f"Hub {hub_id}",
        group_id=hub_id, reference_time=datetime.now(timezone.utc),
    )



async def search_graph(hub_id: str, query: str, limit: int = 10):
    """Search the graph for relevant facts/edges."""
    client = await get_graphiti(hub_id)
    results = await client.search(query, group_ids=[hub_id], num_results=limit)
    return [
        {
            "fact": r.fact, "name": r.name,
            "source_node": r.source_node_uuid, "target_node": r.target_node_uuid,
            "valid_at": r.valid_at.isoformat() if r.valid_at else None,
            "invalid_at": r.invalid_at.isoformat() if r.invalid_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in results
    ]


async def search_nodes(hub_id: str, query: str, limit: int = 10):
    """Search for entity nodes."""
    client = await get_graphiti(hub_id)
    config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
    config.limit = limit
    results = await client._search(query=query, config=config, group_ids=[hub_id])
    return [
        {
            "uuid": n.uuid, "name": n.name, "summary": n.summary or "",
            "labels": list(n.labels) if n.labels else [],
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in results.nodes
    ]



async def get_all_nodes(hub_id: str):
    """Get all entity nodes for a hub via direct Cypher (reliable label reading)."""
    driver = await _get_driver(hub_id)
    records, _, _ = await driver.execute_query(
        "MATCH (n:Entity {group_id: $gid}) RETURN n.uuid AS uuid, n.name AS name, "
        "n.summary AS summary, n.labels AS labels, n.created_at AS created_at "
        "ORDER BY n.name",
        gid=hub_id,
    )
    return [
        {
            "uuid": r["uuid"], "name": r["name"], "summary": r["summary"] or "",
            "labels": list(r["labels"]) if r["labels"] else [],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in records
    ]


async def get_all_edges(hub_id: str):
    """Get all relationship edges for a hub."""
    client = await get_graphiti(hub_id)
    edges = await EntityEdge.get_by_group_ids(client.driver, [hub_id])
    return [
        {
            "uuid": e.uuid, "name": e.name, "fact": e.fact,
            "source_node_uuid": e.source_node_uuid, "target_node_uuid": e.target_node_uuid,
            "valid_at": e.valid_at.isoformat() if e.valid_at else None,
            "invalid_at": e.invalid_at.isoformat() if e.invalid_at else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in edges
    ]



async def get_node_uuids(hub_id: str) -> set[str]:
    """Get just UUIDs of all nodes via direct Cypher (fast)."""
    driver = await _get_driver(hub_id)
    records, _, _ = await driver.execute_query(
        "MATCH (n:Entity {group_id: $gid}) RETURN n.uuid AS uuid",
        gid=hub_id,
    )
    return {r["uuid"] for r in records}


async def get_edge_uuids(hub_id: str) -> set[str]:
    """Get just UUIDs of all edges via direct Cypher (fast)."""
    driver = await _get_driver(hub_id)
    records, _, _ = await driver.execute_query(
        "MATCH ()-[r:RELATES_TO {group_id: $gid}]-() RETURN DISTINCT r.uuid AS uuid",
        gid=hub_id,
    )
    return {r["uuid"] for r in records}


async def get_graph_stats(hub_id: str):
    """Get node and edge counts via Cypher count queries (fast)."""
    driver = await _get_driver(hub_id)
    node_records, _, _ = await driver.execute_query(
        "MATCH (n:Entity {group_id: $gid}) RETURN count(n) AS cnt", gid=hub_id,
    )
    edge_records, _, _ = await driver.execute_query(
        "MATCH ()-[r:RELATES_TO {group_id: $gid}]-() RETURN count(r) AS cnt", gid=hub_id,
    )
    return {
        "nodes": node_records[0]["cnt"] if node_records else 0,
        "edges": edge_records[0]["cnt"] if edge_records else 0,
    }



async def update_node(hub_id: str, uuid: str, summary: str = None, labels: list[str] = None) -> dict | None:
    """Directly update a node's summary and/or labels."""
    driver = await _get_driver(hub_id)
    set_parts = []
    params = {"uuid": uuid, "gid": hub_id}

    if summary is not None:
        set_parts.append("n.summary = $summary")
        params["summary"] = summary
    if labels is not None:
        set_parts.append("n.labels = $labels")
        params["labels"] = list(set(labels) | {"Entity"})

    if not set_parts:
        return None

    records, _, _ = await driver.execute_query(
        f"MATCH (n:Entity {{uuid: $uuid, group_id: $gid}}) SET {', '.join(set_parts)} RETURN n.uuid as uuid, n.name as name, n.summary as summary",
        **params,
    )
    if records:
        return {"uuid": uuid, "name": records[0]["name"], "summary": records[0]["summary"], "labels": params.get("labels", [])}
    return None


async def update_edge(hub_id: str, uuid: str, fact: str = None, invalid_at: str = None) -> dict | None:
    """Directly update an edge's fact or mark it invalid."""
    driver = await _get_driver(hub_id)
    params = {"uuid": uuid, "gid": hub_id}
    set_clauses = []

    if fact is not None:
        set_clauses.append("r.fact = $fact")
        params["fact"] = fact
    if invalid_at is not None:
        set_clauses.append("r.invalid_at = datetime($invalid_at)")
        params["invalid_at"] = invalid_at

    if not set_clauses:
        return None

    records, _, _ = await driver.execute_query(
        f"MATCH ()-[r:RELATES_TO {{uuid: $uuid, group_id: $gid}}]-() SET {', '.join(set_clauses)} RETURN r.uuid as uuid, r.name as name, r.fact as fact",
        **params,
    )
    if records:
        return {"uuid": uuid, "name": records[0]["name"], "fact": records[0]["fact"]}
    return None


async def get_node_neighbors(hub_id: str, uuid: str) -> dict | None:
    """Get a node and its 1-hop neighborhood."""
    driver = await _get_driver(hub_id)
    records, _, _ = await driver.execute_query(
        """
        MATCH (n:Entity {uuid: $uuid, group_id: $gid})
        OPTIONAL MATCH (n)-[r:RELATES_TO]-(m:Entity)
        WHERE m.group_id = $gid
        RETURN n.uuid as uuid, n.name as name, n.summary as summary, labels(n) as labels,
               collect(DISTINCT {
                   edge_uuid: r.uuid, edge_fact: r.fact, edge_name: r.name,
                   neighbor_uuid: m.uuid, neighbor_name: m.name
               }) as neighbors
        """,
        uuid=uuid, gid=hub_id,
    )
    if not records:
        return None

    r = records[0]
    return {
        "uuid": r["uuid"], "name": r["name"], "summary": r["summary"],
        "labels": [l for l in (r["labels"] or []) if l not in ("Entity", "__Entity__")],
        "neighbors": [
            {"edge_uuid": n["edge_uuid"], "edge_fact": n["edge_fact"], "edge_name": n["edge_name"],
             "neighbor_uuid": n["neighbor_uuid"], "neighbor_name": n["neighbor_name"]}
            for n in r["neighbors"] if n["neighbor_uuid"]
        ],
    }


async def merge_nodes(hub_id: str, source_uuid: str, target_uuid: str) -> dict | None:
    """Merge source entity into target: redirect edges, combine summaries, delete source."""
    driver = await _get_driver(hub_id)

    records, _, _ = await driver.execute_query(
        """
        MATCH (s:Entity {uuid: $source, group_id: $gid})
        MATCH (t:Entity {uuid: $target, group_id: $gid})
        RETURN s.name as source_name, s.summary as source_summary,
               t.name as target_name, t.summary as target_summary
        """,
        source=source_uuid, target=target_uuid, gid=hub_id,
    )
    if not records:
        return None

    source_name = records[0]["source_name"]
    target_name = records[0]["target_name"]
    source_summary = records[0]["source_summary"] or ""
    target_summary = records[0]["target_summary"] or ""

    if len(target_summary) < len(source_summary):
        combined = f"{target_summary} {source_summary}".strip()[:500]
        await driver.execute_query(
            "MATCH (t:Entity {uuid: $target, group_id: $gid}) SET t.summary = $summary",
            target=target_uuid, gid=hub_id, summary=combined,
        )

    # Redirect outgoing edges
    await driver.execute_query(
        """
        MATCH (s:Entity {uuid: $source, group_id: $gid})-[r:RELATES_TO]->(other)
        CREATE (t)-[r2:RELATES_TO]->(other)
        WITH r, r2, t
        MATCH (t:Entity {uuid: $target, group_id: $gid})
        SET r2 = properties(r), r2.source_node_uuid = $target
        DELETE r
        """,
        source=source_uuid, target=target_uuid, gid=hub_id,
    )
    # Redirect incoming edges
    await driver.execute_query(
        """
        MATCH (other)-[r:RELATES_TO]->(s:Entity {uuid: $source, group_id: $gid})
        CREATE (other)-[r2:RELATES_TO]->(t)
        WITH r, r2, t
        MATCH (t:Entity {uuid: $target, group_id: $gid})
        SET r2 = properties(r), r2.target_node_uuid = $target
        DELETE r
        """,
        source=source_uuid, target=target_uuid, gid=hub_id,
    )

    await driver.execute_query(
        "MATCH (s:Entity {uuid: $source, group_id: $gid}) DETACH DELETE s",
        source=source_uuid, gid=hub_id,
    )

    return {
        "status": "merged",
        "source_uuid": source_uuid, "source_name": source_name,
        "target_uuid": target_uuid, "target_name": target_name,
    }



async def find_shortest_path(hub_id: str, from_uuid: str, to_uuid: str, max_depth: int = 6) -> dict | None:
    """Find shortest path between two entities."""
    driver = await _get_driver(hub_id)
    records, _, _ = await driver.execute_query(
        """
        MATCH path = shortestPath(
            (a:Entity {uuid: $from_uuid, group_id: $gid})-[:RELATES_TO*1..%d]-(b:Entity {uuid: $to_uuid, group_id: $gid})
        )
        RETURN [n IN nodes(path) | {uuid: n.uuid, name: n.name, summary: n.summary}] as nodes,
               [r IN relationships(path) | {uuid: r.uuid, name: r.name, fact: r.fact}] as edges,
               length(path) as hops
        """ % max_depth,
        from_uuid=from_uuid, to_uuid=to_uuid, gid=hub_id,
    )
    if not records:
        return None
    r = records[0]
    return {"from_uuid": from_uuid, "to_uuid": to_uuid, "hops": r["hops"], "nodes": r["nodes"], "edges": r["edges"]}


async def detect_clusters(hub_id: str, min_cluster_size: int = 3) -> list:
    """Detect entity clusters using connected components (BFS in Python)."""
    nodes = await get_all_nodes(hub_id)
    edges = await get_all_edges(hub_id)
    if not nodes:
        return []

    adj = {n["uuid"]: set() for n in nodes}
    for e in edges:
        s, t = e.get("source_node_uuid"), e.get("target_node_uuid")
        if s in adj and t in adj:
            adj[s].add(t)
            adj[t].add(s)

    visited = set()
    clusters = []
    for node in nodes:
        uid = node["uuid"]
        if uid in visited:
            continue
        component = []
        queue = [uid]
        while queue:
            curr = queue.pop(0)
            if curr in visited:
                continue
            visited.add(curr)
            component.append(curr)
            queue.extend(adj.get(curr, set()) - visited)

        if len(component) >= min_cluster_size:
            node_map = {n["uuid"]: n for n in nodes}
            cluster_nodes = [node_map[u] for u in component if u in node_map]
            cluster_nodes.sort(key=lambda n: len(adj.get(n["uuid"], set())), reverse=True)
            clusters.append({
                "size": len(component),
                "representative": cluster_nodes[0]["name"] if cluster_nodes else "?",
                "entities": [{"uuid": n["uuid"], "name": n["name"], "connections": len(adj.get(n["uuid"], set()))} for n in cluster_nodes[:15]],
            })

    clusters.sort(key=lambda c: c["size"], reverse=True)
    return clusters


async def find_knowledge_gaps(hub_id: str, max_results: int = 20) -> list:
    """Find under-connected or poorly described entities."""
    nodes = await get_all_nodes(hub_id)
    edges = await get_all_edges(hub_id)
    if not nodes:
        return []

    conn_count = {n["uuid"]: 0 for n in nodes}
    for e in edges:
        s, t = e.get("source_node_uuid"), e.get("target_node_uuid")
        if s in conn_count: conn_count[s] += 1
        if t in conn_count: conn_count[t] += 1

    gaps = []
    for n in nodes:
        connections = conn_count.get(n["uuid"], 0)
        summary_len = len(n.get("summary", "") or "")
        labels = [l for l in (n.get("labels") or []) if l not in ("Entity", "__Entity__")]
        gap_score = 0
        if connections == 0: gap_score += 3
        elif connections <= 2: gap_score += 1
        if summary_len < 20: gap_score += 2
        elif summary_len < 50: gap_score += 1
        if not labels: gap_score += 1

        if gap_score > 0:
            gaps.append({
                "uuid": n["uuid"], "name": n["name"], "summary": n.get("summary", ""),
                "labels": labels, "connections": connections, "summary_length": summary_len,
                "gap_score": gap_score,
                "reasons": [r for r in [
                    "isolated" if connections == 0 else ("under-connected" if connections <= 2 else None),
                    "thin summary" if summary_len < 50 else None,
                    "no labels" if not labels else None,
                ] if r],
            })

    gaps.sort(key=lambda g: g["gap_score"], reverse=True)
    return gaps[:max_results]



async def delete_node(hub_id: str, uuid: str) -> bool:
    """Delete an entity node and all its edges."""
    driver = await _get_driver(hub_id)
    records, _, _ = await driver.execute_query(
        "MATCH (n:Entity {uuid: $uuid, group_id: $gid}) DETACH DELETE n RETURN count(n) AS cnt",
        uuid=uuid, gid=hub_id,
    )
    return records[0]["cnt"] > 0 if records else False


import re as _re

# Patterns that indicate garbage entities extracted from web page chrome
_GARBAGE_PATTERNS = [
    _re.compile(r'^(Terms of Service|Privacy Policy|Cookie Policy|Help Center|Imprint|Sign [Ii]n|Log [Ii]n|Subscribe|Newsletter|Contact [Uu]s|About [Uu]s|FAQ|Sitemap|Accessibility|Disclaimer)$', _re.IGNORECASE),
    _re.compile(r'^@\w+$'),  # Twitter handles
    _re.compile(r'^.{1,2}$'),  # Too short (1-2 chars)
    _re.compile(r'^(JavaScript|CSS|HTML|JSON|XML|HTTP|HTTPS|www\..+)$', _re.IGNORECASE),  # Web tech
    _re.compile(r'^\d+$'),  # Pure numbers
]


async def cleanup_garbage_entities(hub_id: str) -> dict:
    """Delete garbage entities. Returns {deleted: int, names: [str]}."""
    nodes = await get_all_nodes(hub_id)
    edges = await get_all_edges(hub_id)

    # Build connection count
    conn = {}
    for e in edges:
        conn[e.get("source_node_uuid", "")] = conn.get(e.get("source_node_uuid", ""), 0) + 1
        conn[e.get("target_node_uuid", "")] = conn.get(e.get("target_node_uuid", ""), 0) + 1

    deleted_names = []
    for n in nodes:
        name = n["name"]
        should_delete = False

        # Pattern match
        for p in _GARBAGE_PATTERNS:
            if p.match(name):
                should_delete = True
                break

        # Orphan with no summary (unconnected + undescribed = garbage)
        if not should_delete:
            connections = conn.get(n["uuid"], 0)
            summary_len = len(n.get("summary", "") or "")
            if connections == 0 and summary_len < 5:
                should_delete = True

        if should_delete:
            try:
                await delete_node(hub_id, n["uuid"])
                deleted_names.append(name)
            except Exception:
                pass

    return {"deleted": len(deleted_names), "names": deleted_names[:20]}


async def close_all():
    """Close all Graphiti connections."""
    for client in _clients.values():
        await client.close()
    _clients.clear()
