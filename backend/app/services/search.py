import httpx
import urllib.parse
from ..config import SEMANTIC_SCHOLAR_API


async def search_papers(query: str, limit: int = 10) -> list[dict]:
    """Search Semantic Scholar for real papers."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(
                f"{SEMANTIC_SCHOLAR_API}/paper/search",
                params={
                    "query": query,
                    "limit": limit,
                    "fields": "title,abstract,year,authors,citationCount,url,externalIds",
                },
            )
            r.raise_for_status()
            data = r.json()
            papers = []
            for p in data.get("data", []):
                authors = [a.get("name", "") for a in (p.get("authors") or [])[:5]]
                doi = (p.get("externalIds") or {}).get("DOI", "")
                papers.append({
                    "title": p.get("title", ""),
                    "abstract": (p.get("abstract") or "")[:600],
                    "year": p.get("year"),
                    "authors": authors,
                    "citations": p.get("citationCount", 0),
                    "url": p.get("url", ""),
                    "doi": doi,
                    "source": "semantic_scholar",
                })
            return papers
        except Exception:
            return []


async def search_arxiv(query: str, limit: int = 5) -> list[dict]:
    """Search arXiv for papers."""
    encoded = urllib.parse.quote(query)
    url = f"http://export.arxiv.org/api/query?search_query=all:{encoded}&start=0&max_results={limit}&sortBy=relevance"
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            return _parse_arxiv_xml(r.text)
        except Exception:
            return []


def _parse_arxiv_xml(xml: str) -> list[dict]:
    entries = []
    text = xml
    while "<entry>" in text:
        start = text.index("<entry>")
        end = text.index("</entry>") + len("</entry>")
        entry = text[start:end]
        text = text[end:]

        title = _tag(entry, "title").strip().replace("\n", " ")
        abstract = _tag(entry, "summary").strip().replace("\n", " ")[:600]
        published = _tag(entry, "published")[:10]

        authors = []
        e = entry
        while "<author>" in e:
            a_start = e.index("<author>")
            a_end = e.index("</author>") + len("</author>")
            name = _tag(e[a_start:a_end], "name")
            if name:
                authors.append(name)
            e = e[a_end:]

        entries.append({
            "title": title,
            "abstract": abstract,
            "year": int(published[:4]) if published else None,
            "authors": authors[:5],
            "source": "arxiv",
        })
    return entries


def _tag(xml: str, tag: str) -> str:
    for prefix in [f"<{tag}>", f"<{tag} "]:
        if prefix in xml and f"</{tag}>" in xml:
            s = xml.index(prefix)
            if prefix.endswith(" "):
                s = xml.index(">", s) + 1
            else:
                s += len(prefix)
            e = xml.index(f"</{tag}>")
            return xml[s:e]
    return ""
