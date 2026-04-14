"""Fleet Manager — manages fleet membership, capabilities, and health.

The FleetManager is responsible for:
- Agent onboarding and offboarding
- Capability registry (what can each agent do?)
- Agent health monitoring
- Fleet snapshot generation
- Auto-scaling suggestions when fleet is overloaded
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


# ── Data Classes ──────────────────────────────────────────────────────────

@dataclass
class AgentRecord:
    """Record for a single fleet agent.

    Attributes:
        agent_id: Unique agent identifier.
        capabilities: List of capability strings.
        status: Current status (active, idle, busy, offline, unhealthy).
        metadata: Additional agent metadata.
        onboarded_at: When the agent was added to the fleet.
        last_heartbeat: Timestamp of the last health check.
        tasks_completed: Number of tasks this agent has completed.
        tasks_failed: Number of tasks this agent has failed.
        current_load: Current number of tasks being processed.
        max_load: Maximum concurrent tasks the agent can handle.
    """
    agent_id: str
    capabilities: list[str] = field(default_factory=list)
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)
    onboarded_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    tasks_completed: int = 0
    tasks_failed: int = 0
    current_load: int = 0
    max_load: int = 5


@dataclass
class FleetSnapshot:
    """A point-in-time snapshot of the fleet.

    Attributes:
        total_agents: Total number of agents.
        active_agents: Number of active agents.
        idle_agents: Number of idle agents.
        busy_agents: Number of busy agents.
        offline_agents: Number of offline agents.
        total_capacity: Sum of all agent max_loads.
        current_load: Sum of all agent current_loads.
        utilization_pct: Current load as percentage of total capacity.
        all_capabilities: Set of all capabilities across the fleet.
        agents: Dict of agent_id → AgentRecord.
    """
    total_agents: int = 0
    active_agents: int = 0
    idle_agents: int = 0
    busy_agents: int = 0
    offline_agents: int = 0
    total_capacity: int = 0
    current_load: int = 0
    utilization_pct: float = 0.0
    all_capabilities: set[str] = field(default_factory=set)
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)


# ── Fleet Manager ─────────────────────────────────────────────────────────

class FleetManager:
    """Manages the fleet of git-agents.

    Provides agent registration, capability lookups, health monitoring,
    and fleet analytics.

    Attributes:
        agents: Registry of agent_id → AgentRecord.
    """

    def __init__(self) -> None:
        self.agents: dict[str, AgentRecord] = {}

    # ── Agent Lifecycle ───────────────────────────────────────────────

    def onboard_agent(
        self,
        agent_id: str,
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRecord:
        """Register a new agent with the fleet.

        Args:
            agent_id: Unique identifier for the agent.
            capabilities: List of capability strings.
            metadata: Optional additional metadata.

        Returns:
            The created AgentRecord.

        Raises:
            ValueError: If agent_id is already registered.
        """
        if agent_id in self.agents:
            raise ValueError(f"Agent {agent_id} is already registered.")

        record = AgentRecord(
            agent_id=agent_id,
            capabilities=capabilities or [],
            metadata=metadata or {},
            onboarded_at=time.time(),
            last_heartbeat=time.time(),
        )
        self.agents[agent_id] = record
        return record

    def offboard_agent(self, agent_id: str) -> None:
        """Remove an agent from the fleet.

        Args:
            agent_id: Unique identifier for the agent.

        Raises:
            KeyError: If agent_id is not found.
        """
        if agent_id not in self.agents:
            raise KeyError(f"Agent {agent_id} not found in fleet.")
        del self.agents[agent_id]

    def agent_count(self) -> int:
        """Return the number of registered agents."""
        return len(self.agents)

    # ── Capability Registry ───────────────────────────────────────────

    def find_agents_by_capabilities(
        self, required: list[str], match_all: bool = False
    ) -> list[str]:
        """Find agents that have the required capabilities.

        Args:
            required: List of required capability strings.
            match_all: If True, agents must have ALL capabilities.
                       If False, agents need at least ONE capability.

        Returns:
            List of matching agent IDs, sorted by current load (ascending).
        """
        matches: list[AgentRecord] = []

        for record in self.agents.values():
            if record.status in ("offline", "unhealthy"):
                continue
            agent_caps = set(record.capabilities)

            if match_all:
                if agent_caps.issuperset(set(required)):
                    matches.append(record)
            else:
                if agent_caps.intersection(required):
                    matches.append(record)

        # Sort by current load (least busy first)
        matches.sort(key=lambda a: a.current_load)
        return [a.agent_id for a in matches]

    def get_agent_capabilities(self, agent_id: str) -> list[str]:
        """Get the capabilities of a specific agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            List of capability strings.

        Raises:
            KeyError: If agent not found.
        """
        if agent_id not in self.agents:
            raise KeyError(f"Agent {agent_id} not found.")
        return self.agents[agent_id].capabilities

    def get_all_capabilities(self) -> set[str]:
        """Get the union of all capabilities across the fleet.

        Returns:
            Set of all capability strings.
        """
        caps: set[str] = set()
        for record in self.agents.values():
            caps.update(record.capabilities)
        return caps

    # ── Health Monitoring ─────────────────────────────────────────────

    def update_heartbeat(self, agent_id: str) -> None:
        """Update the heartbeat timestamp for an agent.

        Args:
            agent_id: Agent identifier.

        Raises:
            KeyError: If agent not found.
        """
        if agent_id not in self.agents:
            raise KeyError(f"Agent {agent_id} not found.")
        self.agents[agent_id].last_heartbeat = time.time()

    def set_agent_status(self, agent_id: str, status: str) -> None:
        """Set the status of an agent.

        Args:
            agent_id: Agent identifier.
            status: New status string (active, idle, busy, offline, unhealthy).

        Raises:
            KeyError: If agent not found.
            ValueError: If status is invalid.
        """
        valid_statuses = {"active", "idle", "busy", "offline", "unhealthy"}
        if status not in valid_statuses:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of: {valid_statuses}"
            )
        if agent_id not in self.agents:
            raise KeyError(f"Agent {agent_id} not found.")
        self.agents[agent_id].status = status

    def check_health(self, timeout_seconds: float = 300.0) -> list[str]:
        """Check agent health based on heartbeat timestamps.

        Marks agents without recent heartbeats as 'unhealthy'.

        Args:
            timeout_seconds: Seconds after which an agent is considered unhealthy.

        Returns:
            List of agent IDs marked as unhealthy.
        """
        now = time.time()
        unhealthy: list[str] = []

        for agent_id, record in self.agents.items():
            if record.status == "offline":
                continue
            if now - record.last_heartbeat > timeout_seconds:
                record.status = "unhealthy"
                unhealthy.append(agent_id)

        return unhealthy

    # ── Task Tracking ─────────────────────────────────────────────────

    def increment_task_count(
        self, agent_id: str, completed: bool = True
    ) -> None:
        """Increment the task counter for an agent.

        Args:
            agent_id: Agent identifier.
            completed: True for completed, False for failed.
        """
        if agent_id in self.agents:
            if completed:
                self.agents[agent_id].tasks_completed += 1
            else:
                self.agents[agent_id].tasks_failed += 1

    def update_agent_load(self, agent_id: str, load_delta: int) -> None:
        """Adjust the current load of an agent.

        Args:
            agent_id: Agent identifier.
            load_delta: Change in load (positive or negative).
        """
        if agent_id in self.agents:
            record = self.agents[agent_id]
            record.current_load = max(0, record.current_load + load_delta)
            # Auto-update status based on load
            if record.current_load >= record.max_load:
                record.status = "busy"
            elif record.current_load == 0 and record.status == "busy":
                record.status = "idle"

    # ── Fleet Analytics ───────────────────────────────────────────────

    def get_fleet_snapshot(self) -> FleetSnapshot:
        """Generate a point-in-time snapshot of the fleet.

        Returns:
            FleetSnapshot with current fleet statistics.
        """
        snapshot = FleetSnapshot()
        snapshot.total_agents = len(self.agents)

        for record in self.agents.values():
            status = record.status
            if status == "active":
                snapshot.active_agents += 1
            elif status == "idle":
                snapshot.idle_agents += 1
            elif status == "busy":
                snapshot.busy_agents += 1
            elif status == "offline":
                snapshot.offline_agents += 1

            snapshot.total_capacity += record.max_load
            snapshot.current_load += record.current_load
            snapshot.all_capabilities.update(record.capabilities)

            snapshot.agents[record.agent_id] = {
                "capabilities": record.capabilities,
                "status": record.status,
                "current_load": record.current_load,
                "max_load": record.max_load,
                "tasks_completed": record.tasks_completed,
                "tasks_failed": record.tasks_failed,
                "metadata": record.metadata,
            }

        if snapshot.total_capacity > 0:
            snapshot.utilization_pct = (
                snapshot.current_load / snapshot.total_capacity * 100
            )

        return snapshot

    def get_scaling_suggestion(self) -> dict[str, Any]:
        """Suggest fleet scaling actions based on current load.

        Returns:
            Dict with scaling suggestions.
        """
        snapshot = self.get_fleet_snapshot()
        suggestion: dict[str, Any] = {
            "current_utilization": snapshot.utilization_pct,
            "action": "none",
            "reason": "Fleet is operating within normal parameters.",
        }

        if snapshot.utilization_pct > 90:
            suggestion = {
                "current_utilization": snapshot.utilization_pct,
                "action": "scale_up",
                "reason": (
                    f"Fleet utilization at {snapshot.utilization_pct:.1f}%. "
                    "Consider adding more agents to handle the workload."
                ),
                "suggested_agents": max(
                    1, int(snapshot.total_capacity * 0.2)
                ),
            }
        elif snapshot.utilization_pct < 20 and snapshot.total_agents > 1:
            suggestion = {
                "current_utilization": snapshot.utilization_pct,
                "action": "scale_down",
                "reason": (
                    f"Fleet utilization at {snapshot.utilization_pct:.1f}%. "
                    "Consider reducing fleet size to save resources."
                ),
                "suggested_removal": max(
                    1, int(snapshot.total_agents * 0.2)
                ),
            }

        return suggestion

    # ── Utility ───────────────────────────────────────────────────────

    def get_all_agent_ids(self) -> list[str]:
        """Get all registered agent IDs.

        Returns:
            List of agent IDs (excluding offline agents).
        """
        return [
            agent_id
            for agent_id, record in self.agents.items()
            if record.status != "offline"
        ]

    def get_agent_record(self, agent_id: str) -> AgentRecord:
        """Get the full record for a specific agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            The AgentRecord.

        Raises:
            KeyError: If agent not found.
        """
        if agent_id not in self.agents:
            raise KeyError(f"Agent {agent_id} not found.")
        return self.agents[agent_id]
