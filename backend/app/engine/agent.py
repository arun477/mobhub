import asyncio
import logging
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .events import Event, EventType

logger = logging.getLogger("engine.agent")


class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class AgentPersonality:
    """Behavioral profile — shapes how the agent approaches work."""
    approach: str = ""
    expertise: list[str] = field(default_factory=list)
    style: str = ""
    risk_tolerance: float = 0.5

    def to_system_prompt(self) -> str:
        """Convert personality to LLM system prompt fragment."""
        parts = []
        if self.approach:
            parts.append(f"Your approach: {self.approach}.")
        if self.expertise:
            parts.append(f"Your expertise: {', '.join(self.expertise)}.")
        if self.style:
            parts.append(f"Your communication style: {self.style}.")
        return " ".join(parts)


@dataclass
class AgentAction:
    """A single action taken by an agent — the unit of the live log."""
    id: str = field(default_factory=lambda: str(uuid4()))
    agent_id: str = ""
    hub_id: str = ""
    action_type: str = ""
    description: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    status: str = "started"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "hub_id": self.hub_id,
            "action_type": self.action_type,
            "description": self.description,
            "detail": self.detail,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
        }


class BaseAgent:
    """
    Base class for all v3 agents. Subclass and override:
    - get_triggers() — which events wake this agent
    - handle_event() — react to an event
    - decide() — given context, decide what to do next
    - execute() — carry out the decision
    """

    def __init__(
        self,
        hub_id: str,
        agent_type: str = "base",
        name: str = "",
        personality: AgentPersonality | None = None,
        parent_agent_id: str | None = None,
    ):
        self.id = str(uuid4())
        self.hub_id = hub_id
        self.agent_type = agent_type
        self.name = name or f"{agent_type}-{self.id[:8]}"
        self.personality = personality or AgentPersonality()
        self.parent_agent_id = parent_agent_id
        self.status = AgentStatus.IDLE
        self.created_at = datetime.now(timezone.utc)

        self.memory: dict[str, Any] = {}
        self.actions: list[AgentAction] = []
        self._max_actions = 200

        self.events_handled = 0
        self.errors = 0
        self._consecutive_errors = 0
        self.last_active: datetime | None = None
        self._lock = asyncio.Lock()
        self.tools: dict[str, Any] = {}
        self._runtime = None

    def get_triggers(self) -> list[EventType]:
        return []

    async def handle_event(self, event: Event):
        pass

    async def decide(self, context: dict) -> dict:
        return {"action": "noop"}

    async def execute(self, decision: dict) -> dict:
        return {"status": "noop"}

    def should_spawn_subagent(self, entity: dict) -> dict | None:
        """Check if this entity warrants a dedicated sub-agent. Returns spec or None."""
        return None

    async def _on_event(self, event: Event):
        if self.status in (AgentStatus.PAUSED, AgentStatus.COMPLETED):
            return

        if self._consecutive_errors >= 3:
            self.status = AgentStatus.PAUSED
            self.log_action("safety", f"Auto-paused after {self._consecutive_errors} consecutive errors")
            return

        async with self._lock:
            self.status = AgentStatus.WORKING
            self.last_active = datetime.now(timezone.utc)
            self.events_handled += 1

            try:
                await self.handle_event(event)
                self.status = AgentStatus.IDLE
                self._consecutive_errors = 0
            except Exception as e:
                self.errors += 1
                self._consecutive_errors += 1
                self.status = AgentStatus.ERROR
                logger.error(f"Agent {self.name} error handling {event.type}: {e}", exc_info=True)

                if self._runtime:
                    from .events import Event as Ev
                    await self._runtime.event_bus.emit(Ev(
                        type=EventType.AGENT_ERROR,
                        hub_id=self.hub_id,
                        source_agent_id=self.id,
                        data={"error": str(e), "event_type": event.type.value},
                    ))

    def log_action(self, action_type: str, description: str, detail: dict = None, status: str = "completed") -> AgentAction:
        """Log an action for the live feed."""
        action = AgentAction(
            agent_id=self.id,
            hub_id=self.hub_id,
            action_type=action_type,
            description=description,
            detail=detail or {},
            status=status,
        )
        self.actions.append(action)
        if len(self.actions) > self._max_actions:
            self.actions = self.actions[-self._max_actions:]

        if self._runtime:
            self._runtime.broadcast_action(action)

        return action

    async def emit(self, event_type: EventType, data: dict = None):
        """Convenience: emit an event from this agent."""
        if self._runtime:
            await self._runtime.event_bus.emit(Event(
                type=event_type,
                hub_id=self.hub_id,
                source_agent_id=self.id,
                data=data or {},
            ))

    def pause(self):
        self.status = AgentStatus.PAUSED

    def resume(self):
        if self.status == AgentStatus.PAUSED:
            self.status = AgentStatus.IDLE

    def to_dict(self) -> dict:
        """Serialize for API/UI."""
        return {
            "id": self.id,
            "hub_id": self.hub_id,
            "agent_type": self.agent_type,
            "name": self.name,
            "status": self.status.value,
            "personality": {
                "approach": self.personality.approach,
                "expertise": self.personality.expertise,
                "style": self.personality.style,
            },
            "parent_agent_id": self.parent_agent_id,
            "events_handled": self.events_handled,
            "errors": self.errors,
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "created_at": self.created_at.isoformat(),
            "memory_keys": list(self.memory.keys()),
            "recent_actions": [a.to_dict() for a in self.actions[-10:]],
        }
