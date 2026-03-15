import asyncio
import logging
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine
from uuid import uuid4

logger = logging.getLogger("engine.events")


class EventType(str, Enum):
    HUB_CREATED = "hub_created"
    HUB_DELETED = "hub_deleted"
    ENTITY_CREATED = "entity_created"
    ENTITY_BATCH = "entity_batch"
    FACT_CREATED = "fact_created"
    ENTITY_FLAGGED = "entity_flagged"
    SOURCE_INGESTED = "source_ingested"
    EPISODE_ADDED = "episode_added"
    AGENT_COMPLETED = "agent_completed"
    AGENT_ERROR = "agent_error"
    AGENT_SPAWNED = "agent_spawned"
    IMPORTANCE_THRESHOLD = "importance_threshold"
    GRAPH_MILESTONE = "graph_milestone"
    USER_INSTRUCTION = "user_instruction"
    EXTERNAL_WEBHOOK = "external_webhook"
    QUALITY_ISSUE = "quality_issue"


@dataclass
class Event:
    type: EventType
    hub_id: str
    data: dict[str, Any] = field(default_factory=dict)
    source_agent_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"Event({self.type.value}, hub={self.hub_id[:8]}..., data_keys={list(self.data.keys())})"

EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """In-process async event bus. Agents subscribe to event types."""

    def __init__(self):
        self._subscribers: dict[EventType, list[EventHandler]] = {}
        self._global_listeners: list[EventHandler] = []
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._task: asyncio.Task | None = None
        self._history: list[Event] = []
        self._max_history = 500

    def subscribe(self, event_type: EventType, handler: EventHandler):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler):
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h is not handler
            ]

    def add_global_listener(self, handler: EventHandler):
        self._global_listeners.append(handler)

    def remove_global_listener(self, handler: EventHandler):
        self._global_listeners = [h for h in self._global_listeners if h is not handler]

    async def emit(self, event: Event):
        await self._queue.put(event)
        logger.info(f"Event emitted: {event}")

    def emit_nowait(self, event: Event):
        self._queue.put_nowait(event)
        logger.info(f"Event emitted (nowait): {event}")

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("EventBus started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("EventBus stopped")

    async def _process_loop(self):
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

            for listener in self._global_listeners:
                try:
                    asyncio.create_task(listener(event))
                except Exception as e:
                    logger.error(f"Global listener error: {e}")

            handlers = self._subscribers.get(event.type, [])
            for handler in handlers:
                try:
                    asyncio.create_task(handler(event))
                except Exception as e:
                    logger.error(f"Handler error for {event.type}: {e}")

    def get_history(self, hub_id: str | None = None, limit: int = 50) -> list[dict]:
        """Get recent events, optionally filtered by hub."""
        events = self._history
        if hub_id:
            events = [e for e in events if e.hub_id == hub_id]
        return [
            {
                "id": e.id,
                "type": e.type.value,
                "hub_id": e.hub_id,
                "data": e.data,
                "source_agent_id": e.source_agent_id,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in events[-limit:]
        ]

    @property
    def pending(self) -> int:
        return self._queue.qsize()
