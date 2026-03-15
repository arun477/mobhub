import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from .events import EventBus, Event, EventType
from .agent import BaseAgent, AgentAction, AgentStatus
from .tools import ToolRegistry, build_default_tools

logger = logging.getLogger("engine.runtime")


class AgentRuntime:
    """
    The orchestrator. One per application instance.
    Manages the event bus, agent registry, and hub lifecycles.
    """

    def __init__(self):
        self.event_bus = EventBus()
        self.tools: ToolRegistry | None = None

        self._agents: dict[str, BaseAgent] = {}
        self._hub_agents: dict[str, list[str]] = {}
        self._entity_owners: dict[tuple[str, str], str] = {}
        self._hub_topics: dict[str, dict] = {}
        self._importance: dict[tuple[str, str], dict] = {}
        self._spawn_threshold = 5
        self._ws_connections: dict[str, list[Any]] = {}
        self._action_log: list[AgentAction] = []
        self._max_action_log = 1000

        self._started = False

    async def start(self):
        if self._started:
            return
        self.tools = await build_default_tools()
        await self.event_bus.start()

        # Listen for AGENT_COMPLETED to log sub-agent results
        self.event_bus.subscribe(EventType.AGENT_COMPLETED, self._on_agent_completed)

        self._started = True
        logger.info("AgentRuntime started")

    async def stop(self):
        await self.event_bus.stop()
        self._started = False
        logger.info("AgentRuntime stopped")

    def register_agent(self, agent: BaseAgent):
        agent._runtime = self

        # Give agent access to tools
        if self.tools:
            agent.tools = {t.name: t for t in self.tools._tools.values()}

        # Subscribe to events
        for event_type in agent.get_triggers():
            self.event_bus.subscribe(event_type, agent._on_event)

        self._agents[agent.id] = agent

        if agent.hub_id not in self._hub_agents:
            self._hub_agents[agent.hub_id] = []
        self._hub_agents[agent.hub_id].append(agent.id)

        logger.info(f"Agent registered: {agent.name} ({agent.agent_type}) for hub {agent.hub_id[:8]}...")

    def unregister_agent(self, agent_id: str):
        agent = self._agents.get(agent_id)
        if not agent:
            return

        # Unsubscribe from events
        for event_type in agent.get_triggers():
            self.event_bus.unsubscribe(event_type, agent._on_event)

        dead_keys = [k for k, v in self._entity_owners.items() if v == agent_id]
        for k in dead_keys:
            del self._entity_owners[k]

        # Remove from hub tracking
        if agent.hub_id in self._hub_agents:
            self._hub_agents[agent.hub_id] = [
                aid for aid in self._hub_agents[agent.hub_id] if aid != agent_id
            ]

        del self._agents[agent_id]
        logger.info(f"Agent unregistered: {agent.name}")

    def get_agent(self, agent_id: str) -> BaseAgent | None:
        return self._agents.get(agent_id)

    def get_hub_agents(self, hub_id: str) -> list[BaseAgent]:
        agent_ids = self._hub_agents.get(hub_id, [])
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def get_all_agents(self) -> list[BaseAgent]:
        return list(self._agents.values())

    async def spawn_hub_agents(self, hub_id: str, hub_name: str, topic: str = ""):
        """
        Create the default agent team for a new hub.
        This is called when a user creates a hub — no auth needed, instant agents.
        """
        from .agents import (
            ScoutAgent, AnalystAgent, VerifierAgent,
            ProfilerAgent, CuratorAgent, SynthesizerAgent,
        )

        self._hub_topics[hub_id] = {"name": hub_name, "topic": topic}

        agents = [
            ScoutAgent(hub_id=hub_id, hub_name=hub_name, topic=topic),
            AnalystAgent(hub_id=hub_id, hub_name=hub_name, topic=topic),
            VerifierAgent(hub_id=hub_id),
            ProfilerAgent(hub_id=hub_id),
            CuratorAgent(hub_id=hub_id, hub_name=hub_name, topic=topic),
            SynthesizerAgent(hub_id=hub_id),
        ]

        for agent in agents:
            self.register_agent(agent)

        logger.info(f"Spawned {len(agents)} agents for hub {hub_id[:8]}... ({hub_name})")

        await self.event_bus.emit(Event(
            type=EventType.HUB_CREATED,
            hub_id=hub_id,
            data={"hub_name": hub_name, "topic": topic},
        ))

        return agents

    async def stop_hub(self, hub_id: str):
        """Hard stop — pause all agents and mark them stopped."""
        for agent in self.get_hub_agents(hub_id):
            agent.status = AgentStatus.PAUSED
            agent._consecutive_errors = 0  # reset so they can restart cleanly
        logger.info(f"Hard stopped all agents for hub {hub_id[:8]}...")

    async def retire_hub_agents(self, hub_id: str):
        """Remove all agents for a hub — nuclear option."""
        # First pause everything to prevent in-flight events from triggering
        await self.stop_hub(hub_id)
        agent_ids = list(self._hub_agents.get(hub_id, []))
        for aid in agent_ids:
            self.unregister_agent(aid)
        logger.info(f"Retired all agents for hub {hub_id[:8]}...")

    def add_importance_signal(self, hub_id: str, entity_name: str, entity_uuid: str,
                              labels: list[str], signal: str, weight: int = 1):
        """
        Any agent can contribute an importance signal for an entity.
        Signals accumulate. When score crosses threshold, sub-agent spawns automatically.

        Signals:
          - "multi_source" (Analyst: entity appears in multiple episodes) +2
          - "high_connectivity" (Analyst: 3+ graph connections) +2
          - "classified_key_role" (Analyst: LLM says founder/CEO/key person) +3
          - "enriched" (Profiler: successfully enriched with web data) +1
          - "verified" (Verifier: facts about entity confirmed) +1
          - "central_to_topic" (Analyst: directly connected to hub topic entity) +2
        """
        key = (hub_id, entity_name.lower())

        if self.get_entity_owner(hub_id, entity_name):
            return

        if key not in self._importance:
            self._importance[key] = {
                "name": entity_name,
                "uuid": entity_uuid,
                "labels": labels,
                "score": 0,
                "signals": [],
            }

        record = self._importance[key]
        # Don't double-count same signal
        if signal in record["signals"]:
            return

        record["score"] += weight
        record["signals"].append(signal)
        record["uuid"] = entity_uuid or record["uuid"]
        if labels:
            record["labels"] = labels

        logger.info(f"Importance signal: {entity_name} +{weight} ({signal}) = {record['score']}")

        # Check if threshold crossed
        if record["score"] >= self._spawn_threshold:
            # Spawn — no cap, agents decide who's important
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._auto_spawn_profiler(hub_id, record))
            except RuntimeError:
                # No running loop — queue it for later
                logger.warning(f"Cannot spawn sub-agent for {entity_name} (no event loop)")
                pass

    async def _auto_spawn_profiler(self, hub_id: str, record: dict):
        """Spawn a sub-agent when importance threshold is crossed."""
        name = record["name"]
        uuid = record["uuid"]
        labels = record["labels"]

        # Double-check ownership (race condition guard)
        if self.get_entity_owner(hub_id, name):
            return

        is_person = "Person" in labels
        is_org = any(l in labels for l in ["Organization", "Company"])

        if not is_person and not is_org:
            return

        # Find the Profiler agent to be the parent
        profiler = None
        for agent in self.get_hub_agents(hub_id):
            if agent.agent_type == "profiler":
                profiler = agent
                break

        if not profiler:
            return

        from .agents.person_profiler import PersonProfilerAgent
        from .agents.org_profiler import OrgProfilerAgent

        agent_class = PersonProfilerAgent if is_person else OrgProfilerAgent
        child = await self.spawn_subagent(
            profiler, agent_class,
            target_name=name,
            target_uuid=uuid,
        )

        if child:
            # Log on the profiler
            profiler.log_action("spawn",
                f"{'PersonProfiler' if is_person else 'OrgProfiler'} spawned for {name} "
                f"(score={record['score']}, signals={record['signals']})")

    def get_importance(self, hub_id: str, entity_name: str) -> dict | None:
        return self._importance.get((hub_id, entity_name.lower()))

    async def _on_agent_completed(self, event: Event):
        """Handle sub-agent completion — log and optionally retire."""
        agent_id = event.source_agent_id
        agent = self.get_agent(agent_id) if agent_id else None
        if agent:
            logger.info(f"Agent completed: {agent.name} ({agent.agent_type})")
            # Completed sub-agents stay registered (they own the entity)
            # but won't process any more events (status=COMPLETED)

    def get_entity_owner(self, hub_id: str, entity_name: str) -> BaseAgent | None:
        """Check if an entity already has a dedicated sub-agent."""
        agent_id = self._entity_owners.get((hub_id, entity_name.lower()))
        if agent_id and agent_id in self._agents:
            return self._agents[agent_id]
        return None

    async def spawn_subagent(self, parent: BaseAgent, agent_class, **kwargs) -> BaseAgent | None:
        """
        Spawn a sub-agent under a parent agent.
        Returns None if entity already has an owner (no duplicates).
        """
        # Check for duplicate: if target_name is provided, enforce one sub-agent per entity
        target_name = kwargs.get("target_name", "")
        if target_name:
            existing = self.get_entity_owner(parent.hub_id, target_name)
            if existing:
                logger.info(f"Entity '{target_name}' already owned by {existing.name}, skipping spawn")
                return existing

        child = agent_class(
            hub_id=parent.hub_id,
            parent_agent_id=parent.id,
            **kwargs,
        )
        self.register_agent(child)

        # Register entity ownership
        if target_name:
            self._entity_owners[(parent.hub_id, target_name.lower())] = child.id

        await self.event_bus.emit(Event(
            type=EventType.AGENT_SPAWNED,
            hub_id=parent.hub_id,
            source_agent_id=parent.id,
            data={
                "child_agent_id": child.id,
                "child_type": child.agent_type,
                "child_name": child.name,
                "target_name": target_name,
            },
        ))

        return child

    def broadcast_action(self, action: AgentAction):
        """Broadcast an agent action to WebSocket clients and the action log."""
        self._action_log.append(action)
        if len(self._action_log) > self._max_action_log:
            self._action_log = self._action_log[-self._max_action_log:]

        # Broadcast to WebSocket connections for this hub
        ws_list = self._ws_connections.get(action.hub_id, [])
        dead = []
        for ws in ws_list:
            try:
                asyncio.create_task(ws.send_json({"type": "agent_action", "action": action.to_dict()}))
            except Exception:
                dead.append(ws)
        for ws in dead:
            ws_list.remove(ws)

    def add_ws_connection(self, hub_id: str, ws):
        if hub_id not in self._ws_connections:
            self._ws_connections[hub_id] = []
        self._ws_connections[hub_id].append(ws)

    def remove_ws_connection(self, hub_id: str, ws):
        if hub_id in self._ws_connections:
            self._ws_connections[hub_id] = [w for w in self._ws_connections[hub_id] if w is not ws]

    def get_action_log(self, hub_id: str | None = None, limit: int = 50) -> list[dict]:
        actions = self._action_log
        if hub_id:
            actions = [a for a in actions if a.hub_id == hub_id]
        return [a.to_dict() for a in actions[-limit:]]

    async def pause_hub(self, hub_id: str):
        for agent in self.get_hub_agents(hub_id):
            agent.pause()

    async def resume_hub(self, hub_id: str):
        for agent in self.get_hub_agents(hub_id):
            agent.resume()

    async def pause_agent(self, agent_id: str):
        agent = self.get_agent(agent_id)
        if agent:
            agent.pause()

    async def resume_agent(self, agent_id: str):
        agent = self.get_agent(agent_id)
        if agent:
            agent.resume()

    async def send_instruction(self, hub_id: str, text: str, target_agent_id: str | None = None):
        """Send a user instruction to agents."""
        await self.event_bus.emit(Event(
            type=EventType.USER_INSTRUCTION,
            hub_id=hub_id,
            data={"text": text, "target_agent_id": target_agent_id},
        ))
