"""Tests for the Human Interface module (human_interface.py) — additional edge cases."""

from __future__ import annotations

import time
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from human_interface import (
    HumanContext,
    HumanInterface,
    should_escalate,
    snapshot_total_active,
    PRIORITY_LEVELS,
)


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def context() -> HumanContext:
    return HumanContext(
        name="Test Operator",
        preferred_name="Test",
        working_hours_start=9,
        working_hours_end=17,
    )


@pytest.fixture
def interface(context: HumanContext) -> HumanInterface:
    return HumanInterface(context)


# ══════════════════════════════════════════════════════════════════════════
# HumanContext — Default Values
# ══════════════════════════════════════════════════════════════════════════

class TestHumanContextDefaults:
    """Tests for default HumanContext values."""

    def test_default_name(self) -> None:
        ctx = HumanContext()
        assert ctx.name == "Operator"

    def test_default_preferred_name(self) -> None:
        ctx = HumanContext()
        assert ctx.preferred_name is None

    def test_default_working_hours(self) -> None:
        ctx = HumanContext()
        assert ctx.working_hours_start == 9
        assert ctx.working_hours_end == 17

    def test_default_timezone(self) -> None:
        ctx = HumanContext()
        assert ctx.timezone == "UTC"

    def test_default_communication_style(self) -> None:
        ctx = HumanContext()
        assert ctx.communication_style == "detailed"

    def test_default_priority_threshold(self) -> None:
        ctx = HumanContext()
        assert ctx.priority_threshold == "HIGH"

    def test_default_quiet_hours(self) -> None:
        ctx = HumanContext()
        assert ctx.quiet_hours is True

    def test_default_preferences(self) -> None:
        ctx = HumanContext()
        assert ctx.preferences == {}

    def test_default_escalation_contacts(self) -> None:
        ctx = HumanContext()
        assert ctx.escalation_contacts == []


# ══════════════════════════════════════════════════════════════════════════
# HumanContext — Working Hours
# ══════════════════════════════════════════════════════════════════════════

class TestWorkingHours:
    """Tests for working hours awareness."""

    @patch("human_interface.time")
    def test_during_working_hours(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 14
        ctx = HumanContext(working_hours_start=9, working_hours_end=17)
        assert ctx.is_working_hours() is True

    @patch("human_interface.time")
    def test_before_working_hours(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 7
        ctx = HumanContext(working_hours_start=9, working_hours_end=17)
        assert ctx.is_working_hours() is False

    @patch("human_interface.time")
    def test_after_working_hours(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 20
        ctx = HumanContext(working_hours_start=9, working_hours_end=17)
        assert ctx.is_working_hours() is False

    @patch("human_interface.time")
    def test_at_start_hour(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 9
        ctx = HumanContext(working_hours_start=9, working_hours_end=17)
        assert ctx.is_working_hours() is True

    @patch("human_interface.time")
    def test_at_end_hour(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 17
        ctx = HumanContext(working_hours_start=9, working_hours_end=17)
        assert ctx.is_working_hours() is False

    @patch("human_interface.time")
    def test_overnight_shift(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 23
        ctx = HumanContext(working_hours_start=22, working_hours_end=6)
        assert ctx.is_working_hours() is True

    @patch("human_interface.time")
    def test_overnight_shift_early_morning(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 3
        ctx = HumanContext(working_hours_start=22, working_hours_end=6)
        assert ctx.is_working_hours() is True

    @patch("human_interface.time")
    def test_overnight_shift_during_day(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 14
        ctx = HumanContext(working_hours_start=22, working_hours_end=6)
        assert ctx.is_working_hours() is False


# ══════════════════════════════════════════════════════════════════════════
# HumanContext — Preferences
# ══════════════════════════════════════════════════════════════════════════

class TestPreferences:
    """Tests for preference management."""

    def test_set_and_get(self, context: HumanContext) -> None:
        context.set_preference("editor", "vim")
        assert context.get_preference("editor") == "vim"

    def test_get_default(self, context: HumanContext) -> None:
        assert context.get_preference("nonexistent") is None

    def test_get_custom_default(self, context: HumanContext) -> None:
        assert context.get_preference("nonexistent", "fallback") == "fallback"

    def test_set_overwrites(self, context: HumanContext) -> None:
        context.set_preference("key", "value1")
        context.set_preference("key", "value2")
        assert context.get_preference("key") == "value2"

    def test_set_various_types(self, context: HumanContext) -> None:
        context.set_preference("int", 42)
        context.set_preference("list", [1, 2, 3])
        context.set_preference("dict", {"a": 1})
        assert context.get_preference("int") == 42
        assert context.get_preference("list") == [1, 2, 3]
        assert context.get_preference("dict") == {"a": 1}


# ══════════════════════════════════════════════════════════════════════════
# HumanContext — Greeting
# ══════════════════════════════════════════════════════════════════════════

class TestGreeting:
    """Tests for greeting generation."""

    @patch("human_interface.time")
    def test_uses_preferred_name(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 10
        ctx = HumanContext(name="Full Name", preferred_name="Nick")
        assert "Nick" in ctx.get_greeting()

    @patch("human_interface.time")
    def test_falls_back_to_name(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 10
        ctx = HumanContext(name="Full Name", preferred_name=None)
        assert "Full Name" in ctx.get_greeting()

    @patch("human_interface.time")
    def test_morning_greeting(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 8
        ctx = HumanContext(name="Test")
        greeting = ctx.get_greeting()
        assert "Good morning" in greeting

    @patch("human_interface.time")
    def test_afternoon_greeting(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 14
        ctx = HumanContext(name="Test")
        greeting = ctx.get_greeting()
        assert "Good afternoon" in greeting

    @patch("human_interface.time")
    def test_evening_greeting(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 19
        ctx = HumanContext(name="Test")
        greeting = ctx.get_greeting()
        assert "Good evening" in greeting

    @patch("human_interface.time")
    def test_night_greeting(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 23
        ctx = HumanContext(name="Test")
        greeting = ctx.get_greeting()
        assert "Hi" in greeting

    @patch("human_interface.time")
    def test_early_morning_greeting(self, mock_time: MagicMock) -> None:
        mock_time.localtime.return_value.tm_hour = 4
        ctx = HumanContext(name="Test")
        greeting = ctx.get_greeting()
        assert "Hi" in greeting


# ══════════════════════════════════════════════════════════════════════════
# should_escalate — Escalation Logic
# ══════════════════════════════════════════════════════════════════════════

class TestShouldEscalate:
    """Tests for escalation logic."""

    def test_critical_always_escalates(self) -> None:
        ctx = HumanContext(quiet_hours=True)
        with patch.object(ctx, "is_working_hours", return_value=False):
            assert should_escalate("CRITICAL", ctx) is True

    def test_low_during_quiet_hours(self) -> None:
        ctx = HumanContext(quiet_hours=True)
        with patch.object(ctx, "is_working_hours", return_value=False):
            assert should_escalate("LOW", ctx) is False

    def test_normal_during_quiet_hours(self) -> None:
        ctx = HumanContext(quiet_hours=True)
        with patch.object(ctx, "is_working_hours", return_value=False):
            assert should_escalate("NORMAL", ctx) is False

    def test_high_during_quiet_hours(self) -> None:
        ctx = HumanContext(priority_threshold="HIGH", quiet_hours=True)
        with patch.object(ctx, "is_working_hours", return_value=False):
            assert should_escalate("HIGH", ctx) is False

    def test_high_during_working_hours(self) -> None:
        ctx = HumanContext(priority_threshold="HIGH", quiet_hours=True)
        with patch.object(ctx, "is_working_hours", return_value=True):
            assert should_escalate("HIGH", ctx) is True

    def test_low_during_working_hours_with_high_threshold(self) -> None:
        ctx = HumanContext(priority_threshold="HIGH", quiet_hours=True)
        with patch.object(ctx, "is_working_hours", return_value=True):
            assert should_escalate("LOW", ctx) is False

    def test_normal_during_working_hours_with_normal_threshold(self) -> None:
        ctx = HumanContext(priority_threshold="NORMAL", quiet_hours=True)
        with patch.object(ctx, "is_working_hours", return_value=True):
            assert should_escalate("NORMAL", ctx) is True

    def test_quiet_hours_disabled_escalates(self) -> None:
        ctx = HumanContext(priority_threshold="NORMAL", quiet_hours=False)
        with patch.object(ctx, "is_working_hours", return_value=False):
            assert should_escalate("HIGH", ctx) is True

    def test_priority_levels_complete(self) -> None:
        assert set(PRIORITY_LEVELS.keys()) == {"LOW", "NORMAL", "HIGH", "CRITICAL"}

    def test_case_insensitive_priority(self) -> None:
        ctx = HumanContext(priority_threshold="HIGH", quiet_hours=True)
        with patch.object(ctx, "is_working_hours", return_value=False):
            assert should_escalate("critical", ctx) is True
            assert should_escalate("Critical", ctx) is True


# ══════════════════════════════════════════════════════════════════════════
# HumanInterface — Formatting
# ══════════════════════════════════════════════════════════════════════════

class TestFormatting:
    """Tests for report formatting."""

    def test_format_status_report_with_tasks(self, interface: HumanInterface) -> None:
        from co_captain import TaskProgress
        tasks = {
            "t1": TaskProgress(task_id="t1", status="completed"),
            "t2": TaskProgress(task_id="t2", status="in_progress"),
        }
        from fleet_manager import FleetSnapshot
        snap = FleetSnapshot(total_agents=2, active_agents=1, idle_agents=1, busy_agents=0, offline_agents=0, all_capabilities={"testing"})
        report = interface.format_status_report(tasks, snap, "MONITORING")
        assert "completed" in report
        assert "in_progress" in report
        assert "MONITORING" in report

    def test_format_status_report_no_tasks(self, interface: HumanInterface) -> None:
        from fleet_manager import FleetSnapshot
        snap = FleetSnapshot()
        report = interface.format_status_report({}, snap, "STANDBY")
        assert "No active tasks" in report

    def test_format_daily_summary(self, interface: HumanInterface) -> None:
        from co_captain import TaskProgress, SessionBrief
        from dispatcher import TaskPriority
        tasks = {"t1": TaskProgress(task_id="t1", status="completed")}
        briefs = [SessionBrief(brief_id="b1", instruction="Test task", priority=TaskPriority.NORMAL)]
        from fleet_manager import FleetSnapshot
        snap = FleetSnapshot(total_agents=1, active_agents=1)
        summary = interface.format_daily_summary(tasks, briefs, snap)
        assert "Daily Summary" in summary
        assert "Test task" in summary

    def test_format_escalation(self, interface: HumanInterface) -> None:
        escalation = interface.format_escalation("CRITICAL", "Server is down!", "prod")
        assert "CRITICAL" in escalation
        assert "Server is down!" in escalation
        assert "prod" in escalation

    def test_format_escalation_no_context(self, interface: HumanInterface) -> None:
        escalation = interface.format_escalation("HIGH", "Warning")
        assert "Warning" in escalation
        assert "Context:" not in escalation

    def test_format_task_update(self, interface: HumanInterface) -> None:
        update = interface.format_task_update("t1", "completed", "All tests passed")
        assert "t1" in update
        assert "completed" in update
        assert "All tests passed" in update

    def test_format_task_update_no_result(self, interface: HumanInterface) -> None:
        update = interface.format_task_update("t1", "in_progress")
        assert "Result:" not in update


# ══════════════════════════════════════════════════════════════════════════
# snapshot_total_active — Helper
# ══════════════════════════════════════════════════════════════════════════

class TestSnapshotTotalActive:
    """Tests for snapshot_total_active helper."""

    def test_with_snapshot(self) -> None:
        from fleet_manager import FleetSnapshot
        snap = FleetSnapshot(active_agents=2, idle_agents=1, busy_agents=1)
        assert snapshot_total_active(snap) == 4

    def test_with_none(self) -> None:
        assert snapshot_total_active(None) == 0

    def test_with_object_without_attribute(self) -> None:
        assert snapshot_total_active("not a snapshot") == 0


# ══════════════════════════════════════════════════════════════════════════
# Status Icons
# ══════════════════════════════════════════════════════════════════════════

class TestStatusIcons:
    """Tests for status icons."""

    def test_all_known_statuses_have_icons(self) -> None:
        known = ["completed", "failed", "in_progress", "pending", "dispatched",
                 "active", "idle", "busy", "offline", "unhealthy"]
        for status in known:
            icon = HumanInterface._status_icon(status)
            assert icon != "❓", f"Missing icon for {status}"

    def test_unknown_status_returns_question(self) -> None:
        assert HumanInterface._status_icon("unknown_status") == "❓"


# ══════════════════════════════════════════════════════════════════════════
# Urgency Labels
# ══════════════════════════════════════════════════════════════════════════

class TestUrgencyLabels:
    """Tests for urgency labels."""

    def test_all_priorities_have_labels(self) -> None:
        for p in ["LOW", "NORMAL", "HIGH", "CRITICAL"]:
            label = HumanInterface._urgency_label(p)
            assert "Unknown" not in label, f"Missing label for {p}"

    def test_unknown_priority_returns_unknown(self) -> None:
        assert "Unknown" in HumanInterface._urgency_label("INVALID")
