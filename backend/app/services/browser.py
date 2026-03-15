import os
import httpx


BROWSERLESS_URL = os.environ.get("BROWSERLESS_URL", "ws://localhost:3300")
BROWSERLESS_HTTP = BROWSERLESS_URL.replace("ws://", "http://").replace(":3000", ":3000")
BROWSERLESS_TOKEN = os.environ.get("BROWSERLESS_TOKEN", "mobhub123")


async def fetch_page(url: str, wait_for: str = None, timeout: int = 20000) -> dict:
    """
    Fetch a page using Browserless headless Chrome.
    Returns {url, title, text, html_length, screenshot_available}.
    Uses the Browserless /content API for rendered page content.
    """
    http_base = BROWSERLESS_HTTP.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Use Browserless /content endpoint for rendered HTML
            resp = await client.post(
                f"{http_base}/content",
                params={"token": BROWSERLESS_TOKEN},
                json={
                    "url": url,
                    "gotoOptions": {"waitUntil": "networkidle2", "timeout": timeout},
                    "waitForSelector": wait_for if wait_for else None,
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            html = resp.text

        # Extract text
        text = _extract_text(html)
        title = _extract_title(html)

        return {
            "url": url,
            "title": title,
            "text": text[:8000],
            "html_length": len(html),
            "success": True,
        }
    except Exception as e:
        # Fallback to simple httpx fetch (no JS rendering)
        return await _simple_fetch(url, str(e))


async def screenshot(url: str, width: int = 1280, height: int = 720) -> bytes | None:
    """Take a screenshot of a URL. Returns PNG bytes or None."""
    http_base = BROWSERLESS_HTTP.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{http_base}/screenshot",
                params={"token": BROWSERLESS_TOKEN},
                json={
                    "url": url,
                    "gotoOptions": {"waitUntil": "networkidle2"},
                    "options": {"type": "png", "fullPage": False},
                    "viewport": {"width": width, "height": height},
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.content
    except Exception:
        return None


async def extract_links(url: str) -> list[dict]:
    """Extract all links from a page."""
    result = await fetch_page(url)
    if not result.get("success"):
        return []

    # Simple link extraction from the fetched HTML
    import re
    html = result.get("_html", "")
    links = []
    for match in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>', html, re.IGNORECASE):
        href, text = match.groups()
        if href.startswith("http"):
            links.append({"url": href, "text": text.strip()[:100]})

    return links[:50]


async def _simple_fetch(url: str, browser_error: str = "") -> dict:
    """Fallback: fetch without browser rendering."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "MobHub/1.0"})
            resp.raise_for_status()
            html = resp.text

        text = _extract_text(html)
        title = _extract_title(html)

        return {
            "url": url,
            "title": title,
            "text": text[:8000],
            "html_length": len(html),
            "success": True,
            "note": f"Simple fetch (browser unavailable: {browser_error})" if browser_error else "Simple fetch",
        }
    except Exception as e:
        return {"url": url, "success": False, "error": str(e)}


def _extract_text(html: str) -> str:
    """Extract text from HTML."""
    try:
        import trafilatura
        text = trafilatura.extract(html)
        if text:
            return text
    except ImportError:
        pass

    import re
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _extract_title(html: str) -> str:
    import re
    match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""
