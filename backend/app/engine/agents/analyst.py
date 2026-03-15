import logging
from ..agent import BaseAgent, AgentPersonality
from ..events import Event, EventType

logger = logging.getLogger("engine.agents.analyst")


class AnalystAgent(BaseAgent):
    """
    The intelligence layer. Classifies entities, assesses importance,
    and contributes signals that determine which entities deserve sub-agents.
    """

    def __init__(self, hub_id: str, hub_name: str = "", topic: str = "", **kwargs):
        super().__init__(
            hub_id=hub_id,
            agent_type="analyst",
            name="Analyst",
            personality=AgentPersonality(
                approach="analytical and systematic",
                expertise=["graph analysis", "pattern recognition", "entity classification"],
                style="presents findings as structured observations",
            ),
            **kwargs,
        )
        self.hub_name = hub_name
        self.topic = topic
        self._entity_batch: list[dict] = []
        self._batch_threshold = 3
        self._main_entity_uuid: str | None = None

    def _is_flagged(self, name: str) -> bool:
        return name in self.memory.get("flagged_names", [])

    def _mark_flagged(self, name: str):
        flagged = self.memory.get("flagged_names", [])
        if name not in flagged:
            flagged.append(name)
            self.memory["flagged_names"] = flagged

    def _is_classified(self, name: str) -> bool:
        return name in self.memory.get("classified_names", [])

    def _mark_classified(self, name: str):
        classified = self.memory.get("classified_names", [])
        if name not in classified:
            classified.append(name)
            self.memory["classified_names"] = classified

    def get_triggers(self) -> list[EventType]:
        return [EventType.SOURCE_INGESTED, EventType.ENTITY_CREATED, EventType.GRAPH_MILESTONE]

    async def handle_event(self, event: Event):
        if event.type == EventType.SOURCE_INGESTED:
            await self._analyze_new_content(event)
        elif event.type == EventType.ENTITY_CREATED:
            self._entity_batch.append(event.data)
            if len(self._entity_batch) >= self._batch_threshold:
                await self._analyze_entity_batch()
                self._entity_batch = []
        elif event.type == EventType.GRAPH_MILESTONE:
            await self._graph_overview(event)

    async def _analyze_new_content(self, event: Event):
        """Analyze graph after new content ingested."""
        self.log_action("analyze", "Analyzing after ingestion")

        get_stats = self.tools.get("graph_get_stats")
        if get_stats:
            stats = await get_stats(hub_id=self.hub_id)
            self.log_action("analyze", f"Graph: {stats.get('nodes', 0)} entities, {stats.get('edges', 0)} edges")

            node_count = stats.get("nodes", 0)
            last_milestone = self.memory.get("last_milestone", 0)
            if node_count >= last_milestone + 20:
                self.memory["last_milestone"] = node_count
                await self.emit(EventType.GRAPH_MILESTONE, {"entity_count": node_count})

        # Flush pending batch
        if self._entity_batch:
            await self._analyze_entity_batch()
            self._entity_batch = []

    async def _analyze_entity_batch(self):
        """Classify entities, flag for enrichment, contribute importance signals."""
        batch = list(self._entity_batch)
        self.log_action("analyze", f"Analyzing {len(batch)} new entities")

        llm = self.tools.get("llm_chat")

        for entity_data in batch:
            labels = entity_data.get("labels", [])
            name = entity_data.get("name", "")
            uuid = entity_data.get("uuid", "")

            if not name or self._is_flagged(name):
                continue

            name_words = name.split()
            if (len(name) < 3
                    or name.islower()
                    or len(name) > 80  # descriptions, not names
                    or any(w in name.lower() for w in [
                        "exceptional", "various", "other", "several", "multiple",
                        "unknown", "professor in", "researcher in", "area of",
                        "full professor", "associate professor", "department of",
                    ])):
                continue

            real_labels = [l for l in labels if l not in ("Entity", "__Entity__")]
            is_person = "Person" in real_labels
            is_org = any(l in real_labels for l in ["Organization", "Company"])

            if not real_labels and llm and not self._is_classified(name):
                self._mark_classified(name)
                try:
                    classification = await llm(messages=[
                        {"role": "system", "content": "Classify this entity name into ONE category. Reply with ONLY the word: Person, Organization, Concept, Method, Tool, Event, Dataset, Location, or Other"},
                        {"role": "user", "content": name},
                    ], max_tokens=10)
                    category = classification.strip().split()[0].strip(".,")
                    if category == "Person":
                        is_person = True
                        real_labels = ["Person"]
                    elif category in ("Organization", "Company"):
                        is_org = True
                        real_labels = ["Organization"]
                    else:
                        real_labels = [category] if category != "Other" else []

                    if real_labels:
                        update_node = self.tools.get("graph_update_node")
                        if update_node and uuid:
                            try:
                                await update_node(hub_id=self.hub_id, uuid=uuid, labels=real_labels)
                            except Exception:
                                pass
                except Exception:
                    pass

            if is_person or is_org:
                self._mark_flagged(name)
                await self.emit(EventType.ENTITY_FLAGGED, {
                    "uuid": uuid,
                    "name": name,
                    "labels": real_labels or labels,
                    "reason": "needs_enrichment",
                })
                self.log_action("flag", f"Flagged {name} as {'Person' if is_person else 'Org'}")

                if self._runtime:
                    # Signal: entity has proper name (2+ words, capitalized)
                    if len(name_words) >= 2:
                        self._runtime.add_importance_signal(
                            self.hub_id, name, uuid, real_labels or labels,
                            signal="proper_name", weight=1,
                        )

                    # Signal: check graph connectivity + connection to main entity
                    neighbors = self.tools.get("graph_neighbors")
                    if neighbors and uuid:
                        try:
                            nbr_data = await neighbors(hub_id=self.hub_id, uuid=uuid)
                            neighbor_list = nbr_data.get("neighbors", []) if nbr_data else []
                            conn_count = len(neighbor_list)
                            neighbor_names = [n.get("neighbor_name", "").lower() for n in neighbor_list]

                            if conn_count >= 3:
                                self._runtime.add_importance_signal(
                                    self.hub_id, name, uuid, real_labels or labels,
                                    signal="high_connectivity", weight=2,
                                )

                            # Key signal: directly connected to the hub's main entity
                            hub_name_lower = (self.hub_name or self.topic or "").lower()
                            if hub_name_lower and any(hub_name_lower in nn or nn in hub_name_lower for nn in neighbor_names if nn):
                                self._runtime.add_importance_signal(
                                    self.hub_id, name, uuid, real_labels or labels,
                                    signal="connected_to_main", weight=2,
                                )
                                self.log_action("assess", f"{name} directly connected to {self.hub_name}")

                            # Also find and cache the main entity UUID for future checks
                            if not self._main_entity_uuid:
                                for n in neighbor_list:
                                    nn = n.get("neighbor_name", "").lower()
                                    if hub_name_lower and (hub_name_lower in nn or nn in hub_name_lower):
                                        self._main_entity_uuid = n.get("neighbor_uuid")
                                        break
                        except Exception:
                            pass

                    # Signal: LLM assesses importance WITH hub context
                    hub_context = f"This knowledge hub is about: {self.topic or self.hub_name}"

                    if llm and is_person:
                        try:
                            verdict = await llm(messages=[
                                {"role": "system", "content": f"""{hub_context}

Does this person deserve a dedicated research profile? Answer YES only if they are:
- A founder, CEO, CTO, or core team member of the hub's primary subject
- A key researcher or creator directly responsible for the hub topic's main work
- Someone whose role is CENTRAL to understanding the hub topic

Answer NO for: investors, advisors, random employees, paper co-authors, people only tangentially mentioned, generic role descriptions.

Reply ONLY: YES or NO"""},
                                {"role": "user", "content": f"Person: {name}\nContext: {entity_data.get('summary', '')[:150]}"},
                            ], max_tokens=5)
                            if "YES" in verdict.upper():
                                self._runtime.add_importance_signal(
                                    self.hub_id, name, uuid, real_labels or labels,
                                    signal="key_figure", weight=3,
                                )
                                self.log_action("assess", f"{name} → key figure for {self.topic or self.hub_name}")
                        except Exception:
                            pass

                    elif llm and is_org:
                        try:
                            verdict = await llm(messages=[
                                {"role": "system", "content": f"""{hub_context}

Does this organization deserve a dedicated research profile? Answer YES only if it is:
- The primary subject of this hub (e.g. the company/lab the hub is about)
- A direct parent, subsidiary, or core partner of the primary subject

Answer NO for: investors, VCs, funding firms, universities mentioned in passing, generic industry bodies, competitors only briefly mentioned.

Reply ONLY: YES or NO"""},
                                {"role": "user", "content": f"Organization: {name}\nContext: {entity_data.get('summary', '')[:150]}"},
                            ], max_tokens=5)
                            if "YES" in verdict.upper():
                                self._runtime.add_importance_signal(
                                    self.hub_id, name, uuid, real_labels or labels,
                                    signal="central_org", weight=3,
                                )
                                self.log_action("assess", f"{name} → central org for {self.topic or self.hub_name}")
                        except Exception:
                            pass

    async def _graph_overview(self, event: Event):
        """Graph-wide analysis at milestones."""
        self.log_action("analyze", f"Milestone: {event.data.get('entity_count', '?')} entities")

        llm = self.tools.get("llm_chat")
        get_nodes = self.tools.get("graph_get_nodes")

        if llm and get_nodes:
            try:
                nodes = await get_nodes(hub_id=self.hub_id)
                entity_summary = "\n".join(
                    f"- {n['name']} ({', '.join(n.get('labels', []))}): {n.get('summary', '')[:80]}"
                    for n in nodes[:30]
                )

                analysis = await llm(messages=[
                    {"role": "system", "content": "Analyze these entities. Identify: 1) main themes, 2) most important entities, 3) gaps. Be concise."},
                    {"role": "user", "content": f"Entities:\n{entity_summary}"},
                ], max_tokens=500)

                self.log_action("analyze", "Overview complete", {"analysis": analysis[:300]})
                self.memory["last_overview"] = analysis[:500]
            except Exception as e:
                self.log_action("analyze", f"Overview failed: {e}", status="failed")
