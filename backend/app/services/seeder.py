import asyncio
from .search import search_papers, search_arxiv
from .graph import get_graphiti
from graphiti_core.nodes import EpisodeType
from datetime import datetime, timezone


async def seed_hub(hub_id: str, topic: str, num_papers: int = 20):
    """
    Seed a hub's graph with real academic papers.

    1. Search Semantic Scholar + arXiv for papers on the topic
    2. Feed paper abstracts as episodes into Graphiti
    3. Graphiti auto-extracts entities and relationships
    """
    scholar_papers = await search_papers(topic, limit=num_papers)
    arxiv_papers = await search_arxiv(topic, limit=min(num_papers // 2, 10))
    all_papers = scholar_papers + arxiv_papers

    if not all_papers:
        return {"papers_found": 0, "episodes_added": 0}

    client = await get_graphiti(hub_id)
    added = 0

    for paper in all_papers:
        if not paper.get("abstract"):
            continue

        authors = ", ".join(paper.get("authors", []))
        year = paper.get("year", "unknown")
        title = paper.get("title", "Untitled")
        abstract = paper.get("abstract", "")
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
                name=f"Paper: {title[:80]}",
                episode_body=episode_text,
                source=EpisodeType.text,
                source_description=f"Seed paper from {paper.get('source', 'unknown')}",
                group_id=hub_id,
                reference_time=datetime.now(timezone.utc),
            )
            added += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"  Failed to add episode for '{title[:50]}': {e}")
            continue

    return {"papers_found": len(all_papers), "episodes_added": added}
