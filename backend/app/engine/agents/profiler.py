import logging
from ..agent import BaseAgent, AgentPersonality
from ..events import Event, EventType

logger = logging.getLogger("engine.agents.profiler")


class ProfilerAgent(BaseAgent):
    """
    The enricher. Wakes when entities are flagged for enrichment.
    Does a quick enrichment pass, then contributes importance signals to the runtime.
    The RUNTIME decides when to spawn sub-agents — not the Profiler.
    """

    def __init__(self, hub_id: str, **kwargs):
        super().__init__(
            hub_id=hub_id,
            agent_type="profiler",
            name="Profiler",
            personality=AgentPersonality(
                approach="detail-oriented and structured",
                expertise=["entity enrichment", "structured data extraction", "web profiling"],
                style="provides structured metadata and facts",
            ),
            **kwargs,
        )
        self._enrich_count = 0
        self._max_enrichments = 15

    def _is_enriched(self, uuid: str) -> bool:
        return uuid in self.memory.get("enriched_uuids", [])

    def _mark_enriched(self, uuid: str):
        enriched = self.memory.get("enriched_uuids", [])
        if uuid not in enriched:
            enriched.append(uuid)
            self.memory["enriched_uuids"] = enriched

    def get_triggers(self) -> list[EventType]:
        return [EventType.ENTITY_FLAGGED]

    async def handle_event(self, event: Event):
        if event.type == EventType.ENTITY_FLAGGED:
            reason = event.data.get("reason", "")
            if reason == "needs_enrichment":
                await self._enrich_entity(event.data)

    async def _enrich_entity(self, entity_data: dict):
        """Enrich an entity and contribute importance signals."""
        name = entity_data.get("name", "")
        labels = entity_data.get("labels", [])
        uuid = entity_data.get("uuid", "")

        if not name or self._is_enriched(uuid):
            return
        if self._enrich_count >= self._max_enrichments:
            return

        self._mark_enriched(uuid)
        self._enrich_count += 1

        is_person = "Person" in labels
        is_org = any(l in labels for l in ["Organization", "Company"])

        self.log_action("enrich", f"Enriching: {name} ({self._enrich_count}/{self._max_enrichments})")

        # Quick enrichment: web search + LLM summary
        web_search = self.tools.get("web_search")
        llm = self.tools.get("llm_chat")

        if not web_search or not llm:
            return

        search_queries = [name]
        if is_person:
            search_queries.append(f"{name} role position organization")
        elif is_org:
            search_queries.append(f"{name} company about")

        search_context = ""
        result_count = 0
        for query in search_queries[:2]:
            try:
                results = await web_search(query=query, limit=3)
                result_count += len(results)
                for r in results:
                    if r.get("content"):
                        search_context += f"\n{r['content'][:300]}"
            except Exception:
                pass

        if not search_context:
            self.log_action("enrich", f"No web results for {name}", status="failed")
            return

        # LLM enrichment
        entity_type = "person" if is_person else "organization" if is_org else "entity"
        try:
            extracted = await llm(messages=[
                {"role": "system", "content": f"Extract structured information about this {entity_type}. Return a concise summary (2-3 sentences) with key facts."},
                {"role": "user", "content": f"Entity: {name}\n\nWeb results:\n{search_context[:2000]}"},
            ], max_tokens=300)

            update_node = self.tools.get("graph_update_node")
            if update_node and uuid:
                await update_node(hub_id=self.hub_id, uuid=uuid, summary=extracted[:500])
                self.log_action("enrich", f"Updated {name}", {"summary_preview": extracted[:80]})

        except Exception as e:
            self.log_action("enrich", f"LLM failed for {name}: {e}", status="failed")
            return

        # Contribute importance signal: "enriched with real web data"
        if self._runtime and result_count >= 2:
            self._runtime.add_importance_signal(
                self.hub_id, name, uuid, labels,
                signal="enriched", weight=1,
            )
