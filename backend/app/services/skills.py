import json
import time
import httpx
from abc import ABC, abstractmethod
from .search import search_papers, search_arxiv
from . import websearch, browser


class SkillHandler(ABC):
    """Base class for skill handlers."""
    skill_type: str = ""
    name: str = ""
    description: str = ""
    input_schema: dict = {}

    @abstractmethod
    async def execute(self, input_data: dict, config: dict) -> dict:
        pass


class WebSearchSkill(SkillHandler):
    skill_type = "web_search"
    name = "Web Search"
    description = "Search the web for any topic via SearXNG (self-hosted, no API keys needed)"
    input_schema = {"query": "str (required)", "limit": "int (default 10)", "category": "str (general|news|images)"}

    async def execute(self, input_data: dict, config: dict) -> dict:
        query = input_data.get("query", "")
        limit = input_data.get("limit", 10)
        category = input_data.get("category", "general")
        if not query:
            return {"error": "query is required", "results": []}

        results = await websearch.search(query, limit=limit, categories=category)
        return {"query": query, "results": results, "total": len(results)}


class BrowserSkill(SkillHandler):
    skill_type = "browser"
    name = "Browser"
    description = "Fetch and render web pages using headless Chrome (handles JavaScript-heavy sites)"
    input_schema = {"url": "str (required)", "action": "str (fetch|screenshot|links, default fetch)"}

    async def execute(self, input_data: dict, config: dict) -> dict:
        url = input_data.get("url", "")
        action = input_data.get("action", "fetch")
        if not url:
            return {"error": "url is required"}

        if action == "screenshot":
            img_bytes = await browser.screenshot(url)
            if img_bytes:
                import base64
                return {"url": url, "screenshot_b64": base64.b64encode(img_bytes).decode(), "format": "png"}
            return {"url": url, "error": "Screenshot failed"}
        elif action == "links":
            links = await browser.extract_links(url)
            return {"url": url, "links": links, "total": len(links)}
        else:
            result = await browser.fetch_page(url)
            return result


class PaperSearchSkill(SkillHandler):
    skill_type = "paper_search"
    name = "Paper Search"
    description = "Search academic papers from Semantic Scholar and arXiv"
    input_schema = {"query": "str (required)", "limit": "int (default 10)"}

    async def execute(self, input_data: dict, config: dict) -> dict:
        query = input_data.get("query", "")
        limit = input_data.get("limit", 10)
        if not query:
            return {"error": "query is required", "results": []}

        scholar = await search_papers(query, limit=limit)
        arxiv = await search_arxiv(query, limit=min(limit // 2, 5))
        results = scholar + arxiv
        return {"results": results, "total": len(results)}


class UrlIngestSkill(SkillHandler):
    skill_type = "url_ingest"
    name = "URL Ingest"
    description = "Fetch a URL (using headless Chrome), extract content, and add it to the knowledge graph"
    input_schema = {"url": "str (required)", "name": "str (optional)"}

    async def execute(self, input_data: dict, config: dict) -> dict:
        url = input_data.get("url", "")
        name = input_data.get("name", url)
        hub_id = config.get("hub_id", "")
        if not url or not hub_id:
            return {"error": "url and hub_id are required"}

        # Use browser to get rendered content first
        page = await browser.fetch_page(url)
        if not page.get("success"):
            return {"error": f"Failed to fetch: {page.get('error', 'unknown')}"}

        # Ingest the extracted text
        from .ingest import _ingest_text
        text = f"Source: {name}\nURL: {url}\n\n{page.get('text', '')}"
        result = await _ingest_text(hub_id, f"URL: {name}", text[:5000])
        result["page_title"] = page.get("title", "")
        return result


class TextAnalysisSkill(SkillHandler):
    skill_type = "text_analysis"
    name = "Text Analysis"
    description = "Analyze text and extract entities/relationships into the knowledge graph"
    input_schema = {"text": "str (required)", "name": "str (optional)"}

    async def execute(self, input_data: dict, config: dict) -> dict:
        text = input_data.get("text", "")
        name = input_data.get("name", "Text analysis")
        hub_id = config.get("hub_id", "")
        if not text or not hub_id:
            return {"error": "text and hub_id are required"}

        from .ingest import _ingest_text
        return await _ingest_text(hub_id, name, text[:5000])


class DeepResearchSkill(SkillHandler):
    skill_type = "deep_research"
    name = "Deep Research"
    description = "Web search + browser fetch combined: search for a topic, fetch top results, extract content"
    input_schema = {"query": "str (required)", "depth": "int (how many pages to fetch, default 3)"}

    async def execute(self, input_data: dict, config: dict) -> dict:
        query = input_data.get("query", "")
        depth = min(input_data.get("depth", 3), 5)
        if not query:
            return {"error": "query is required"}

        search_results = await websearch.search(query, limit=depth + 2)
        if not search_results:
            return {"query": query, "error": "No search results", "pages": []}

        pages = []
        for sr in search_results[:depth]:
            url = sr.get("url", "")
            if not url:
                continue
            try:
                page = await browser.fetch_page(url)
                if page.get("success"):
                    pages.append({
                        "url": url,
                        "title": page.get("title", sr.get("title", "")),
                        "text": page.get("text", "")[:2000],
                    })
            except Exception:
                pass

        return {
            "query": query,
            "search_results": len(search_results),
            "pages_fetched": len(pages),
            "pages": pages,
        }



SKILL_REGISTRY: dict[str, type[SkillHandler]] = {
    "web_search": WebSearchSkill,
    "browser": BrowserSkill,
    "paper_search": PaperSearchSkill,
    "url_ingest": UrlIngestSkill,
    "text_analysis": TextAnalysisSkill,
    "deep_research": DeepResearchSkill,
}

DEFAULT_SKILLS = ["web_search", "browser", "paper_search", "url_ingest", "text_analysis", "deep_research"]


def get_skill_handler(skill_type: str) -> SkillHandler | None:
    cls = SKILL_REGISTRY.get(skill_type)
    return cls() if cls else None


def list_available_skills() -> list[dict]:
    return [
        {"skill_type": cls.skill_type, "name": cls.name, "description": cls.description, "input_schema": cls.input_schema}
        for cls in SKILL_REGISTRY.values()
    ]


async def execute_skill(skill_type: str, input_data: dict, config: dict) -> dict:
    """Execute a skill and return its output."""
    handler = get_skill_handler(skill_type)
    if not handler:
        return {"error": f"Unknown skill type: {skill_type}"}

    start = time.time()
    try:
        result = await handler.execute(input_data, config)
        result["_duration_ms"] = int((time.time() - start) * 1000)
        return result
    except Exception as e:
        return {"error": str(e), "_duration_ms": int((time.time() - start) * 1000)}
