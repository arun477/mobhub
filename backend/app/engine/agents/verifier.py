import logging
from ..agent import BaseAgent, AgentPersonality
from ..events import Event, EventType

logger = logging.getLogger("engine.agents.verifier")


class VerifierAgent(BaseAgent):
    """
    The skeptic. Wakes when new facts are created.
    Cross-references claims against web sources to catch hallucinations.
    """

    def __init__(self, hub_id: str, **kwargs):
        super().__init__(
            hub_id=hub_id,
            agent_type="verifier",
            name="Verifier",
            personality=AgentPersonality(
                approach="skeptical and precise",
                expertise=["fact-checking", "source verification", "claim analysis"],
                style="flags issues clearly with evidence",
                risk_tolerance=0.2,
            ),
            **kwargs,
        )
        self._check_queue: list[dict] = []
        self._batch_size = 5
        self._checks_done = 0
        self._max_checks = 5              # max verification batches (each = web search + LLM)
        self._spot_checks_done = 0
        self._max_spot_checks = 3

    def get_triggers(self) -> list[EventType]:
        return [EventType.FACT_CREATED, EventType.SOURCE_INGESTED]

    async def handle_event(self, event: Event):
        if event.type == EventType.FACT_CREATED:
            self._check_queue.append(event.data)
            if len(self._check_queue) >= self._batch_size and self._checks_done < self._max_checks:
                self._checks_done += 1
                await self._verify_batch()
        elif event.type == EventType.SOURCE_INGESTED:
            if self._spot_checks_done < self._max_spot_checks:
                self._spot_checks_done += 1
                await self._spot_check(event)

    async def _verify_batch(self):
        """Verify a batch of facts."""
        facts = self._check_queue[:self._batch_size]
        self._check_queue = self._check_queue[self._batch_size:]

        self.log_action("verify", f"Verifying batch of {len(facts)} facts")

        llm = self.tools.get("llm_chat")
        web_search = self.tools.get("web_search")

        for fact_data in facts:
            fact = fact_data.get("fact", "")
            if not fact or len(fact) < 10:
                continue

            # Search for corroboration
            if web_search:
                try:
                    results = await web_search(query=fact[:100], limit=3)
                    has_support = any(r.get("content", "") for r in results)

                    if not has_support and llm:
                        # Ask LLM if this fact seems plausible
                        check = await llm(messages=[
                            {"role": "system", "content": "You are a fact checker. Assess if this claim is plausible, suspicious, or clearly wrong. Reply with one word: PLAUSIBLE, SUSPICIOUS, or WRONG."},
                            {"role": "user", "content": fact},
                        ], max_tokens=20)

                        if "WRONG" in check.upper() or "SUSPICIOUS" in check.upper():
                            self.log_action("flag", f"Suspicious fact: {fact[:80]}", {
                                "fact": fact,
                                "assessment": check.strip(),
                            })
                            await self.emit(EventType.QUALITY_ISSUE, {
                                "type": "suspicious_fact",
                                "fact": fact,
                                "assessment": check.strip(),
                                "edge_uuid": fact_data.get("edge_uuid"),
                            })
                except Exception as e:
                    logger.debug(f"Verification search failed: {e}")

        self.memory["facts_checked"] = self.memory.get("facts_checked", 0) + len(facts)

    async def _spot_check(self, event: Event):
        """After ingestion, spot-check some edges for quality."""
        self.log_action("verify", "Spot-checking edges after ingestion")

        graph_search = self.tools.get("graph_search")
        if not graph_search:
            return

        try:
            # Get recent edges
            topic = event.data.get("topic", "")
            edges = await graph_search(hub_id=self.hub_id, query=topic or "recent", limit=5)

            suspicious = []
            for edge in edges:
                fact = edge.get("fact", "")
                # Basic heuristics for suspicious facts
                if len(fact) < 10:
                    suspicious.append({"fact": fact, "reason": "too_short"})
                elif fact.count(",") > 5:
                    suspicious.append({"fact": fact, "reason": "looks_like_list"})

            if suspicious:
                self.log_action("flag", f"Found {len(suspicious)} suspicious edges", {
                    "suspicious": suspicious[:3],
                })
        except Exception as e:
            logger.debug(f"Spot check failed: {e}")
