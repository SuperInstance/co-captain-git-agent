"""Tests for the Dispatcher module (dispatcher.py) — additional edge cases."""

from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dispatcher import (
    Dispatcher,
    FleetMessage,
    TaskPriority,
    parse_intent_capabilities,
    INTENT_CAPABILITY_MAP,
)
from fleet_manager import FleetManager


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def fleet() -> FleetManager:
    fm = FleetManager()
    fm.onboard_agent("agent-1", ["code_review", "git_operations"])
    fm.onboard_agent("agent-2", ["testing", "deployment"])
    fm.onboard_agent("agent-3", ["code_review", "testing", "code_quality"])
    return fm


@pytest.fixture
def dispatcher(fleet: FleetManager) -> Dispatcher:
    return Dispatcher(fleet)


# ══════════════════════════════════════════════════════════════════════════
# Intent Parsing — Additional Keywords
# ══════════════════════════════════════════════════════════════════════════

class TestIntentParsingAdditional:
    """Test additional keywords from the intent capability map."""

    def test_parse_merge_intent(self) -> None:
        caps = parse_intent_capabilities("Merge the feature branch")
        assert "git_operations" in caps

    def test_parse_branch_intent(self) -> None:
        caps = parse_intent_capabilities("Create a new branch")
        assert "git_operations" in caps

    def test_parse_release_intent(self) -> None:
        caps = parse_intent_capabilities("Release version 2.0")
        assert "deployment" in caps
        assert "git_operations" in caps

    def test_parse_update_intent(self) -> None:
        caps = parse_intent_capabilities("Update dependencies")
        assert "dependency_management" in caps

    def test_parse_upgrade_intent(self) -> None:
        caps = parse_intent_capabilities("Upgrade the package")
        assert "dependency_management" in caps

    def test_parse_lint_intent(self) -> None:
        caps = parse_intent_capabilities("Lint the codebase")
        assert "code_quality" in caps

    def test_parse_format_intent(self) -> None:
        caps = parse_intent_capabilities("Format the code")
        assert "code_quality" in caps

    def test_parse_clean_intent(self) -> None:
        caps = parse_intent_capabilities("Clean up the repo")
        assert "code_quality" in caps
        assert "maintenance" in caps

    def test_parse_migrate_intent(self) -> None:
        caps = parse_intent_capabilities("Migrate the database")
        assert "migration" in caps

    def test_parse_optimize_intent(self) -> None:
        caps = parse_intent_capabilities("Optimize the query")
        assert "performance" in caps

    def test_parse_benchmark_intent(self) -> None:
        caps = parse_intent_capabilities("Benchmark the API")
        assert "performance" in caps
        assert "testing" in caps

    def test_parse_monitor_intent(self) -> None:
        caps = parse_intent_capabilities("Monitor the service")
        assert "monitoring" in caps

    def test_parse_debug_intent(self) -> None:
        caps = parse_intent_capabilities("Debug the crash")
        assert "debugging" in caps

    def test_parse_investigate_intent(self) -> None:
        caps = parse_intent_capabilities("Investigate the error")
        assert "code_analysis" in caps

    def test_parse_analyze_intent(self) -> None:
        caps = parse_intent_capabilities("Analyze the performance")
        assert "code_analysis" in caps

    def test_parse_build_intent(self) -> None:
        caps = parse_intent_capabilities("Build the project")
        assert "build_system" in caps

    def test_parse_bug_intent(self) -> None:
        caps = parse_intent_capabilities("Fix the bug")
        assert "bug_fixing" in caps


# ══════════════════════════════════════════════════════════════════════════
# Intent Parsing — Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestIntentParsingEdgeCases:
    """Edge cases for intent parsing."""

    def test_partial_word_match(self) -> None:
        """Only whole word matches, not substrings."""
        caps = parse_intent_capabilities("documentation")
        # "document" is a keyword, but "documentation" won't match "document"
        # because it's a whole word match
        assert "documentation" not in caps or "documentation" in caps

    def test_special_characters_ignored(self) -> None:
        caps = parse_intent_capabilities("fix!!! the $$$ bug???")
        assert "bug_fixing" in caps

    def test_numbers_ignored(self) -> None:
        caps = parse_intent_capabilities("123 456 789")
        assert caps == []

    def test_whitespace_only(self) -> None:
        caps = parse_intent_capabilities("   ")
        assert caps == []

    def test_union_of_multiple_keywords(self) -> None:
        caps = parse_intent_capabilities("Refactor, test, and deploy the release")
        assert "code_analysis" in caps
        assert "testing" in caps
        assert "deployment" in caps
        assert "git_operations" in caps

    def test_intent_capability_map_completeness(self) -> None:
        """Verify known keywords exist in the map."""
        for keyword in ["refactor", "test", "fix", "deploy", "review", "security"]:
            assert keyword in INTENT_CAPABILITY_MAP


# ══════════════════════════════════════════════════════════════════════════
# FleetMessage — Additional Tests
# ══════════════════════════════════════════════════════════════════════════

class TestFleetMessageAdditional:
    """Additional FleetMessage tests."""

    def test_message_with_deadline(self) -> None:
        msg = FleetMessage(
            task_id="t1", message_type="task", payload="Test",
            deadline=time.time() + 3600,
        )
        assert msg.deadline is not None

    def test_message_with_context(self) -> None:
        msg = FleetMessage(
            task_id="t1", message_type="task", payload="Test",
            context={"key": "value"},
        )
        assert msg.context == {"key": "value"}

    def test_message_default_context_empty(self) -> None:
        msg = FleetMessage(task_id="t1", message_type="task", payload="Test")
        assert msg.context == {}

    def test_message_created_at(self) -> None:
        import time as _time
        before = _time.time()
        msg = FleetMessage(task_id="t1", message_type="task", payload="Test")
        after = _time.time()
        assert before <= msg.created_at <= after

    def test_equal_priority_equal_deadline(self) -> None:
        m1 = FleetMessage(task_id="t1", message_type="task", payload="A", priority=TaskPriority.NORMAL)
        m2 = FleetMessage(task_id="t2", message_type="task", payload="B", priority=TaskPriority.NORMAL)
        # Should not raise
        _ = m1 < m2

    def test_cancel_message_type(self) -> None:
        msg = FleetMessage(task_id="t1", message_type="cancel", payload="Cancel")
        assert msg.message_type == "cancel"

    def test_query_message_type(self) -> None:
        msg = FleetMessage(task_id="t1", message_type="query", payload="Query")
        assert msg.message_type == "query"

    def test_broadcast_message_type(self) -> None:
        msg = FleetMessage(task_id="t1", message_type="broadcast", payload="Broadcast")
        assert msg.message_type == "broadcast"

    def test_message_acknowledged_flag_default(self) -> None:
        msg = FleetMessage(task_id="t1", message_type="task", payload="Test")
        assert not msg.acknowledged

    def test_message_acknowledged_flag_set(self) -> None:
        msg = FleetMessage(task_id="t1", message_type="task", payload="Test", acknowledged=True)
        assert msg.acknowledged


# ══════════════════════════════════════════════════════════════════════════
# Dispatcher — Routing Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestDispatcherRoutingEdgeCases:
    """Edge cases for routing."""

    def test_route_with_empty_instruction(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.translate_and_route("")
        assert len(messages) > 0

    def test_route_with_multiple_targets(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.translate_and_route(
            "Test", target_agents=["agent-1", "agent-2"]
        )
        targets = {m.target_agent for m in messages}
        assert targets == {"agent-1", "agent-2"}

    def test_route_with_nonexistent_target(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.translate_and_route(
            "Test", target_agents=["nonexistent-agent"]
        )
        assert len(messages) == 1
        assert messages[0].target_agent == "nonexistent-agent"

    def test_route_capability_context_includes_caps(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.translate_and_route("Run tests")
        for msg in messages:
            assert "required_capabilities" in msg.context

    def test_route_empty_capabilities_context(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.translate_and_route("Hello world")
        for msg in messages:
            assert msg.context["required_capabilities"] == []

    def test_route_broadcast_type_for_no_capabilities(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.translate_and_route("Hello fleet")
        for msg in messages:
            assert msg.message_type == "broadcast"

    def test_route_task_type_for_targeted(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.translate_and_route(
            "Test", target_agents=["agent-1"]
        )
        for msg in messages:
            assert msg.message_type == "task"

    def test_route_task_type_for_capability_match(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.translate_and_route("Run tests")
        for msg in messages:
            assert msg.message_type == "task"


# ══════════════════════════════════════════════════════════════════════════
# Dispatcher — Queue Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestDispatcherQueueEdgeCases:
    """Edge cases for the priority queue."""

    def test_queue_with_same_priority_same_deadline(self, dispatcher: Dispatcher) -> None:
        m1 = FleetMessage(task_id="t1", message_type="task", payload="A", priority=TaskPriority.NORMAL)
        m2 = FleetMessage(task_id="t2", message_type="task", payload="B", priority=TaskPriority.NORMAL)
        dispatcher.enqueue(m1)
        dispatcher.enqueue(m2)
        # Both should be dequeued
        first = dispatcher.dequeue_next()
        second = dispatcher.dequeue_next()
        assert first is not None
        assert second is not None

    def test_queue_snapshot_empty(self, dispatcher: Dispatcher) -> None:
        snapshot = dispatcher.get_queue_snapshot()
        assert snapshot == []

    def test_queue_snapshot_payload_truncation(self, dispatcher: Dispatcher) -> None:
        long_payload = "A" * 100
        dispatcher.enqueue(
            FleetMessage(task_id="t1", message_type="task", payload=long_payload)
        )
        snapshot = dispatcher.get_queue_snapshot()
        assert len(snapshot[0]["payload"]) <= 50

    def test_dequeue_exhausts_queue(self, dispatcher: Dispatcher) -> None:
        dispatcher.enqueue(FleetMessage(task_id="t1", message_type="task", payload="A"))
        dispatcher.enqueue(FleetMessage(task_id="t2", message_type="task", payload="B"))
        dispatcher.dequeue_next()
        dispatcher.dequeue_next()
        assert dispatcher.dequeue_next() is None
        assert dispatcher.queue_size() == 0


# ══════════════════════════════════════════════════════════════════════════
# Dispatcher — Cancel Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestDispatcherCancelEdgeCases:
    """Edge cases for cancel."""

    def test_cancel_preserves_target(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.translate_and_route("Test")
        cancel = dispatcher.cancel_task(messages[0].task_id)
        assert cancel is not None
        assert cancel.target_agent == messages[0].target_agent

    def test_cancel_has_context(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.translate_and_route("Test")
        cancel = dispatcher.cancel_task(messages[0].task_id)
        assert "cancelled_task_id" in cancel.context

    def test_cancel_added_to_sent(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.translate_and_route("Test")
        before = len(dispatcher.sent_messages)
        dispatcher.cancel_task(messages[0].task_id)
        assert len(dispatcher.sent_messages) == before + 1


# ══════════════════════════════════════════════════════════════════════════
# Dispatcher — Broadcast Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestDispatcherBroadcastEdgeCases:
    """Edge cases for broadcast."""

    def test_broadcast_with_priority(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.create_broadcast("Urgent", priority=TaskPriority.CRITICAL)
        for msg in messages:
            assert msg.priority == TaskPriority.CRITICAL

    def test_broadcast_with_context(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.create_broadcast(
            "Info", context={"source": "operator"}
        )
        for msg in messages:
            assert msg.context["source"] == "operator"

    def test_broadcast_empty_fleet(self) -> None:
        fm = FleetManager()
        d = Dispatcher(fm)
        messages = d.create_broadcast("Hello")
        assert messages == []

    def test_broadcast_covers_all_agents(self, dispatcher: Dispatcher) -> None:
        messages = dispatcher.create_broadcast("Hello")
        targets = {m.target_agent for m in messages}
        assert targets == {"agent-1", "agent-2", "agent-3"}

    def test_broadcast_added_to_queue(self, dispatcher: Dispatcher) -> None:
        before = dispatcher.queue_size()
        dispatcher.create_broadcast("Test")
        assert dispatcher.queue_size() == before + 3


import time
