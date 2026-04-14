"""Task Dispatch Engine — translates human intent into fleet protocol messages.

The dispatcher is responsible for:
- Translating human instructions into FleetMessage protocol messages
- Routing tasks to appropriate agents based on capability matching
- Supporting broadcast (all agents) and targeted dispatch
- Maintaining a priority queue with deadline support
- Tracking task acknowledgments
"""

from __future__ import annotations

import heapq
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from fleet_manager import FleetManager


# ── Priority Levels ───────────────────────────────────────────────────────

class TaskPriority(IntEnum):
    """Task priority levels. Higher value = higher priority."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


# ── Fleet Protocol Message ────────────────────────────────────────────────

@dataclass(order=False)
class FleetMessage:
    """A message in the fleet protocol.

    Attributes:
        task_id: Unique task identifier.
        message_type: Type of message (task, query, broadcast, cancel).
        payload: The actual instruction/data.
        target_agent: Specific agent to target (None for broadcast).
        priority: Task priority level.
        deadline: Optional deadline timestamp.
        source: Source identifier (always 'co-captain').
        created_at: Message creation timestamp.
        context: Additional context metadata.
    """
    task_id: str
    message_type: str  # task, query, broadcast, cancel
    payload: str
    target_agent: str | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    deadline: float | None = None
    source: str = "co-captain"
    created_at: float = field(default_factory=time.time)
    context: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False

    def __lt__(self, other: FleetMessage) -> bool:
        """Heap ordering: higher priority first, then earlier deadline."""
        if self.priority != other.priority:
            return self.priority > other.priority  # Higher priority = sooner
        # If priorities are equal, earlier deadline first
        self_deadline = self.deadline if self.deadline else float("inf")
        other_deadline = other.deadline if other.deadline else float("inf")
        return self_deadline < other_deadline


# ── Intent Parsing ────────────────────────────────────────────────────────

# Keyword → capability mapping for human instruction parsing
INTENT_CAPABILITY_MAP: dict[str, list[str]] = {
    "refactor": ["code_analysis", "code_modification"],
    "test": ["testing"],
    "tests": ["testing"],
    "fix": ["bug_fixing", "code_modification"],
    "bug": ["bug_fixing"],
    "review": ["code_review"],
    "deploy": ["deployment"],
    "build": ["build_system"],
    "document": ["documentation"],
    "docs": ["documentation"],
    "merge": ["git_operations"],
    "branch": ["git_operations"],
    "pr": ["git_operations", "code_review"],
    "release": ["deployment", "git_operations"],
    "update": ["dependency_management", "code_modification"],
    "upgrade": ["dependency_management", "code_modification"],
    "security": ["security"],
    "lint": ["code_quality"],
    "format": ["code_quality"],
    "clean": ["code_quality", "maintenance"],
    "migrate": ["migration", "code_modification"],
    "optimize": ["performance", "code_analysis"],
    "benchmark": ["performance", "testing"],
    "monitor": ["monitoring"],
    "log": ["monitoring", "debugging"],
    "debug": ["debugging", "code_analysis"],
    "investigate": ["code_analysis", "debugging"],
    "analyze": ["code_analysis"],
}


def parse_intent_capabilities(instruction: str) -> list[str]:
    """Extract required capabilities from a human instruction.

    Scans the instruction for known keywords and returns the union
    of all matched capabilities.

    Args:
        instruction: Human-readable instruction text.

    Returns:
        List of required capability strings.
    """
    instruction_lower = instruction.lower()
    words = set(re.findall(r"\b\w+\b", instruction_lower))
    capabilities: list[str] = []
    seen: set[str] = set()

    for keyword, caps in INTENT_CAPABILITY_MAP.items():
        if keyword in words:
            for cap in caps:
                if cap not in seen:
                    seen.add(cap)
                    capabilities.append(cap)

    return capabilities


# ── Dispatcher ────────────────────────────────────────────────────────────

class Dispatcher:
    """Translates human intent and dispatches tasks to the fleet.

    The dispatcher is the bridge between human language and fleet protocol.
    It determines which agents can handle a task, creates protocol messages,
    and manages the priority queue.

    Attributes:
        fleet_manager: Reference to the fleet manager for agent lookups.
        queue: Priority queue of pending messages.
        sent_messages: History of all dispatched messages.
        acknowledgments: Map of task_id → acknowledgment status.
    """

    def __init__(self, fleet_manager: FleetManager) -> None:
        self.fleet_manager = fleet_manager
        self.queue: list[FleetMessage] = []
        self.sent_messages: list[FleetMessage] = []
        self.acknowledgments: dict[str, bool] = {}

    # ── Translation ───────────────────────────────────────────────────

    def translate_and_route(
        self,
        instruction: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        target_agents: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[FleetMessage]:
        """Translate a human instruction into fleet protocol messages.

        Args:
            instruction: Human-readable instruction.
            priority: Task priority level.
            target_agents: Specific agents to target, or None for auto-routing.
            context: Additional context metadata.

        Returns:
            List of FleetMessage objects ready for delivery.
        """
        required_capabilities = parse_intent_capabilities(instruction)
        context = context or {}

        # Determine target agents
        if target_agents:
            agents = target_agents
        elif required_capabilities:
            agents = self.fleet_manager.find_agents_by_capabilities(
                required_capabilities
            )
            if not agents:
                # Fall back to broadcast if no specific agents found
                agents = self.fleet_manager.get_all_agent_ids()
        else:
            # No specific capabilities required — broadcast
            agents = self.fleet_manager.get_all_agent_ids()

        # Create messages
        messages: list[FleetMessage] = []
        broadcast = not target_agents and not required_capabilities

        for agent_id in agents:
            msg = FleetMessage(
                task_id=str(uuid.uuid4())[:8],
                message_type="broadcast" if broadcast else "task",
                payload=instruction,
                target_agent=agent_id,
                priority=priority,
                context={
                    **context,
                    "required_capabilities": required_capabilities,
                },
            )
            messages.append(msg)
            heapq.heappush(self.queue, msg)

        self.sent_messages.extend(messages)
        return messages

    # ── Priority Queue ────────────────────────────────────────────────

    def enqueue(self, message: FleetMessage) -> None:
        """Add a message to the priority queue.

        Args:
            message: The FleetMessage to enqueue.
        """
        heapq.heappush(self.queue, message)

    def dequeue_next(self) -> FleetMessage | None:
        """Pop the highest-priority message from the queue.

        Returns:
            The next FleetMessage, or None if the queue is empty.
        """
        if not self.queue:
            return None
        return heapq.heappop(self.queue)

    def queue_size(self) -> int:
        """Return the number of messages in the queue."""
        return len(self.queue)

    def get_queue_snapshot(self) -> list[dict[str, Any]]:
        """Get a snapshot of queued messages (without dequeuing).

        Returns:
            List of dicts with message details sorted by priority.
        """
        return [
            {
                "task_id": msg.task_id,
                "payload": msg.payload[:50],
                "target_agent": msg.target_agent,
                "priority": msg.priority.name,
                "type": msg.message_type,
            }
            for msg in sorted(self.queue)
        ]

    # ── Acknowledgment Tracking ───────────────────────────────────────

    def acknowledge(self, task_id: str) -> None:
        """Mark a task as acknowledged by an agent.

        Args:
            task_id: The task identifier to acknowledge.

        Raises:
            KeyError: If task_id is not found in sent messages.
        """
        self.acknowledgments[task_id] = True
        for msg in self.sent_messages:
            if msg.task_id == task_id:
                msg.acknowledged = True
                return
        raise KeyError(f"Task {task_id} not found in sent messages.")

    def is_acknowledged(self, task_id: str) -> bool:
        """Check if a task has been acknowledged.

        Args:
            task_id: The task identifier.

        Returns:
            True if acknowledged, False otherwise.
        """
        return self.acknowledgments.get(task_id, False)

    def unacknowledged_count(self) -> int:
        """Count sent messages that have not been acknowledged.

        Returns:
            Number of unacknowledged messages.
        """
        total = len(self.sent_messages)
        return total - len(self.acknowledgments)

    # ── Broadcast ─────────────────────────────────────────────────────

    def create_broadcast(
        self,
        payload: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        context: dict[str, Any] | None = None,
    ) -> list[FleetMessage]:
        """Create broadcast messages for all fleet agents.

        Args:
            payload: The message content.
            priority: Task priority level.
            context: Additional context metadata.

        Returns:
            List of FleetMessage objects for each agent.
        """
        agents = self.fleet_manager.get_all_agent_ids()
        messages: list[FleetMessage] = []

        for agent_id in agents:
            msg = FleetMessage(
                task_id=str(uuid.uuid4())[:8],
                message_type="broadcast",
                payload=payload,
                target_agent=agent_id,
                priority=priority,
                context=context or {},
            )
            messages.append(msg)
            heapq.heappush(self.queue, msg)

        self.sent_messages.extend(messages)
        return messages

    # ── Utility ───────────────────────────────────────────────────────

    def cancel_task(self, task_id: str) -> FleetMessage | None:
        """Create a cancel message for a dispatched task.

        Args:
            task_id: The task identifier to cancel.

        Returns:
            Cancel FleetMessage, or None if task not found.
        """
        target = None
        for msg in self.sent_messages:
            if msg.task_id == task_id:
                target = msg
                break

        if target is None:
            return None

        cancel_msg = FleetMessage(
            task_id=str(uuid.uuid4())[:8],
            message_type="cancel",
            payload=f"Cancel task {task_id}",
            target_agent=target.target_agent,
            priority=TaskPriority.HIGH,
            context={"cancelled_task_id": task_id},
        )
        self.sent_messages.append(cancel_msg)
        return cancel_msg
