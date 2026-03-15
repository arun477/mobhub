from fastapi import APIRouter
from ..services.search import search_papers, search_arxiv
from ..services import websearch, browser

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("/search")
async def search(q: str, limit: int = 10):
    """Search Semantic Scholar for academic papers."""
    return await search_papers(q, limit)


@router.get("/arxiv")
async def arxiv(q: str, limit: int = 5):
    """Search arXiv for papers."""
    return await search_arxiv(q, limit)


@router.get("/web")
async def web_search(q: str, limit: int = 10, category: str = "general"):
    """Search the web via SearXNG (self-hosted, no API keys)."""
    return await websearch.search(q, limit=limit, categories=category)


@router.get("/web/news")
async def news_search(q: str, limit: int = 10):
    """Search news via SearXNG."""
    return await websearch.search_news(q, limit=limit)


@router.get("/browse")
async def browse_url(url: str):
    """Fetch and render a web page using headless Chrome."""
    return await browser.fetch_page(url)


@router.get("/browse/screenshot")
async def browse_screenshot(url: str):
    """Take a screenshot of a URL. Returns base64 PNG."""
    import base64
    img = await browser.screenshot(url)
    if img:
        return {"url": url, "screenshot_b64": base64.b64encode(img).decode(), "format": "png"}
    return {"url": url, "error": "Screenshot failed"}
