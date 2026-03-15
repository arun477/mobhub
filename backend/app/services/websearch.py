import os
import httpx


SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888")


async def search(query: str, limit: int = 10, categories: str = "general") -> list[dict]:
    """
    Search the web via SearXNG. Returns list of {title, url, content}.
    Falls back to a basic approach if SearXNG is unavailable.
    """
    try:
        return await _searxng_search(query, limit, categories)
    except Exception as e:
        print(f"SearXNG search failed: {e}, trying fallback")
        try:
            return await _duckduckgo_fallback(query, limit)
        except Exception as e2:
            print(f"DuckDuckGo fallback also failed: {e2}")
            return []


async def _searxng_search(query: str, limit: int, categories: str) -> list[dict]:
    """Search via self-hosted SearXNG instance."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{SEARXNG_URL}/search", params={
            "q": query, "format": "json", "categories": categories,
            "language": "en", "pageno": 1,
        })
        resp.raise_for_status()
        data = resp.json()

    results = []
    for r in data.get("results", [])[:limit]:
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", "")[:500],
            "engine": r.get("engine", ""),
        })
    return results


async def _duckduckgo_fallback(query: str, limit: int) -> list[dict]:
    """Fallback: use DuckDuckGo instant answer API (limited but free)."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get("https://api.duckduckgo.com/", params={
            "q": query, "format": "json", "no_redirect": 1,
        })
        resp.raise_for_status()
        data = resp.json()

    results = []
    if data.get("Abstract"):
        results.append({
            "title": data.get("Heading", query),
            "url": data.get("AbstractURL", ""),
            "content": data.get("Abstract", "")[:500],
            "engine": "duckduckgo",
        })
    for topic in data.get("RelatedTopics", [])[:limit]:
        if isinstance(topic, dict) and topic.get("Text"):
            results.append({
                "title": topic.get("Text", "")[:100],
                "url": topic.get("FirstURL", ""),
                "content": topic.get("Text", "")[:500],
                "engine": "duckduckgo",
            })

    return results[:limit]


async def search_news(query: str, limit: int = 10) -> list[dict]:
    """Search news via SearXNG."""
    return await search(query, limit, categories="news")


async def search_images(query: str, limit: int = 10) -> list[dict]:
    """Search images via SearXNG."""
    return await search(query, limit, categories="images")
