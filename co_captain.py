"""Co-Captain Git-Agent — the human's liaison to the SuperInstance fleet.

The Co-Captain is NOT another worker agent. It is the human's representative
inside the SuperInstance. It receives instructions, translates them into fleet
protocol messages, dispatches work to git-agents, monitors progress, and
reports back to the human operator.

State Machine:
    STANDBY → BRIEFED → DISPATCHING → MONITORING → REPORTING → STANDBY
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from dispatcher import Dispatcher, FleetMessage, TaskPriority
from fleet_manager import FleetManager
from human_interface import HumanContext, HumanInterface


# ── State Machine ──────────────────────────────────────────────────────────

class CoCaptainState(Enum):
    """States the co-captain can be in."""
    STANDBY = auto()
    BRIEFED = auto()
    DISPATCHING = auto()
    MONITORING = auto()
    REPORTING = auto()


VALID_TRANSITIONS: dict[CoCaptainState, set[CoCaptainState]] = {
    CoCaptainState.STANDBY: {CoCaptainState.BRIEFED},
    CoCaptainState.BRIEFED: {CoCaptainState.DISPATCHING, CoCaptainState.STANDBY},
    CoCaptainState.DISPATCHING: {CoCaptainState.MONITORING, CoCaptainState.REPORTING},
    CoCaptainState.MONITORING: {CoCaptainState.REPORTING, CoCaptainState.DISPATCHING},
    CoCaptainState.REPORTING: {CoCaptainState.STANDBY, CoCaptainState.BRIEFED},
}


# ── Data Classes ──────────────────────────────────────────────────────────

@dataclass
class TaskProgress:
    """Tracks progress of a single task."""
    task_id: str
    agent_id: str | None = None
    status: str = "pending"  # pending, dispatched, in_progress, completed, failed
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: float | None = None


@dataclass
class SessionBrief:
    """A human instruction that the co-captain processes."""
    brief_id: str
    instruction: str
    priority: TaskPriority = TaskPriority.NORMAL
    target_agents: list[str] | None = None  # None means let dispatcher decide
    context: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


# ── Core Agent ────────────────────────────────────────────────────────────

class CoCaptainAgent:
    """The Co-Captain: human liaison to the SuperInstance fleet.

    Acts as the single point of contact between a human operator and the
    entire fleet of git-agents. Nothing reaches the fleet without passing
    through the co-captain.

    Attributes:
        state: Current state in the co-captain state machine.
        human_context: Stores human preferences, priorities, schedule.
        fleet_manager: Manages fleet membership and capabilities.
        dispatcher: Translates and routes tasks to the fleet.
        human_interface: Formats communications for the human.
        active_tasks: Currently tracked tasks.
        brief_history: History of received instructions.
    """

    def __init__(
        self,
        fleet_manager: FleetManager | None = None,
        dispatcher: Dispatcher | None = None,
        human_interface: HumanInterface | None = None,
        human_context: HumanContext | None = None,
    ) -> None:
        self.state = CoCaptainState.STANDBY
        self.fleet_manager = fleet_manager or FleetManager()
        self.dispatcher = dispatcher or Dispatcher(self.fleet_manager)
        self.human_interface = human_interface or HumanInterface(
            human_context or HumanContext()
        )
        self.human_context = self.human_interface.human_context
        self.active_tasks: dict[str, TaskProgress] = {}
        self.brief_history: list[SessionBrief] = []

    # ── State Transitions ─────────────────────────────────────────────

    def _transition_to(self, new_state: CoCaptainState) -> None:
        """Attempt a state machine transition. Raises on invalid transition."""
        allowed = VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise CoCaptainStateError(
                f"Cannot transition from {self.state.name} to {new_state.name}. "
                f"Allowed: {', '.join(s.name for s in allowed)}"
            )
        self.state = new_state

    def is_standby(self) -> bool:
        """Return True if the co-captain is in STANDBY state."""
        return self.state == CoCaptainState.STANDBY

    def reset_to_standby(self) -> None:
        """Force reset to STANDBY (for error recovery)."""
        self.state = CoCaptainState.STANDBY

    # ── Brief (Receive Human Instruction) ─────────────────────────────

    def receive_brief(
        self,
        instruction: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        target_agents: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> SessionBrief:
        """Receive a human instruction and move to BRIEFED state.

        Args:
            instruction: Human-readable instruction text.
            priority: Task priority level.
            target_agents: Specific agents to target, or None for auto-routing.
            context: Additional context for the instruction.

        Returns:
            The created SessionBrief object.

        Raises:
            CoCaptainStateError: If not in STANDBY state.
        """
        if self.state != CoCaptainState.STANDBY:
            raise CoCaptainStateError(
                f"Cannot receive brief in {self.state.name} state. "
                f"Must be in STANDBY."
            )

        brief = SessionBrief(
            brief_id=str(uuid.uuid4())[:8],
            instruction=instruction,
            priority=priority,
            target_agents=target_agents,
            context=context or {},
        )
        self.brief_history.append(brief)
        self._transition_to(CoCaptainState.BRIEFED)
        return brief

    # ── Dispatch ──────────────────────────────────────────────────────

    def dispatch_brief(self, brief: SessionBrief) -> list[str]:
        """Dispatch a brief's tasks to the fleet.

        Translates the human instruction into fleet protocol messages and
        routes them to appropriate agents.

        Args:
            brief: The SessionBrief to dispatch.

        Returns:
            List of task IDs created.

        Raises:
            CoCaptainStateError: If not in BRIEFED state.
            FleetEmptyError: If no agents are available.
        """
        if self.state != CoCaptainState.BRIEFED:
            raise CoCaptainStateError(
                f"Cannot dispatch in {self.state.name} state. "
                f"Must be in BRIEFED."
            )

        if self.fleet_manager.agent_count() == 0:
            raise FleetEmptyError("No agents available in the fleet.")

        self._transition_to(CoCaptainState.DISPATCHING)
        messages = self.dispatcher.translate_and_route(
            instruction=brief.instruction,
            priority=brief.priority,
            target_agents=brief.target_agents,
            context=brief.context,
        )

        task_ids: list[str] = []
        for msg in messages:
            task_id = msg.task_id
            progress = TaskProgress(
                task_id=task_id,
                agent_id=msg.target_agent,
                status="dispatched",
            )
            self.active_tasks[task_id] = progress
            task_ids.append(task_id)

        self._transition_to(CoCaptainState.MONITORING)
        return task_ids

    # ── Monitor ───────────────────────────────────────────────────────

    def update_task_status(
        self,
        task_id: str,
        status: str,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        """Update the status of a tracked task.

        Args:
            task_id: The task identifier.
            status: New status string.
            result: Optional result data.
            error: Optional error message.

        Raises:
            TaskNotFoundError: If task_id is not tracked.
        """
        if task_id not in self.active_tasks:
            raise TaskNotFoundError(f"Task {task_id} not found in active tasks.")

        progress = self.active_tasks[task_id]
        progress.status = status
        progress.updated_at = time.time()

        if result is not None:
            progress.result = result
        if error is not None:
            progress.error = error
        if status in ("completed", "failed"):
            progress.completed_at = time.time()

    def get_progress_summary(self) -> dict[str, int]:
        """Return a summary of task statuses.

        Returns:
            Dict mapping status strings to counts.
        """
        summary: dict[str, int] = {}
        for progress in self.active_tasks.values():
            summary[progress.status] = summary.get(progress.status, 0) + 1
        return summary

    def all_tasks_completed(self) -> bool:
        """Check if all active tasks are in a terminal state."""
        if not self.active_tasks:
            return False
        return all(
            p.status in ("completed", "failed") for p in self.active_tasks.values()
        )

    # ── Report ────────────────────────────────────────────────────────

    def generate_report(self) -> str:
        """Generate a human-readable status report.

        Returns:
            Formatted status report string.
        """
        self._transition_to(CoCaptainState.REPORTING)
        report = self.human_interface.format_status_report(
            tasks=self.active_tasks,
            fleet_snapshot=self.fleet_manager.get_fleet_snapshot(),
            state=self.state.name,
        )
        self._transition_to(CoCaptainState.STANDBY)
        return report

    # ── Fleet Management Delegation ───────────────────────────────────

    def onboard_agent(
        self, agent_id: str, capabilities: list[str], metadata: dict[str, Any] | None = None
    ) -> None:
        """Add a new agent to the fleet.

        Args:
            agent_id: Unique identifier for the agent.
            capabilities: List of capability strings.
            metadata: Optional additional metadata.
        """
        self.fleet_manager.onboard_agent(agent_id, capabilities, metadata)

    def offboard_agent(self, agent_id: str) -> None:
        """Remove an agent from the fleet.

        Args:
            agent_id: Unique identifier for the agent to remove.
        """
        self.fleet_manager.offboard_agent(agent_id)

    def get_fleet_status(self) -> str:
        """Get a human-readable fleet status.

        Returns:
            Formatted fleet status string.
        """
        snapshot = self.fleet_manager.get_fleet_snapshot()
        return self.human_interface.format_fleet_status(snapshot)

    # ── Daily Summary ─────────────────────────────────────────────────

    def generate_daily_summary(self) -> str:
        """Generate an end-of-day summary for the human operator.

        Returns:
            Formatted daily summary string.
        """
        return self.human_interface.format_daily_summary(
            tasks=self.active_tasks,
            brief_history=self.brief_history,
            fleet_snapshot=self.fleet_manager.get_fleet_snapshot(),
        )


# ── Exceptions ────────────────────────────────────────────────────────────

class CoCaptainError(Exception):
    """Base exception for Co-Captain."""


class CoCaptainStateError(CoCaptainError):
    """Raised on invalid state transitions."""


class FleetEmptyError(CoCaptainError):
    """Raised when fleet has no agents."""


class TaskNotFoundError(CoCaptainError):
    """Raised when a task ID is not found."""
