"""Tests for the Fleet Manager module (fleet_manager.py) — additional edge cases."""

from __future__ import annotations

import time
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fleet_manager import AgentRecord, FleetManager, FleetSnapshot


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def fleet() -> FleetManager:
    fm = FleetManager()
    fm.onboard_agent("alpha", ["code_review", "git_operations"])
    fm.onboard_agent("beta", ["testing"])
    fm.onboard_agent("gamma", ["deployment", "code_review"])
    return fm


# ══════════════════════════════════════════════════════════════════════════
# AgentRecord — Data Class Tests
# ══════════════════════════════════════════════════════════════════════════

class TestAgentRecord:
    """Tests for AgentRecord data class."""

    def test_default_values(self) -> None:
        record = AgentRecord(agent_id="test")
        assert record.agent_id == "test"
        assert record.capabilities == []
        assert record.status == "active"
        assert record.metadata == {}
        assert record.tasks_completed == 0
        assert record.tasks_failed == 0
        assert record.current_load == 0
        assert record.max_load == 5

    def test_custom_values(self) -> None:
        record = AgentRecord(
            agent_id="test",
            capabilities=["testing"],
            status="busy",
            max_load=10,
        )
        assert record.max_load == 10
        assert record.capabilities == ["testing"]

    def test_onboarded_at_timestamp(self) -> None:
        before = time.time()
        record = AgentRecord(agent_id="test")
        after = time.time()
        assert before <= record.onboarded_at <= after

    def test_last_heartbeat_timestamp(self) -> None:
        before = time.time()
        record = AgentRecord(agent_id="test")
        after = time.time()
        assert before <= record.last_heartbeat <= after


# ══════════════════════════════════════════════════════════════════════════
# FleetSnapshot — Data Class Tests
# ══════════════════════════════════════════════════════════════════════════

class TestFleetSnapshot:
    """Tests for FleetSnapshot data class."""

    def test_default_values(self) -> None:
        snap = FleetSnapshot()
        assert snap.total_agents == 0
        assert snap.active_agents == 0
        assert snap.utilization_pct == 0.0
        assert snap.all_capabilities == set()
        assert snap.agents == {}

    def test_empty_fleet_snapshot(self) -> None:
        fm = FleetManager()
        snap = fm.get_fleet_snapshot()
        assert snap.total_agents == 0
        assert snap.total_capacity == 0
        assert snap.current_load == 0
        assert snap.utilization_pct == 0.0


# ══════════════════════════════════════════════════════════════════════════
# FleetManager — Onboarding Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestOnboardingEdgeCases:
    """Edge cases for onboarding."""

    def test_onboard_with_empty_capabilities(self) -> None:
        fm = FleetManager()
        record = fm.onboard_agent("test", [])
        assert record.capabilities == []

    def test_onboard_with_none_capabilities(self) -> None:
        fm = FleetManager()
        record = fm.onboard_agent("test", None)
        assert record.capabilities == []

    def test_onboard_with_none_metadata(self) -> None:
        fm = FleetManager()
        record = fm.onboard_agent("test", ["testing"], None)
        assert record.metadata == {}

    def test_onboard_with_empty_metadata(self) -> None:
        fm = FleetManager()
        record = fm.onboard_agent("test", ["testing"], {})
        assert record.metadata == {}

    def test_onboard_same_id_after_offboard(self, fleet: FleetManager) -> None:
        fleet.offboard_agent("alpha")
        record = fleet.onboard_agent("alpha", ["new_cap"])
        assert record.capabilities == ["new_cap"]


# ══════════════════════════════════════════════════════════════════════════
# FleetManager — Task Tracking
# ══════════════════════════════════════════════════════════════════════════

class TestTaskTracking:
    """Tests for task counting and load management."""

    def test_increment_task_completed(self, fleet: FleetManager) -> None:
        fleet.increment_task_count("alpha", completed=True)
        assert fleet.agents["alpha"].tasks_completed == 1

    def test_increment_task_failed(self, fleet: FleetManager) -> None:
        fleet.increment_task_count("alpha", completed=False)
        assert fleet.agents["alpha"].tasks_failed == 1

    def test_increment_multiple_times(self, fleet: FleetManager) -> None:
        for _ in range(5):
            fleet.increment_task_count("alpha", completed=True)
        assert fleet.agents["alpha"].tasks_completed == 5

    def test_increment_nonexistent_agent_silent(self, fleet: FleetManager) -> None:
        """Incrementing a nonexistent agent does not raise."""
        fleet.increment_task_count("nonexistent", completed=True)
        # Should not raise, just silently ignored

    def test_update_load_positive(self, fleet: FleetManager) -> None:
        fleet.update_agent_load("alpha", 2)
        assert fleet.agents["alpha"].current_load == 2

    def test_update_load_negative(self, fleet: FleetManager) -> None:
        fleet.update_agent_load("alpha", 3)
        fleet.update_agent_load("alpha", -1)
        assert fleet.agents["alpha"].current_load == 2

    def test_update_load_floor_zero(self, fleet: FleetManager) -> None:
        fleet.update_agent_load("alpha", -10)
        assert fleet.agents["alpha"].current_load == 0

    def test_load_at_max_sets_busy(self, fleet: FleetManager) -> None:
        fleet.update_agent_load("alpha", 5)  # max_load is 5
        assert fleet.agents["alpha"].status == "busy"

    def test_load_below_max_keeps_status(self, fleet: FleetManager) -> None:
        fleet.update_agent_load("alpha", 3)
        assert fleet.agents["alpha"].status == "active"

    def test_load_drop_from_busy_to_idle(self, fleet: FleetManager) -> None:
        fleet.update_agent_load("alpha", 5)  # becomes busy
        assert fleet.agents["alpha"].status == "busy"
        fleet.update_agent_load("alpha", -5)  # drops to 0
        assert fleet.agents["alpha"].status == "idle"

    def test_update_load_nonexistent_silent(self, fleet: FleetManager) -> None:
        fleet.update_agent_load("nonexistent", 5)
        # Should not raise


# ══════════════════════════════════════════════════════════════════════════
# FleetManager — Fleet Snapshot
# ══════════════════════════════════════════════════════════════════════════

class TestFleetSnapshotGeneration:
    """Tests for fleet snapshot generation."""

    def test_snapshot_counts_all_statuses(self, fleet: FleetManager) -> None:
        fleet.set_agent_status("alpha", "active")
        fleet.set_agent_status("beta", "idle")
        fleet.set_agent_status("gamma", "busy")
        snap = fleet.get_fleet_snapshot()
        assert snap.total_agents == 3
        assert snap.active_agents == 1
        assert snap.idle_agents == 1
        assert snap.busy_agents == 1

    def test_snapshot_offline_counted(self, fleet: FleetManager) -> None:
        fleet.set_agent_status("alpha", "offline")
        snap = fleet.get_fleet_snapshot()
        assert snap.offline_agents == 1
        assert snap.total_agents == 3

    def test_snapshot_utilization(self, fleet: FleetManager) -> None:
        fleet.update_agent_load("alpha", 2)
        fleet.update_agent_load("beta", 1)
        snap = fleet.get_fleet_snapshot()
        assert snap.total_capacity == 15  # 3 agents * 5 max_load
        assert snap.current_load == 3
        assert abs(snap.utilization_pct - 20.0) < 0.01

    def test_snapshot_capabilities_union(self, fleet: FleetManager) -> None:
        snap = fleet.get_fleet_snapshot()
        assert "code_review" in snap.all_capabilities
        assert "testing" in snap.all_capabilities
        assert "deployment" in snap.all_capabilities

    def test_snapshot_agent_details(self, fleet: FleetManager) -> None:
        snap = fleet.get_fleet_snapshot()
        assert "alpha" in snap.agents
        assert snap.agents["alpha"]["status"] == "active"
        assert "code_review" in snap.agents["alpha"]["capabilities"]


# ══════════════════════════════════════════════════════════════════════════
# FleetManager — Scaling Suggestions
# ══════════════════════════════════════════════════════════════════════════

class TestScalingSuggestions:
    """Tests for scaling suggestions."""

    def test_scale_up_high_utilization(self, fleet: FleetManager) -> None:
        fleet.update_agent_load("alpha", 5)
        fleet.update_agent_load("beta", 5)
        fleet.update_agent_load("gamma", 5)
        suggestion = fleet.get_scaling_suggestion()
        assert suggestion["action"] == "scale_up"
        assert "suggested_agents" in suggestion

    def test_scale_down_low_utilization(self, fleet: FleetManager) -> None:
        suggestion = fleet.get_scaling_suggestion()
        assert suggestion["action"] == "scale_down"
        assert "suggested_removal" in suggestion

    def test_normal_utilization(self, fleet: FleetManager) -> None:
        fleet.update_agent_load("alpha", 2)
        fleet.update_agent_load("beta", 2)
        fleet.update_agent_load("gamma", 2)
        suggestion = fleet.get_scaling_suggestion()
        assert suggestion["action"] == "none"

    def test_scale_down_single_agent_no_action(self) -> None:
        fm = FleetManager()
        fm.onboard_agent("solo", ["testing"])
        suggestion = fm.get_scaling_suggestion()
        # Single agent with low utilization should still say "none"
        assert suggestion["action"] == "none"

    def test_scaling_suggestion_has_utilization(self, fleet: FleetManager) -> None:
        suggestion = fleet.get_scaling_suggestion()
        assert "current_utilization" in suggestion
        assert isinstance(suggestion["current_utilization"], float)

    def test_scaling_suggestion_has_reason(self, fleet: FleetManager) -> None:
        suggestion = fleet.get_scaling_suggestion()
        assert "reason" in suggestion


# ══════════════════════════════════════════════════════════════════════════
# FleetManager — get_all_agent_ids
# ══════════════════════════════════════════════════════════════════════════

class TestGetAllAgentIds:
    """Tests for get_all_agent_ids."""

    def test_excludes_offline_agents(self, fleet: FleetManager) -> None:
        fleet.set_agent_status("alpha", "offline")
        ids = fleet.get_all_agent_ids()
        assert "alpha" not in ids
        assert "beta" in ids
        assert "gamma" in ids

    def test_all_active_agents_included(self, fleet: FleetManager) -> None:
        ids = fleet.get_all_agent_ids()
        assert len(ids) == 3

    def test_empty_fleet_returns_empty(self) -> None:
        fm = FleetManager()
        assert fm.get_all_agent_ids() == []


# ══════════════════════════════════════════════════════════════════════════
# FleetManager — get_agent_record
# ══════════════════════════════════════════════════════════════════════════

class TestGetAgentRecord:
    """Tests for get_agent_record."""

    def test_get_existing_record(self, fleet: FleetManager) -> None:
        record = fleet.get_agent_record("alpha")
        assert record.agent_id == "alpha"

    def test_get_nonexistent_raises(self, fleet: FleetManager) -> None:
        with pytest.raises(KeyError):
            fleet.get_agent_record("nonexistent")

    def test_record_is_mutable(self, fleet: FleetManager) -> None:
        record = fleet.get_agent_record("alpha")
        record.status = "busy"
        assert fleet.agents["alpha"].status == "busy"


# ══════════════════════════════════════════════════════════════════════════
# FleetManager — Health Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestHealthEdgeCases:
    """Edge cases for health monitoring."""

    def test_health_marked_unhealthy(self, fleet: FleetManager) -> None:
        fleet.agents["alpha"].last_heartbeat = time.time() - 600
        fleet.check_health(timeout_seconds=300.0)
        assert fleet.agents["alpha"].status == "unhealthy"

    def test_health_multiple_stale(self, fleet: FleetManager) -> None:
        fleet.agents["alpha"].last_heartbeat = time.time() - 600
        fleet.agents["beta"].last_heartbeat = time.time() - 600
        unhealthy = fleet.check_health(timeout_seconds=300.0)
        assert len(unhealthy) == 2

    def test_all_valid_statuses(self, fleet: FleetManager) -> None:
        for status in ["active", "idle", "busy", "offline", "unhealthy"]:
            fleet.set_agent_status("alpha", status)
            assert fleet.agents["alpha"].status == status

    def test_zero_timeout_marks_all_unhealthy(self, fleet: FleetManager) -> None:
        fleet.agents["alpha"].last_heartbeat = time.time() - 1
        unhealthy = fleet.check_health(timeout_seconds=0.0)
        assert "alpha" in unhealthy
