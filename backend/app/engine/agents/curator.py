import logging
from ..agent import BaseAgent, AgentPersonality
from ..events import Event, EventType

logger = logging.getLogger("engine.agents.curator")


class CuratorAgent(BaseAgent):
    """
    The quality controller. Cleans garbage entities, merges duplicates,
    and prunes entities that aren't relevant to the hub topic.
    """

    def __init__(self, hub_id: str, hub_name: str = "", topic: str = "", **kwargs):
        super().__init__(
            hub_id=hub_id,
            agent_type="curator",
            name="Curator",
            personality=AgentPersonality(
                approach="meticulous and quality-focused",
                expertise=["data quality", "deduplication", "entity resolution"],
                style="reports cleanup actions with counts",
                risk_tolerance=0.3,
            ),
            **kwargs,
        )
        self.hub_name = hub_name
        self.topic = topic
        self._ingestion_count = 0
        self._cleanup_interval = 3
        self._pruned: set[str] = set()  # track pruned entity UUIDs
        self._prune_done = False  # only do full prune once

    def get_triggers(self) -> list[EventType]:
        return [EventType.SOURCE_INGESTED, EventType.QUALITY_ISSUE]

    async def handle_event(self, event: Event):
        if event.type == EventType.SOURCE_INGESTED:
            self._ingestion_count += 1
            if self._ingestion_count >= self._cleanup_interval:
                await self._run_cleanup()
                self._ingestion_count = 0
        elif event.type == EventType.QUALITY_ISSUE:
            await self._handle_quality_issue(event)

    async def _run_cleanup(self):
        """Run garbage cleanup + duplicate merge + relevance prune."""
        self.log_action("cleanup", "Running cleanup cycle")

        cleanup = self.tools.get("graph_cleanup")
        if cleanup:
            try:
                result = await cleanup(hub_id=self.hub_id)
                deleted = result.get("deleted", 0)
                if deleted > 0:
                    self.log_action("cleanup", f"Removed {deleted} garbage entities", {
                        "examples": result.get("names", [])[:5],
                    })
                self.memory["total_cleaned"] = self.memory.get("total_cleaned", 0) + deleted
            except Exception as e:
                self.log_action("cleanup", f"Cleanup failed: {e}", status="failed")

        await self._check_duplicates()

        if not self._prune_done:
            get_stats = self.tools.get("graph_get_stats")
            if get_stats:
                stats = await get_stats(hub_id=self.hub_id)
                if stats.get("nodes", 0) >= 30:
                    await self._prune_irrelevant()
                    self._prune_done = True

    async def _check_duplicates(self):
        """Find and merge duplicate entities."""
        get_nodes = self.tools.get("graph_get_nodes")
        merge = self.tools.get("graph_merge_nodes")
        if not get_nodes:
            return

        try:
            nodes = await get_nodes(hub_id=self.hub_id)
            if len(nodes) < 2:
                return

            name_map: dict[str, list] = {}
            for n in nodes:
                key = n["name"].lower().strip()
                if key not in name_map:
                    name_map[key] = []
                name_map[key].append(n)

            duplicates = {k: v for k, v in name_map.items() if len(v) > 1}
            if duplicates and merge:
                merged = 0
                for name, dupes in duplicates.items():
                    if len(dupes) == 2:
                        try:
                            await merge(hub_id=self.hub_id, source_uuid=dupes[1]["uuid"], target_uuid=dupes[0]["uuid"])
                            merged += 1
                            self.log_action("merge", f"Merged duplicate: {name}")
                        except Exception:
                            pass
                if merged:
                    self.log_action("cleanup", f"Merged {merged} duplicate groups")
                    self.memory["total_merged"] = self.memory.get("total_merged", 0) + merged
            elif duplicates:
                self.log_action("flag", f"Found {len(duplicates)} potential duplicates")
        except Exception as e:
            logger.debug(f"Duplicate check failed: {e}")

    async def _prune_irrelevant(self):
        """Use LLM to identify and remove entities that don't belong in this hub."""
        get_nodes = self.tools.get("graph_get_nodes")
        llm = self.tools.get("llm_chat")
        delete_node = self.tools.get("graph_cleanup")  # we'll use direct deletion

        if not get_nodes or not llm:
            return

        topic = self.topic or self.hub_name
        if not topic:
            return

        self.log_action("prune", f"Pruning entities irrelevant to: {topic}")

        try:
            nodes = await get_nodes(hub_id=self.hub_id)
            if not nodes:
                return

            entity_names = [
                {"name": n["name"], "uuid": n["uuid"], "summary": (n.get("summary") or "")[:60]}
                for n in nodes
                if n["name"] not in self._pruned
                and len(n["name"]) > 2
                and n["name"].lower() != topic.lower()  # never prune the main entity
            ]

            if not entity_names:
                return

            from ..services import graph
            total_pruned = 0

            for i in range(0, len(entity_names), 20):
                batch = entity_names[i:i + 20]
                entity_list = "\n".join(
                    f"- {e['name']}: {e['summary']}" for e in batch
                )

                try:
                    verdict = await llm(messages=[
                        {"role": "system", "content": f"""This knowledge hub is about: {topic}

Review these entities and identify which ones are NOT relevant to {topic}.

An entity is IRRELEVANT if:
- It's a generic concept not specific to {topic} (e.g. "Privacy Policy", "Terms of Service")
- It's an unrelated company/person with no direct connection to {topic}
- It's a description fragment, not a real entity (e.g. "full professor in area of...")
- It's too generic to be useful (e.g. "research", "technology", "company")

An entity IS relevant if:
- It's a person who works at/founded/leads {topic}
- It's a product/project created by {topic}
- It's a direct partner, competitor, or closely related org
- It's a specific technology or concept central to {topic}'s work

List ONLY the names of IRRELEVANT entities, one per line. If all are relevant, reply with NONE."""},
                        {"role": "user", "content": entity_list},
                    ], max_tokens=300)

                    if "NONE" in verdict.upper().strip():
                        continue

                    irrelevant_names = {
                        line.strip().lstrip("- ").strip()
                        for line in verdict.strip().split("\n")
                        if line.strip() and line.strip().upper() != "NONE"
                    }

                    for entity in batch:
                        if entity["name"] in irrelevant_names:
                            try:
                                driver = await graph._get_driver(self.hub_id)
                                await driver.execute_query(
                                    "MATCH (n:Entity {uuid: $uuid, group_id: $gid}) DETACH DELETE n",
                                    uuid=entity["uuid"], gid=self.hub_id,
                                )
                                self._pruned.add(entity["name"])
                                total_pruned += 1
                            except Exception:
                                pass

                except Exception as e:
                    logger.debug(f"Prune batch failed: {e}")

            if total_pruned > 0:
                self.log_action("prune", f"Pruned {total_pruned} irrelevant entities from graph")
                self.memory["total_pruned"] = self.memory.get("total_pruned", 0) + total_pruned
            else:
                self.log_action("prune", "No irrelevant entities found")

        except Exception as e:
            self.log_action("prune", f"Prune failed: {e}", status="failed")

    async def _handle_quality_issue(self, event: Event):
        """Handle a reported quality issue."""
        issue_type = event.data.get("type", "unknown")
        self.log_action("quality", f"Quality issue: {issue_type}", event.data)
