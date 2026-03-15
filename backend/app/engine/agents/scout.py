import asyncio
import logging
from ..agent import BaseAgent, AgentPersonality
from ..events import Event, EventType

logger = logging.getLogger("engine.agents.scout")


class ScoutAgent(BaseAgent):
    """
    General-purpose web discoverer. Searches the web, filters for relevance,
    browses promising pages, and ingests only content directly related to the hub topic.
    """

    def __init__(self, hub_id: str, hub_name: str = "", topic: str = "", **kwargs):
        super().__init__(
            hub_id=hub_id,
            agent_type="scout",
            name="Scout",
            personality=AgentPersonality(
                approach="thorough but focused",
                expertise=["web research", "source discovery", "relevance filtering"],
                style="reports findings concisely with source attribution",
            ),
            **kwargs,
        )
        self.hub_name = hub_name
        self.topic = topic

    def get_triggers(self) -> list[EventType]:
        return [EventType.HUB_CREATED, EventType.USER_INSTRUCTION]

    async def handle_event(self, event: Event):
        if event.type == EventType.HUB_CREATED:
            await self._initial_discovery(event)
        elif event.type == EventType.USER_INSTRUCTION:
            instruction = event.data.get("text", "")
            target = event.data.get("target_agent_id")
            if target and target != self.id:
                return
            if event.data.get("from_synthesizer") and self.memory.get("discovery_rounds", 0) >= 6:
                return
            await self._directed_search(instruction)

    async def _initial_discovery(self, event: Event):
        """Focused discovery when a hub is first created."""
        hub_name = event.data.get("hub_name", self.hub_name)
        topic = event.data.get("topic", self.topic) or hub_name

        self.log_action("discovery", f"Starting discovery for: {topic}")

        # Plan focused search queries
        queries = await self._plan_searches(topic)
        self.log_action("plan", f"Search plan: {len(queries)} queries", {"queries": queries})

        total_ingested = 0
        for query in queries:
            ingested = await self._search_and_ingest(query, browse_top=2)
            total_ingested += ingested

            if ingested > 0:
                await self.emit(EventType.SOURCE_INGESTED, {
                    "source_type": "web_discovery",
                    "count": ingested,
                    "query": query,
                    "topic": topic,
                })

            await asyncio.sleep(0.5)

        self.log_action("complete", f"Initial discovery done. Ingested {total_ingested} sources.")

        self.memory["last_search_topic"] = topic
        self.memory["sources_ingested"] = self.memory.get("sources_ingested", 0) + total_ingested
        self.memory["discovery_rounds"] = self.memory.get("discovery_rounds", 0) + 1

    async def _plan_searches(self, topic: str) -> list[str]:
        """Generate focused search queries that stay on-topic."""
        llm = self.tools.get("llm_chat")
        if not llm:
            return [topic, f"what is {topic}", f"{topic} team founders"]

        try:
            response = await llm(messages=[
                {"role": "system", "content": f"""Generate 4-5 web search queries to build knowledge about: {topic}

Rules:
- Every query MUST include the topic name "{topic}" to stay focused
- Cover: what it is, who's behind it, what they've built, recent developments
- Do NOT generate generic queries that would pull in unrelated results
- Each query should target DIRECT information about {topic}, not tangential topics

Return only the queries, one per line. No numbering."""},
                {"role": "user", "content": topic},
            ], max_tokens=200)
            queries = [q.strip().strip('"').strip("'") for q in response.strip().split("\n") if q.strip() and len(q.strip()) > 3]
            return queries[:5] if queries else [topic]
        except Exception:
            return [topic, f"what is {topic}", f"{topic} founders team"]

    async def _search_and_ingest(self, query: str, browse_top: int = 2) -> int:
        """Search web, filter for relevance, browse top results, ingest."""
        web_search = self.tools.get("web_search")
        browse = self.tools.get("browse_url")
        add_episode = self.tools.get("graph_add_episode")
        llm = self.tools.get("llm_chat")

        if not web_search or not add_episode:
            return 0

        try:
            results = await web_search(query=query, limit=8)
            self.log_action("search", f"'{query[:50]}' -> {len(results)} results")
        except Exception as e:
            self.log_action("search", f"Search failed: '{query[:40]}': {e}", status="failed")
            return 0

        if not results:
            return 0

        ingested = 0
        topic_lower = (self.topic or self.hub_name or "").lower()
        ingested_urls = self.memory.get("ingested_urls", [])

        # Browse top results for full page content
        if browse:
            for result in results[:browse_top]:
                url = result.get("url", "")
                title = result.get("title", "")
                if not url or url in ingested_urls:
                    continue

                # Quick relevance check on title/snippet
                snippet = result.get("content", "")
                if not self._quick_relevance_check(title, snippet, topic_lower):
                    self.log_action("skip", f"Skipped irrelevant: {title[:50]}")
                    continue

                try:
                    page = await browse(url=url)
                    page_text = page.get("text", "") if isinstance(page, dict) else ""
                    if page_text and len(page_text) > 200:
                        # LLM relevance filter — only ingest if content is actually about our topic
                        if llm:
                            relevant = await self._check_content_relevance(llm, title, page_text[:1500])
                            if not relevant:
                                self.log_action("skip", f"Content not relevant: {title[:50]}")
                                continue

                        episode_text = f"Source: {title or page.get('title', url)}\nURL: {url}\n\n{page_text[:4000]}"
                        await add_episode(
                            hub_id=self.hub_id,
                            name=f"{title[:80] or url[:80]}",
                            content=episode_text,
                            source_desc=f"Web: {query}",
                        )
                        ingested += 1
                        ingested_urls.append(url)
                        self.log_action("ingest", f"Browsed & ingested: {title[:50]}")
                except Exception as e:
                    self.log_action("browse", f"Browse failed: {url[:50]}: {e}", status="failed")

        # Ingest remaining search snippets (with relevance filter)
        for result in results[browse_top:browse_top + 4]:
            title = result.get("title", "")
            content = result.get("content", "")
            url = result.get("url", "")
            if not content or len(content) < 50:
                continue
            if url in ingested_urls:
                continue

            if not self._quick_relevance_check(title, content, topic_lower):
                continue

            try:
                episode_text = f"Source: {title}\nURL: {url}\n\n{content}"
                await add_episode(
                    hub_id=self.hub_id,
                    name=f"{title[:80]}",
                    content=episode_text,
                    source_desc=f"Web: {query}",
                )
                ingested += 1
                ingested_urls.append(url)
                self.log_action("ingest", f"Ingested snippet: {title[:50]}")
            except Exception as e:
                self.log_action("ingest", f"Failed: {title[:40]}: {e}", status="failed")

        # Persist ingested URLs
        self.memory["ingested_urls"] = ingested_urls[-200:]  # cap at 200

        return ingested

    def _quick_relevance_check(self, title: str, content: str, topic_lower: str) -> bool:
        """Fast heuristic: does this content mention the hub topic?"""
        if not topic_lower:
            return True
        text = f"{title} {content}".lower()
        # Check if any significant word from the topic appears
        topic_words = [w for w in topic_lower.split() if len(w) > 3]
        if not topic_words:
            return topic_lower in text
        return any(w in text for w in topic_words)

    async def _check_content_relevance(self, llm, title: str, content_preview: str) -> bool:
        """LLM check: is this content primarily about our hub topic?"""
        try:
            verdict = await llm(messages=[
                {"role": "system", "content": f"""Is this content primarily about or directly relevant to "{self.topic or self.hub_name}"?

Answer YES if it's about:
- The entity itself (what it is, what it does)
- People who work at/founded/lead it
- Products, projects, or research it has produced
- Direct partnerships or collaborations

Answer NO if it's:
- About a completely different topic that just mentions it in passing
- Generic industry news not focused on this entity
- A list/directory page with many unrelated items

Reply ONLY: YES or NO"""},
                {"role": "user", "content": f"Title: {title}\nContent: {content_preview[:800]}"},
            ], max_tokens=5)
            return "YES" in verdict.upper()
        except Exception:
            return True  # on failure, allow ingestion

    async def _directed_search(self, instruction: str):
        """Handle a user instruction or synthesizer gap-fill request."""
        self.log_action("search", f"Directed: {instruction[:80]}")

        llm = self.tools.get("llm_chat")
        if llm:
            try:
                response = await llm(messages=[
                    {"role": "system", "content": f"You are a scout for a knowledge hub about '{self.topic or self.hub_name}'. Turn this instruction into 2-3 specific web search queries. Each query MUST include '{self.topic or self.hub_name}' to stay focused. Return only queries, one per line."},
                    {"role": "user", "content": instruction},
                ], max_tokens=200)
                queries = [q.strip().strip('"') for q in response.strip().split("\n") if q.strip() and len(q.strip()) > 3]
            except Exception:
                queries = [f"{self.topic or self.hub_name} {instruction}"]
        else:
            queries = [f"{self.topic or self.hub_name} {instruction}"]

        total_ingested = 0
        for query in queries[:3]:
            ingested = await self._search_and_ingest(query, browse_top=1)
            total_ingested += ingested

            if ingested > 0:
                await self.emit(EventType.SOURCE_INGESTED, {
                    "source_type": "directed_search",
                    "count": ingested,
                    "query": query,
                })

            await asyncio.sleep(0.3)

        self.log_action("complete", f"Directed search done. Ingested {total_ingested} sources.")
        self.memory["sources_ingested"] = self.memory.get("sources_ingested", 0) + total_ingested
        self.memory["discovery_rounds"] = self.memory.get("discovery_rounds", 0) + 1
