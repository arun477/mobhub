import logging
from ..agent import BaseAgent, AgentPersonality
from ..events import Event, EventType

logger = logging.getLogger("engine.agents.synthesizer")


class SynthesizerAgent(BaseAgent):
    """
    The big-picture thinker. Wakes at graph milestones.
    Creates overview summaries and identifies what's missing.
    """

    def __init__(self, hub_id: str, **kwargs):
        super().__init__(
            hub_id=hub_id,
            agent_type="synthesizer",
            name="Synthesizer",
            personality=AgentPersonality(
                approach="holistic and strategic",
                expertise=["knowledge synthesis", "gap analysis", "narrative construction"],
                style="produces clear, structured overviews",
            ),
            **kwargs,
        )
        self._overview_count = 0
        self._max_overviews = 3           # max auto-overviews (user instructions bypass this)
        self._last_overview_entities = 0  # prevent re-running if graph hasn't grown

    def get_triggers(self) -> list[EventType]:
        return [EventType.GRAPH_MILESTONE, EventType.USER_INSTRUCTION]

    async def handle_event(self, event: Event):
        if event.type == EventType.GRAPH_MILESTONE:
            # Skip if we've hit the cap or graph hasn't grown enough since last overview
            entity_count = event.data.get("entity_count", 0)
            if self._overview_count >= self._max_overviews:
                return
            if entity_count < self._last_overview_entities + 15:
                return  # need at least 15 new entities since last overview
            self._overview_count += 1
            self._last_overview_entities = entity_count
            await self._create_overview(event)
        elif event.type == EventType.USER_INSTRUCTION:
            target = event.data.get("target_agent_id")
            if target and target != self.id:
                return
            text = event.data.get("text", "")
            if any(w in text.lower() for w in ["overview", "summary", "synthesize", "summarize"]):
                await self._create_overview(event)

    async def _create_overview(self, event: Event):
        """Create a knowledge graph overview."""
        self.log_action("synthesize", "Creating knowledge graph overview")

        get_nodes = self.tools.get("graph_get_nodes")
        get_edges = self.tools.get("graph_get_edges")
        get_stats = self.tools.get("graph_get_stats")
        llm = self.tools.get("llm_chat")

        if not get_nodes or not llm:
            self.log_action("synthesize", "Missing required tools", status="failed")
            return

        try:
            nodes = await get_nodes(hub_id=self.hub_id)
            stats = await get_stats(hub_id=self.hub_id) if get_stats else {}
            edges = await get_edges(hub_id=self.hub_id) if get_edges else []

            if not nodes:
                self.log_action("synthesize", "No entities in graph yet")
                return

            # Build context for LLM
            entity_list = "\n".join(
                f"- {n['name']} [{', '.join(n.get('labels', []))}]: {(n.get('summary') or '')[:100]}"
                for n in nodes[:40]
            )
            edge_list = "\n".join(
                f"- {e.get('name', '?')}: {e.get('fact', '')[:100]}"
                for e in edges[:30]
            )

            overview = await llm(messages=[
                {"role": "system", "content": """You are a knowledge synthesizer. Given a set of entities and relationships, produce:
1. A 2-3 sentence executive summary of what this knowledge graph covers
2. The 3-5 main themes/clusters
3. 2-3 notable gaps or areas that need more exploration
4. Suggested next directions to explore

Be concise and specific."""},
                {"role": "user", "content": f"Graph stats: {stats}\n\nEntities ({len(nodes)}):\n{entity_list}\n\nRelationships ({len(edges)}):\n{edge_list}"},
            ], max_tokens=600)

            self.log_action("synthesize", "Overview complete", {
                "overview": overview,
                "entity_count": len(nodes),
                "edge_count": len(edges),
            })

            # Store the overview
            self.memory["latest_overview"] = overview
            self.memory["overview_entity_count"] = len(nodes)

            # If there are suggested directions, tell the scout
            if "gap" in overview.lower() or "missing" in overview.lower():
                await self.emit(EventType.USER_INSTRUCTION, {
                    "text": f"Based on the overview, explore these gaps:\n{overview}",
                    "from_synthesizer": True,
                })

        except Exception as e:
            self.log_action("synthesize", f"Overview failed: {e}", status="failed")
