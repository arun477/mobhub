import json
import httpx
from datetime import datetime, timezone
from .graph import get_graphiti, get_node_uuids, get_edge_uuids
from .search import search_papers, search_arxiv
from graphiti_core.nodes import EpisodeType


async def ingest_source(hub_id: str, source_type: str, name: str,
                        content: str = "", url: str = None,
                        metadata: dict = None) -> dict:
    """
    Ingest a source into the hub's knowledge graph.
    Routes to the appropriate handler based on source_type.
    Returns {episodes_added, entities_new, edges_new}.
    """
    if source_type == "text":
        return await _ingest_text(hub_id, name, content)
    elif source_type == "url":
        return await _ingest_url(hub_id, name, url or content)
    elif source_type == "paper":
        topic = (metadata or {}).get("topic", name)
        limit = (metadata or {}).get("limit", 15)
        return await _ingest_papers(hub_id, topic, limit)
    elif source_type == "document":
        return await _ingest_document(hub_id, name, content, (metadata or {}).get("mime_type", ""))
    else:
        # Fallback: treat as text
        return await _ingest_text(hub_id, name, content)


async def _ingest_text(hub_id: str, name: str, content: str) -> dict:
    """Ingest raw text as a single episode."""
    if not content.strip():
        return {"episodes_added": 0, "entities_new": 0, "edges_new": 0}

    nodes_before = await get_node_uuids(hub_id)
    edges_before = await get_edge_uuids(hub_id)

    client = await get_graphiti(hub_id)
    await client.add_episode(
        name=name, episode_body=content, source=EpisodeType.text,
        source_description=f"Text source: {name}",
        group_id=hub_id, reference_time=datetime.now(timezone.utc),
    )

    nodes_after = await get_node_uuids(hub_id)
    edges_after = await get_edge_uuids(hub_id)

    return {
        "episodes_added": 1,
        "entities_new": len(nodes_after - nodes_before),
        "edges_new": len(edges_after - edges_before),
        "new_node_uuids": list(nodes_after - nodes_before),
        "new_edge_uuids": list(edges_after - edges_before),
    }


async def _ingest_url(hub_id: str, name: str, url: str) -> dict:
    """Fetch a URL, extract text content, ingest as episode."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "MobHub/1.0"})
        resp.raise_for_status()
        html = resp.text

    text = ""
    try:
        import trafilatura
        text = trafilatura.extract(html) or ""
    except ImportError:
        text = _basic_html_extract(html)

    if not text.strip():
        return {"episodes_added": 0, "entities_new": 0, "edges_new": 0, "error": "No text extracted"}

    text = text[:5000]

    episode_text = f"""Source: {name}
URL: {url}

{text}"""

    return await _ingest_text(hub_id, f"URL: {name}", episode_text)


async def _ingest_papers(hub_id: str, topic: str, limit: int = 15) -> dict:
    """Search for papers and ingest them. Wraps existing seeder logic."""
    scholar = await search_papers(topic, limit=limit)
    arxiv = await search_arxiv(topic, limit=min(limit // 2, 10))
    all_papers = scholar + arxiv

    if not all_papers:
        return {"episodes_added": 0, "entities_new": 0, "edges_new": 0, "papers_found": 0}

    import asyncio

    nodes_before = await get_node_uuids(hub_id)
    edges_before = await get_edge_uuids(hub_id)

    client = await get_graphiti(hub_id)
    added = 0

    for paper in all_papers:
        if not paper.get("abstract"):
            continue
        authors = ", ".join(paper.get("authors", []))
        title = paper.get("title", "Untitled")
        abstract = paper.get("abstract", "")
        year = paper.get("year", "unknown")
        doi = paper.get("doi", "")
        citations = paper.get("citations", 0)

        episode_text = f"""Research Paper: "{title}"
Authors: {authors}
Year: {year}
{"DOI: " + doi if doi else ""}
{"Citations: " + str(citations) if citations else ""}

Abstract: {abstract}"""

        try:
            await client.add_episode(
                name=f"Paper: {title[:80]}", episode_body=episode_text,
                source=EpisodeType.text,
                source_description=f"Paper from {paper.get('source', 'unknown')}",
                group_id=hub_id, reference_time=datetime.now(timezone.utc),
            )
            added += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"  Failed to ingest paper '{title[:50]}': {e}")

    nodes_after = await get_node_uuids(hub_id)
    edges_after = await get_edge_uuids(hub_id)

    return {
        "episodes_added": added,
        "papers_found": len(all_papers),
        "entities_new": len(nodes_after - nodes_before),
        "edges_new": len(edges_after - edges_before),
        "new_node_uuids": list(nodes_after - nodes_before),
        "new_edge_uuids": list(edges_after - edges_before),
    }


async def _ingest_document(hub_id: str, name: str, content: str, mime_type: str) -> dict:
    """Parse a document (PDF/DOCX/TXT) and ingest as episodes."""
    text = content  # Already text if uploaded as text

    if mime_type == "application/pdf" or name.lower().endswith(".pdf"):
        try:
            import fitz  # pymupdf
            import base64
            pdf_bytes = base64.b64decode(content) if _is_base64(content) else content.encode()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = "\n\n".join(page.get_text() for page in doc)[:8000]
            doc.close()
        except ImportError:
            return {"episodes_added": 0, "error": "pymupdf not installed"}
        except Exception as e:
            return {"episodes_added": 0, "error": f"PDF parsing failed: {e}"}

    elif mime_type in ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",) or name.lower().endswith(".docx"):
        try:
            from docx import Document
            import base64, io
            doc_bytes = base64.b64decode(content) if _is_base64(content) else content.encode()
            doc = Document(io.BytesIO(doc_bytes))
            text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())[:8000]
        except ImportError:
            return {"episodes_added": 0, "error": "python-docx not installed"}
        except Exception as e:
            return {"episodes_added": 0, "error": f"DOCX parsing failed: {e}"}

    if not text.strip():
        return {"episodes_added": 0, "entities_new": 0, "edges_new": 0, "error": "No text extracted"}

    episode_text = f"""Document: {name}

{text[:5000]}"""

    return await _ingest_text(hub_id, f"Document: {name}", episode_text)


def _basic_html_extract(html: str) -> str:
    """Very basic HTML to text — strips tags."""
    import re
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _is_base64(s: str) -> bool:
    """Check if string looks like base64."""
    import base64
    try:
        base64.b64decode(s[:100], validate=True)
        return len(s) > 100
    except Exception:
        return False
