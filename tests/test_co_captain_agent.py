"""Tests for the Co-Captain Agent (co_captain.py) — additional edge cases."""

from __future__ import annotations

import time
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from co_captain import (
    CoCaptainAgent,
    CoCaptainState,
    CoCaptainStateError,
    FleetEmptyError,
    TaskNotFoundError,
    TaskProgress,
    SessionBrief,
    VALID_TRANSITIONS,
)
from dispatcher import TaskPriority
from fleet_manager import FleetManager


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def fleet() -> FleetManager:
    fm = FleetManager()
    fm.onboard_agent("agent-a", ["code_review"])
    fm.onboard_agent("agent-b", ["testing"])
    return fm


@pytest.fixture
def agent(fleet: FleetManager) -> CoCaptainAgent:
    return CoCaptainAgent(fleet_manager=fleet)


# ══════════════════════════════════════════════════════════════════════════
# State Machine — Valid Transitions Table
# ══════════════════════════════════════════════════════════════════════════

class TestValidTransitionsTable:
    """Verify the VALID_TRANSITIONS table is correct."""

    def test_all_states_have_transitions(self) -> None:
        """Every CoCaptainState has at least one valid transition."""
        for state in CoCaptainState:
            assert state in VALID_TRANSITIONS
            assert len(VALID_TRANSITIONS[state]) >= 1

    def test_standby_can_only_go_to_briefed(self) -> None:
        assert VALID_TRANSITIONS[CoCaptainState.STANDBY] == {CoCaptainState.BRIEFED}

    def test_briefed_can_go_to_dispatching_or_standby(self) -> None:
        assert CoCaptainState.DISPATCHING in VALID_TRANSITIONS[CoCaptainState.BRIEFED]
        assert CoCaptainState.STANDBY in VALID_TRANSITIONS[CoCaptainState.BRIEFED]

    def test_reporting_can_go_to_standby_or_briefed(self) -> None:
        assert CoCaptainState.STANDBY in VALID_TRANSITIONS[CoCaptainState.REPORTING]
        assert CoCaptainState.BRIEFED in VALID_TRANSITIONS[CoCaptainState.REPORTING]

    def test_monitoring_can_go_to_reporting_or_dispatching(self) -> None:
        assert CoCaptainState.REPORTING in VALID_TRANSITIONS[CoCaptainState.MONITORING]
        assert CoCaptainState.DISPATCHING in VALID_TRANSITIONS[CoCaptainState.MONITORING]


# ══════════════════════════════════════════════════════════════════════════
# Agent Construction
# ══════════════════════════════════════════════════════════════════════════

class TestAgentConstruction:
    """Tests for agent initialization."""

    def test_default_construction(self) -> None:
        """Agent can be constructed with defaults."""
        a = CoCaptainAgent()
        assert a.state == CoCaptainState.STANDBY
        assert a.fleet_manager.agent_count() == 0
        assert a.active_tasks == {}
        assert a.brief_history == []

    def test_custom_fleet_manager(self, fleet: FleetManager) -> None:
        """Custom fleet manager is used."""
        a = CoCaptainAgent(fleet_manager=fleet)
        assert a.fleet_manager is fleet

    def test_human_context_shared(self, agent: CoCaptainAgent) -> None:
        """Human context is shared between interface and agent."""
        assert agent.human_context is agent.human_interface.human_context

    def test_empty_active_tasks(self, agent: CoCaptainAgent) -> None:
        """New agent has no active tasks."""
        assert len(agent.active_tasks) == 0

    def test_empty_brief_history(self, agent: CoCaptainAgent) -> None:
        """New agent has no brief history."""
        assert len(agent.brief_history) == 0


# ══════════════════════════════════════════════════════════════════════════
# Receive Brief — Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestReceiveBriefEdgeCases:
    """Edge cases for receive_brief."""

    def test_brief_with_low_priority(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("task", priority=TaskPriority.LOW)
        assert brief.priority == TaskPriority.LOW

    def test_brief_with_high_priority(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("task", priority=TaskPriority.HIGH)
        assert brief.priority == TaskPriority.HIGH

    def test_brief_with_empty_target_agents(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("task", target_agents=[])
        assert brief.target_agents == []

    def test_brief_with_multiple_target_agents(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("task", target_agents=["a", "b", "c"])
        assert brief.target_agents == ["a", "b", "c"]

    def test_brief_created_at_timestamp(self, agent: CoCaptainAgent) -> None:
        before = time.time()
        brief = agent.receive_brief("task")
        after = time.time()
        assert before <= brief.created_at <= after

    def test_multiple_briefs_accumulate_in_history(self, agent: CoCaptainAgent) -> None:
        agent.receive_brief("task1")
        agent.reset_to_standby()
        agent.receive_brief("task2")
        agent.reset_to_standby()
        agent.receive_brief("task3")
        assert len(agent.brief_history) == 3


# ══════════════════════════════════════════════════════════════════════════
# Dispatch — Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestDispatchEdgeCases:
    """Edge cases for dispatch."""

    def test_dispatch_creates_task_progress(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("Test")
        task_ids = agent.dispatch_brief(brief)
        for tid in task_ids:
            assert tid in agent.active_tasks
            assert agent.active_tasks[tid].status == "dispatched"

    def test_dispatch_with_targeted_agent(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("Review", target_agents=["agent-a"])
        task_ids = agent.dispatch_brief(brief)
        assert len(task_ids) == 1
        assert agent.active_tasks[task_ids[0]].agent_id == "agent-a"

    def test_dispatch_in_monitoring_raises(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("Test")
        agent.dispatch_brief(brief)
        with pytest.raises(CoCaptainStateError):
            agent.dispatch_brief(brief)

    def test_dispatch_with_all_failed_is_completed(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("Test")
        task_ids = agent.dispatch_brief(brief)
        for tid in task_ids:
            agent.update_task_status(tid, "failed")
        assert agent.all_tasks_completed()

    def test_dispatch_sets_agent_id(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("Test")
        task_ids = agent.dispatch_brief(brief)
        for tid in task_ids:
            assert agent.active_tasks[tid].agent_id is not None


# ══════════════════════════════════════════════════════════════════════════
# Report — Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestReportEdgeCases:
    """Edge cases for report generation."""

    def test_report_from_monitoring(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("Test")
        agent.dispatch_brief(brief)
        report = agent.generate_report()
        assert "Status Report" in report
        assert agent.state == CoCaptainState.STANDBY

    def test_report_includes_fleet_info(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("Test")
        agent.dispatch_brief(brief)
        report = agent.generate_report()
        # The status report includes fleet overview data (total agents, utilization)
        # but not individual agent names in the report format
        assert "Fleet Overview" in report
        assert "Utilization" in report

    def test_report_empty_tasks(self, agent: CoCaptainAgent) -> None:
        """Report can be generated even with no active tasks."""
        # Force to monitoring then report
        agent.state = CoCaptainState.MONITORING
        report = agent.generate_report()
        assert "No active tasks" in report


# ══════════════════════════════════════════════════════════════════════════
# Update Task Status — Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestUpdateTaskEdgeCases:
    """Edge cases for update_task_status."""

    def test_failed_task_has_timestamp(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("Test")
        task_ids = agent.dispatch_brief(brief)
        agent.update_task_status(task_ids[0], "failed")
        assert agent.active_tasks[task_ids[0]].completed_at is not None

    def test_update_preserves_existing_result(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("Test")
        task_ids = agent.dispatch_brief(brief)
        agent.update_task_status(task_ids[0], "completed", result="first")
        agent.update_task_status(task_ids[0], "completed", result="second")
        assert agent.active_tasks[task_ids[0]].result == "second"

    def test_update_updates_timestamp(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("Test")
        task_ids = agent.dispatch_brief(brief)
        tp = agent.active_tasks[task_ids[0]]
        original_updated = tp.updated_at
        time.sleep(0.01)
        agent.update_task_status(task_ids[0], "in_progress")
        assert agent.active_tasks[task_ids[0]].updated_at > original_updated

    def test_progress_summary_empty(self, agent: CoCaptainAgent) -> None:
        assert agent.get_progress_summary() == {}

    def test_progress_summary_single_status(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("Test")
        task_ids = agent.dispatch_brief(brief)
        for tid in task_ids:
            agent.update_task_status(tid, "completed")
        summary = agent.get_progress_summary()
        assert summary == {"completed": len(task_ids)}


# ══════════════════════════════════════════════════════════════════════════
# Reset and Recovery
# ══════════════════════════════════════════════════════════════════════════

class TestResetAndRecovery:
    """Tests for error recovery."""

    def test_reset_from_monitoring(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("Test")
        agent.dispatch_brief(brief)
        assert agent.state == CoCaptainState.MONITORING
        agent.reset_to_standby()
        assert agent.is_standby()

    def test_reset_preserves_tasks(self, agent: CoCaptainAgent) -> None:
        brief = agent.receive_brief("Test")
        agent.dispatch_brief(brief)
        agent.reset_to_standby()
        assert len(agent.active_tasks) > 0

    def test_reset_preserves_history(self, agent: CoCaptainAgent) -> None:
        agent.receive_brief("Test")
        agent.reset_to_standby()
        assert len(agent.brief_history) == 1

    def test_reset_idempotent(self, agent: CoCaptainAgent) -> None:
        agent.reset_to_standby()
        agent.reset_to_standby()
        assert agent.is_standby()


# ══════════════════════════════════════════════════════════════════════════
# Offboard from CoCaptain
# ══════════════════════════════════════════════════════════════════════════

class TestCoCaptainOffboard:
    """Tests for offboard_agent delegation."""

    def test_offboard_nonexistent_raises(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(KeyError):
            agent.offboard_agent("nonexistent")

    def test_onboard_then_offboard(self, agent: CoCaptainAgent) -> None:
        agent.onboard_agent("agent-c", ["review"])
        assert agent.fleet_manager.agent_count() == 3
        agent.offboard_agent("agent-c")
        assert agent.fleet_manager.agent_count() == 2

    def test_onboard_duplicate_raises(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(ValueError):
            agent.onboard_agent("agent-a", ["review"])
