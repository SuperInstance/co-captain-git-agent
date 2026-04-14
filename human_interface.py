"""Human Interface — manages communication with the human operator.

The HumanInterface is responsible for:
- Message formatting (human-readable status reports)
- Priority escalation rules
- Daily summary generation
- Working hours awareness (don't bother the human at 3am unless critical)
- Context memory (remember human preferences)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


# ── Human Context ─────────────────────────────────────────────────────────

@dataclass
class HumanContext:
    """Stores human operator preferences and context.

    Attributes:
        name: Human operator's name.
        preferred_name: How the human likes to be addressed.
        working_hours_start: Start of working hours (hour, 0-23).
        working_hours_end: End of working hours (hour, 0-23).
        timezone: Human's timezone string.
        communication_style: Preferred communication style (brief, detailed).
        priority_threshold: Minimum priority that warrants immediate notification.
        quiet_hours: Whether quiet hours are enabled.
        preferences: Free-form preference key-value store.
        escalation_contacts: List of escalation contact info.
    """
    name: str = "Operator"
    preferred_name: str | None = None
    working_hours_start: int = 9
    working_hours_end: int = 17
    timezone: str = "UTC"
    communication_style: str = "detailed"  # brief, detailed
    priority_threshold: str = "HIGH"
    quiet_hours: bool = True
    preferences: dict[str, Any] = field(default_factory=dict)
    escalation_contacts: list[str] = field(default_factory=list)

    def is_working_hours(self) -> bool:
        """Check if the current time is within working hours.

        Returns:
            True if within working hours, False otherwise.
        """
        hour = time.localtime().tm_hour
        if self.working_hours_start <= self.working_hours_end:
            return self.working_hours_start <= hour < self.working_hours_end
        # Handle overnight shifts (e.g., 22:00 - 06:00)
        return hour >= self.working_hours_start or hour < self.working_hours_end

    def set_preference(self, key: str, value: Any) -> None:
        """Set a preference value.

        Args:
            key: Preference key.
            value: Preference value.
        """
        self.preferences[key] = value

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a preference value.

        Args:
            key: Preference key.
            default: Default value if key not found.

        Returns:
            The preference value or default.
        """
        return self.preferences.get(key, default)

    def get_greeting(self) -> str:
        """Generate a time-aware greeting for the human.

        Returns:
            A greeting string.
        """
        name = self.preferred_name or self.name
        hour = time.localtime().tm_hour

        if 5 <= hour < 12:
            period = "Good morning"
        elif 12 <= hour < 17:
            period = "Good afternoon"
        elif 17 <= hour < 21:
            period = "Good evening"
        else:
            period = "Hi"

        return f"{period}, {name}."


# ── Priority Escalation ───────────────────────────────────────────────────

PRIORITY_LEVELS = {"LOW": 1, "NORMAL": 2, "HIGH": 3, "CRITICAL": 4}


def should_escalate(priority: str, context: HumanContext) -> bool:
    """Determine if a notification should escalate to the human.

    During quiet hours, only CRITICAL and HIGH (if threshold is HIGH)
    notifications should escalate.

    Args:
        priority: Priority level string.
        context: Human context with settings.

    Returns:
        True if the notification should escalate.
    """
    priority_val = PRIORITY_LEVELS.get(priority.upper(), 2)
    threshold_val = PRIORITY_LEVELS.get(context.priority_threshold.upper(), 3)

    # Always escalate critical
    if priority_val >= 4:
        return True

    # During working hours, escalate if above threshold
    if context.is_working_hours():
        return priority_val >= threshold_val

    # During quiet hours, only critical (handled above)
    if context.quiet_hours:
        return False

    # Quiet hours disabled — escalate as normal
    return priority_val >= threshold_val


# ── Human Interface ───────────────────────────────────────────────────────

class HumanInterface:
    """Formats communications for the human operator.

    Attributes:
        human_context: The human operator's context and preferences.
    """

    def __init__(self, human_context: HumanContext | None = None) -> None:
        self.human_context = human_context or HumanContext()

    # ── Status Reports ────────────────────────────────────────────────

    def format_status_report(
        self,
        tasks: dict[str, Any],
        fleet_snapshot: Any,
        state: str = "STANDBY",
    ) -> str:
        """Format a status report for the human.

        Args:
            tasks: Dict of task_id → TaskProgress.
            fleet_snapshot: FleetSnapshot object.
            state: Current co-captain state name.

        Returns:
            Formatted status report string.
        """
        greeting = self.human_context.get_greeting()
        lines: list[str] = [
            f"{greeting}",
            f"Co-Captain Status Report — {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"State: {state}",
            "",
            "── Fleet Overview ──",
        ]

        if fleet_snapshot:
            lines.extend([
                f"  Total agents: {fleet_snapshot.total_agents}",
                f"  Active: {fleet_snapshot.active_agents}",
                f"  Idle: {fleet_snapshot.idle_agents}",
                f"  Busy: {fleet_snapshot.busy_agents}",
                f"  Utilization: {fleet_snapshot.utilization_pct:.1f}%",
                f"  Capabilities: {', '.join(sorted(fleet_snapshot.all_capabilities)) or 'none'}",
            ])

        lines.append("")
        lines.append("── Tasks ──")

        if not tasks:
            lines.append("  No active tasks.")
        else:
            status_counts: dict[str, int] = {}
            for task_data in tasks.values():
                status = task_data.status if hasattr(task_data, "status") else "unknown"
                status_counts[status] = status_counts.get(status, 0) + 1

            for status, count in sorted(status_counts.items()):
                lines.append(f"  {status}: {count}")

        lines.append("")
        lines.append("── End of Report ──")
        return "\n".join(lines)

    def format_fleet_status(self, snapshot: Any) -> str:
        """Format fleet status for human display.

        Args:
            snapshot: FleetSnapshot object.

        Returns:
            Formatted fleet status string.
        """
        lines: list[str] = [
            "Fleet Status",
            "=" * 40,
            f"Total agents: {snapshot.total_agents}",
            f"Active: {snapshot.active_agents}",
            f"Idle: {snapshot.idle_agents}",
            f"Busy: {snapshot.busy_agents}",
            f"Offline: {snapshot.offline_agents}",
            f"Utilization: {snapshot.utilization_pct:.1f}%",
            "",
        ]

        if snapshot.agents:
            lines.append("Agent Details:")
            for agent_id, info in snapshot.agents.items():
                status_icon = self._status_icon(info.get("status", "unknown"))
                lines.append(
                    f"  {status_icon} {agent_id}: "
                    f"{info.get('status', 'unknown')} "
                    f"(load: {info.get('current_load', 0)}/{info.get('max_load', 0)})"
                )

        return "\n".join(lines)

    def format_daily_summary(
        self,
        tasks: dict[str, Any],
        brief_history: list[Any],
        fleet_snapshot: Any,
    ) -> str:
        """Generate an end-of-day summary.

        Args:
            tasks: Dict of task_id → TaskProgress.
            brief_history: List of SessionBrief objects.
            fleet_snapshot: FleetSnapshot object.

        Returns:
            Formatted daily summary string.
        """
        greeting = self.human_context.get_greeting()
        lines: list[str] = [
            f"{greeting}",
            f"Daily Summary — {time.strftime('%Y-%m-%d')}",
            "=" * 40,
            "",
        ]

        # Task summary
        if tasks:
            completed = sum(
                1 for t in tasks.values()
                if hasattr(t, "status") and t.status == "completed"
            )
            failed = sum(
                1 for t in tasks.values()
                if hasattr(t, "status") and t.status == "failed"
            )
            in_progress = sum(
                1 for t in tasks.values()
                if hasattr(t, "status") and t.status == "in_progress"
            )
            pending = sum(
                1 for t in tasks.values()
                if hasattr(t, "status") and t.status in ("pending", "dispatched")
            )

            lines.extend([
                "── Task Summary ──",
                f"  Total tasks: {len(tasks)}",
                f"  Completed: {completed}",
                f"  Failed: {failed}",
                f"  In Progress: {in_progress}",
                f"  Pending: {pending}",
                "",
            ])

        # Brief history
        if brief_history:
            lines.append("── Instructions Received ──")
            for brief in brief_history[-10:]:  # Last 10
                priority = brief.priority.name if hasattr(brief, "priority") else "NORMAL"
                lines.append(f"  [{priority}] {brief.instruction[:60]}")
            lines.append("")

        # Fleet summary
        if fleet_snapshot:
            active_count = (
                fleet_snapshot.active_agents
                + fleet_snapshot.idle_agents
                + fleet_snapshot.busy_agents
            )
            lines.extend([
                "── Fleet Summary ──",
                f"  Agents: {fleet_snapshot.total_agents} ({active_count} active)",
                f"  Utilization: {fleet_snapshot.utilization_pct:.1f}%",
                "",
            ])

        lines.extend([
            "── Recommendations ──",
            self._generate_recommendations(tasks, fleet_snapshot),
            "",
            "End of daily summary.",
        ])

        return "\n".join(lines)

    def format_escalation(
        self, priority: str, message: str, context_info: str = ""
    ) -> str:
        """Format an escalation notification.

        Args:
            priority: Priority level.
            message: Escalation message.
            context_info: Additional context.

        Returns:
            Formatted escalation string.
        """
        urgency = self._urgency_label(priority)
        lines: list[str] = [
            f"⚠️  ESCALATION [{urgency}]",
            f"Priority: {priority}",
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            message,
        ]
        if context_info:
            lines.extend(["", f"Context: {context_info}"])
        return "\n".join(lines)

    def format_task_update(
        self, task_id: str, status: str, result: Any = None
    ) -> str:
        """Format a task status update for the human.

        Args:
            task_id: Task identifier.
            status: New status.
            result: Optional result data.

        Returns:
            Formatted update string.
        """
        icon = self._status_icon(status)
        lines: list[str] = [
            f"{icon} Task {task_id}: {status}",
        ]
        if result:
            lines.append(f"  Result: {result}")
        return "\n".join(lines)

    # ── Private Helpers ───────────────────────────────────────────────

    @staticmethod
    def _status_icon(status: str) -> str:
        """Return an emoji icon for a status."""
        icons = {
            "completed": "✅",
            "failed": "❌",
            "in_progress": "🔄",
            "pending": "⏳",
            "dispatched": "📤",
            "active": "🟢",
            "idle": "💤",
            "busy": "🔴",
            "offline": "⚫",
            "unhealthy": "🟡",
        }
        return icons.get(status, "❓")

    @staticmethod
    def _urgency_label(priority: str) -> str:
        """Return a human-readable urgency label."""
        labels = {
            "LOW": "🟢 Low",
            "NORMAL": "🔵 Normal",
            "HIGH": "🟠 High",
            "CRITICAL": "🔴 CRITICAL",
        }
        return labels.get(priority.upper(), "Unknown")

    @staticmethod
    def _generate_recommendations(tasks: dict[str, Any], snapshot: Any) -> str:
        """Generate recommendations based on current state."""
        recommendations: list[str] = []

        failed_count = sum(
            1 for t in tasks.values()
            if hasattr(t, "status") and t.status == "failed"
        )
        if failed_count > 0:
            recommendations.append(
                f"  • {failed_count} task(s) failed. Review errors and consider retrying."
            )

        if snapshot and snapshot.utilization_pct > 80:
            recommendations.append(
                "  • Fleet utilization is high. Consider adding agents."
            )

        if snapshot and snapshot.utilization_pct < 20 and snapshot.total_agents > 1:
            recommendations.append(
                "  • Fleet utilization is low. Consider scaling down."
            )

        if not recommendations:
            recommendations.append("  • No immediate actions required.")

        return "\n".join(recommendations)


# ── Helper Function ───────────────────────────────────────────────────────

def snapshot_total_active(snapshot: Any) -> int:
    """Get total active agents from a snapshot (handles different snapshot types)."""
    if hasattr(snapshot, "active_agents"):
        return snapshot.active_agents + snapshot.idle_agents + snapshot.busy_agents
    return 0
