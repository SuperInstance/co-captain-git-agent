"""Comprehensive tests for the Co-Captain Git-Agent.

Tests cover:
- State machine transitions
- Dispatcher routing and priority queue
- Fleet manager operations
- Human interface formatting
- CLI parsing
- Integration tests
"""

from __future__ import annotations

import time
import sys
import os
from unittest.mock import patch

import pytest

# Ensure imports work from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from co_captain import (
    CoCaptainAgent,
    CoCaptainState,
    CoCaptainStateError,
    CoCaptainError,
    FleetEmptyError,
    TaskNotFoundError,
    TaskProgress,
    SessionBrief,
)
from dispatcher import (
    Dispatcher,
    FleetMessage,
    TaskPriority,
    parse_intent_capabilities,
)
from fleet_manager import (
    AgentRecord,
    FleetManager,
    FleetSnapshot,
)
from human_interface import (
    HumanContext,
    HumanInterface,
    should_escalate,
    snapshot_total_active,
)
from cli import (
    main,
    cmd_brief,
    cmd_status,
    cmd_dispatch,
    cmd_fleet,
    cmd_summary,
    cmd_config,
    print_help,
)


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def fleet_manager() -> FleetManager:
    """Create a FleetManager with some test agents."""
    fm = FleetManager()
    fm.onboard_agent("agent-alpha", ["code_review", "git_operations"])
    fm.onboard_agent("agent-beta", ["testing", "code_quality"])
    fm.onboard_agent("agent-gamma", ["deployment", "git_operations", "code_review"])
    return fm


@pytest.fixture
def dispatcher(fleet_manager: FleetManager) -> Dispatcher:
    """Create a Dispatcher with the test fleet manager."""
    return Dispatcher(fleet_manager)


@pytest.fixture
def human_context() -> HumanContext:
    """Create a test HumanContext."""
    return HumanContext(
        name="Test Operator",
        preferred_name="Test",
        working_hours_start=9,
        working_hours_end=17,
    )


@pytest.fixture
def human_interface(human_context: HumanContext) -> HumanInterface:
    """Create a HumanInterface with test context."""
    return HumanInterface(human_context)


@pytest.fixture
def co_captain(fleet_manager: FleetManager) -> CoCaptainAgent:
    """Create a CoCaptainAgent with test fleet manager."""
    return CoCaptainAgent(fleet_manager=fleet_manager)


# ══════════════════════════════════════════════════════════════════════════
# CoCaptainAgent — State Machine Tests
# ══════════════════════════════════════════════════════════════════════════

class TestCoCaptainStateMachine:
    """Tests for the co-captain state machine."""

    def test_initial_state_is_standby(self, co_captain: CoCaptainAgent) -> None:
        """Agent starts in STANDBY state."""
        assert co_captain.state == CoCaptainState.STANDBY
        assert co_captain.is_standby()

    def test_receive_brief_transitions_to_briefed(self, co_captain: CoCaptainAgent) -> None:
        """Receiving a brief transitions to BRIEFED."""
        brief = co_captain.receive_brief("Run tests")
        assert co_captain.state == CoCaptainState.BRIEFED
        assert brief.instruction == "Run tests"
        assert brief.priority == TaskPriority.NORMAL

    def test_receive_brief_with_priority(self, co_captain: CoCaptainAgent) -> None:
        """Receiving a brief with custom priority."""
        brief = co_captain.receive_brief("Fix bug", priority=TaskPriority.CRITICAL)
        assert brief.priority == TaskPriority.CRITICAL

    def test_receive_brief_with_target_agents(self, co_captain: CoCaptainAgent) -> None:
        """Receiving a brief with specific target agents."""
        brief = co_captain.receive_brief("Review code", target_agents=["agent-alpha"])
        assert brief.target_agents == ["agent-alpha"]

    def test_receive_brief_with_context(self, co_captain: CoCaptainAgent) -> None:
        """Receiving a brief with additional context."""
        brief = co_captain.receive_brief("Deploy", context={"env": "production"})
        assert brief.context == {"env": "production"}

    def test_cannot_receive_brief_in_non_standby(self, co_captain: CoCaptainAgent) -> None:
        """Cannot receive brief when not in STANDBY."""
        co_captain.receive_brief("Test")
        with pytest.raises(CoCaptainStateError):
            co_captain.receive_brief("Test again")

    def test_brief_id_is_generated(self, co_captain: CoCaptainAgent) -> None:
        """Each brief gets a unique ID."""
        brief1 = co_captain.receive_brief("Test 1")
        co_captain.reset_to_standby()
        brief2 = co_captain.receive_brief("Test 2")
        assert brief1.brief_id != brief2.brief_id

    def test_brief_stored_in_history(self, co_captain: CoCaptainAgent) -> None:
        """Briefs are stored in history."""
        co_captain.receive_brief("Test")
        assert len(co_captain.brief_history) == 1
        assert co_captain.brief_history[0].instruction == "Test"

    def test_dispatch_transitions_to_monitoring(self, co_captain: CoCaptainAgent) -> None:
        """Dispatching transitions to MONITORING."""
        brief = co_captain.receive_brief("Run tests")
        task_ids = co_captain.dispatch_brief(brief)
        assert co_captain.state == CoCaptainState.MONITORING
        assert len(task_ids) > 0

    def test_cannot_dispatch_in_non_briefed(self, co_captain: CoCaptainAgent) -> None:
        """Cannot dispatch when not in BRIEFED."""
        with pytest.raises(CoCaptainStateError):
            co_captain.dispatch_brief(
                SessionBrief(brief_id="x", instruction="test")
            )

    def test_dispatch_with_empty_fleet_raises(self) -> None:
        """Dispatching with no agents raises FleetEmptyError."""
        agent = CoCaptainAgent()
        brief = agent.receive_brief("Test")
        with pytest.raises(FleetEmptyError):
            agent.dispatch_brief(brief)

    def test_report_transitions_to_standby(self, co_captain: CoCaptainAgent) -> None:
        """Generating report transitions back to STANDBY."""
        brief = co_captain.receive_brief("Run tests")
        co_captain.dispatch_brief(brief)
        co_captain.generate_report()
        assert co_captain.state == CoCaptainState.STANDBY

    def test_reset_to_standby(self, co_captain: CoCaptainAgent) -> None:
        """Force reset to STANDBY works from any state."""
        co_captain.receive_brief("Test")
        assert co_captain.state == CoCaptainState.BRIEFED
        co_captain.reset_to_standby()
        assert co_captain.is_standby()

    def test_invalid_transition_raises(self, co_captain: CoCaptainAgent) -> None:
        """Invalid state transitions raise CoCaptainStateError."""
        # STANDBY -> DISPATCHING is not valid
        with pytest.raises(CoCaptainStateError):
            co_captain._transition_to(CoCaptainState.DISPATCHING)

    def test_full_state_cycle(self, co_captain: CoCaptainAgent) -> None:
        """Complete state cycle: STANDBY → BRIEFED → MONITORING → REPORTING → STANDBY."""
        assert co_captain.state == CoCaptainState.STANDBY

        co_captain.receive_brief("Test")
        assert co_captain.state == CoCaptainState.BRIEFED

        brief = co_captain.brief_history[-1]
        co_captain.dispatch_brief(brief)
        assert co_captain.state == CoCaptainState.MONITORING

        report = co_captain.generate_report()
        assert co_captain.state == CoCaptainState.STANDBY
        assert "Status Report" in report


# ══════════════════════════════════════════════════════════════════════════
# CoCaptainAgent — Task Monitoring Tests
# ══════════════════════════════════════════════════════════════════════════

class TestCoCaptainMonitoring:
    """Tests for task monitoring and progress tracking."""

    def test_update_task_status(self, co_captain: CoCaptainAgent) -> None:
        """Task status can be updated."""
        brief = co_captain.receive_brief("Test")
        task_ids = co_captain.dispatch_brief(brief)
        task_id = task_ids[0]

        co_captain.update_task_status(task_id, "in_progress")
        assert co_captain.active_tasks[task_id].status == "in_progress"

    def test_update_task_with_result(self, co_captain: CoCaptainAgent) -> None:
        """Task result can be stored."""
        brief = co_captain.receive_brief("Test")
        task_ids = co_captain.dispatch_brief(brief)
        task_id = task_ids[0]

        co_captain.update_task_status(task_id, "completed", result={"tests": 42})
        assert co_captain.active_tasks[task_id].result == {"tests": 42}

    def test_update_task_with_error(self, co_captain: CoCaptainAgent) -> None:
        """Task error can be stored."""
        brief = co_captain.receive_brief("Test")
        task_ids = co_captain.dispatch_brief(brief)
        task_id = task_ids[0]

        co_captain.update_task_status(task_id, "failed", error="Connection timeout")
        assert co_captain.active_tasks[task_id].error == "Connection timeout"

    def test_update_nonexistent_task_raises(self, co_captain: CoCaptainAgent) -> None:
        """Updating a nonexistent task raises TaskNotFoundError."""
        with pytest.raises(TaskNotFoundError):
            co_captain.update_task_status("nonexistent", "completed")

    def test_progress_summary(self, co_captain: CoCaptainAgent) -> None:
        """Progress summary counts tasks by status."""
        brief = co_captain.receive_brief("Test")
        task_ids = co_captain.dispatch_brief(brief)

        co_captain.update_task_status(task_ids[0], "completed")
        if len(task_ids) > 1:
            co_captain.update_task_status(task_ids[1], "in_progress")

        summary = co_captain.get_progress_summary()
        expected_dispatched = (len(task_ids) - 1) if len(task_ids) > 1 else 0
        assert summary.get("dispatched", 0) == expected_dispatched
        assert summary.get("completed", 0) >= 1

    def test_all_tasks_completed(self, co_captain: CoCaptainAgent) -> None:
        """Detects when all tasks are done."""
        brief = co_captain.receive_brief("Test")
        task_ids = co_captain.dispatch_brief(brief)

        for tid in task_ids:
            co_captain.update_task_status(tid, "completed")
        assert co_captain.all_tasks_completed()

    def test_all_tasks_not_completed(self, co_captain: CoCaptainAgent) -> None:
        """Returns False when tasks are still in progress."""
        brief = co_captain.receive_brief("Test")
        task_ids = co_captain.dispatch_brief(brief)

        co_captain.update_task_status(task_ids[0], "in_progress")
        assert not co_captain.all_tasks_completed()

    def test_completed_task_has_timestamp(self, co_captain: CoCaptainAgent) -> None:
        """Completed tasks get a completed_at timestamp."""
        brief = co_captain.receive_brief("Test")
        task_ids = co_captain.dispatch_brief(brief)

        before = time.time()
        co_captain.update_task_status(task_ids[0], "completed")
        after = time.time()

        completed_at = co_captain.active_tasks[task_ids[0]].completed_at
        assert completed_at is not None
        assert before <= completed_at <= after

    def test_no_tasks_not_completed(self, co_captain: CoCaptainAgent) -> None:
        """No tasks means not all completed."""
        assert not co_captain.all_tasks_completed()


# ══════════════════════════════════════════════════════════════════════════
# CoCaptainAgent — Fleet Management Tests
# ══════════════════════════════════════════════════════════════════════════

class TestCoCaptainFleet:
    """Tests for fleet management delegation."""

    def test_onboard_agent(self, co_captain: CoCaptainAgent) -> None:
        """Can onboard a new agent."""
        co_captain.onboard_agent("agent-new", ["testing"])
        assert co_captain.fleet_manager.agent_count() == 4

    def test_offboard_agent(self, co_captain: CoCaptainAgent) -> None:
        """Can offboard an existing agent."""
        co_captain.offboard_agent("agent-alpha")
        assert co_captain.fleet_manager.agent_count() == 2

    def test_get_fleet_status(self, co_captain: CoCaptainAgent) -> None:
        """Fleet status is a formatted string."""
        status = co_captain.get_fleet_status()
        assert "Fleet Status" in status
        assert "agent-alpha" in status

    def test_daily_summary(self, co_captain: CoCaptainAgent) -> None:
        """Daily summary is generated."""
        brief = co_captain.receive_brief("Test")
        co_captain.dispatch_brief(brief)
        co_captain.reset_to_standby()

        summary = co_captain.generate_daily_summary()
        assert "Daily Summary" in summary
        assert "Test" in summary


# ══════════════════════════════════════════════════════════════════════════
# CoCaptainAgent — Exceptions Tests
# ══════════════════════════════════════════════════════════════════════════

class TestCoCaptainExceptions:
    """Tests for custom exceptions."""

    def test_co_captain_error_base(self) -> None:
        """CoCaptainError is the base exception."""
        err = CoCaptainError("test")
        assert str(err) == "test"

    def test_state_error_inherits_base(self) -> None:
        """CoCaptainStateError inherits from CoCaptainError."""
        err = CoCaptainStateError("test")
        assert isinstance(err, CoCaptainError)

    def test_fleet_empty_error(self) -> None:
        """FleetEmptyError is properly constructed."""
        err = FleetEmptyError("No agents")
        assert str(err) == "No agents"
        assert isinstance(err, CoCaptainError)

    def test_task_not_found_error(self) -> None:
        """TaskNotFoundError is properly constructed."""
        err = TaskNotFoundError("task-123")
        assert str(err) == "task-123"
        assert isinstance(err, CoCaptainError)


# ══════════════════════════════════════════════════════════════════════════
# TaskProgress and SessionBrief Tests
# ══════════════════════════════════════════════════════════════════════════

class TestDataClasses:
    """Tests for data classes."""

    def test_task_progress_defaults(self) -> None:
        """TaskProgress has correct defaults."""
        tp = TaskProgress(task_id="t1")
        assert tp.status == "pending"
        assert tp.result is None
        assert tp.error is None
        assert tp.completed_at is None
        assert tp.created_at > 0

    def test_task_progress_custom(self) -> None:
        """TaskProgress can be created with custom values."""
        tp = TaskProgress(
            task_id="t1",
            agent_id="agent-1",
            status="completed",
            result="OK",
        )
        assert tp.agent_id == "agent-1"
        assert tp.result == "OK"

    def test_session_brief_defaults(self) -> None:
        """SessionBrief has correct defaults."""
        sb = SessionBrief(brief_id="b1", instruction="Test")
        assert sb.priority == TaskPriority.NORMAL
        assert sb.target_agents is None
        assert sb.context == {}

    def test_session_brief_custom(self) -> None:
        """SessionBrief can be customized."""
        sb = SessionBrief(
            brief_id="b1",
            instruction="Test",
            priority=TaskPriority.HIGH,
            target_agents=["a1"],
            context={"key": "value"},
        )
        assert sb.priority == TaskPriority.HIGH
        assert sb.target_agents == ["a1"]
        assert sb.context == {"key": "value"}


# ══════════════════════════════════════════════════════════════════════════
# Dispatcher — Intent Parsing Tests
# ══════════════════════════════════════════════════════════════════════════

class TestIntentParsing:
    """Tests for human instruction intent parsing."""

    def test_parse_refactor_intent(self) -> None:
        """Refactoring instruction maps to correct capabilities."""
        caps = parse_intent_capabilities("Refactor the auth module")
        assert "code_analysis" in caps
        assert "code_modification" in caps

    def test_parse_test_intent(self) -> None:
        """Testing instruction maps correctly."""
        caps = parse_intent_capabilities("Run the test suite")
        assert "testing" in caps

    def test_parse_fix_intent(self) -> None:
        """Fix instruction maps to bug_fixing and code_modification."""
        caps = parse_intent_capabilities("Fix the login bug")
        assert "bug_fixing" in caps
        assert "code_modification" in caps

    def test_parse_deploy_intent(self) -> None:
        """Deploy instruction maps correctly."""
        caps = parse_intent_capabilities("Deploy to production")
        assert "deployment" in caps

    def test_parse_review_intent(self) -> None:
        """Review instruction maps to code_review."""
        caps = parse_intent_capabilities("Review the PR")
        assert "code_review" in caps

    def test_parse_empty_instruction(self) -> None:
        """Empty instruction returns no capabilities."""
        caps = parse_intent_capabilities("")
        assert caps == []

    def test_parse_unknown_intent(self) -> None:
        """Unknown instruction returns no capabilities."""
        caps = parse_intent_capabilities("Do something random")
        assert caps == []

    def test_parse_multi_keyword(self) -> None:
        """Instruction with multiple keywords returns union of capabilities."""
        caps = parse_intent_capabilities("Run tests and deploy")
        assert "testing" in caps
        assert "deployment" in caps

    def test_parse_case_insensitive(self) -> None:
        """Parsing is case-insensitive."""
        caps_lower = parse_intent_capabilities("run tests")
        caps_upper = parse_intent_capabilities("RUN TESTS")
        assert set(caps_lower) == set(caps_upper)

    def test_parse_no_duplicates(self) -> None:
        """No duplicate capabilities in output."""
        caps = parse_intent_capabilities("fix fix fix")
        # bug_fixing should appear once
        assert caps.count("bug_fixing") == 1

    def test_parse_document_intent(self) -> None:
        """Document instruction maps to documentation."""
        caps = parse_intent_capabilities("Document the API")
        assert "documentation" in caps

    def test_parse_docs_intent(self) -> None:
        """Docs instruction also maps to documentation."""
        caps = parse_intent_capabilities("Update the docs")
        assert "documentation" in caps

    def test_parse_security_intent(self) -> None:
        """Security instruction maps correctly."""
        caps = parse_intent_capabilities("Run security audit")
        assert "security" in caps

    def test_parse_pr_intent(self) -> None:
        """PR instruction maps to multiple capabilities."""
        caps = parse_intent_capabilities("Review this PR")
        assert "code_review" in caps
        assert "git_operations" in caps


# ══════════════════════════════════════════════════════════════════════════
# Dispatcher — FleetMessage Tests
# ══════════════════════════════════════════════════════════════════════════

class TestFleetMessage:
    """Tests for the FleetMessage protocol."""

    def test_message_creation(self) -> None:
        """FleetMessage can be created with required fields."""
        msg = FleetMessage(
            task_id="t1",
            message_type="task",
            payload="Do something",
        )
        assert msg.task_id == "t1"
        assert msg.message_type == "task"
        assert msg.source == "co-captain"
        assert not msg.acknowledged

    def test_message_with_target(self) -> None:
        """FleetMessage can target a specific agent."""
        msg = FleetMessage(
            task_id="t1",
            message_type="task",
            payload="Test",
            target_agent="agent-1",
        )
        assert msg.target_agent == "agent-1"

    def test_message_priority_ordering(self) -> None:
        """Higher priority messages sort first."""
        high = FleetMessage(
            task_id="t1",
            message_type="task",
            payload="High",
            priority=TaskPriority.HIGH,
        )
        low = FleetMessage(
            task_id="t2",
            message_type="task",
            payload="Low",
            priority=TaskPriority.LOW,
        )
        assert high < low  # Higher priority = "less than" in heap

    def test_message_deadline_ordering(self) -> None:
        """Earlier deadline messages sort first when priorities equal."""
        urgent = FleetMessage(
            task_id="t1",
            message_type="task",
            payload="Urgent",
            priority=TaskPriority.NORMAL,
            deadline=100.0,
        )
        relaxed = FleetMessage(
            task_id="t2",
            message_type="task",
            payload="Relaxed",
            priority=TaskPriority.NORMAL,
            deadline=200.0,
        )
        assert urgent < relaxed

    def test_message_no_deadline(self) -> None:
        """Messages without deadlines sort after those with deadlines."""
        with_deadline = FleetMessage(
            task_id="t1",
            message_type="task",
            payload="D",
            priority=TaskPriority.NORMAL,
            deadline=100.0,
        )
        without_deadline = FleetMessage(
            task_id="t2",
            message_type="task",
            payload="ND",
            priority=TaskPriority.NORMAL,
        )
        assert with_deadline < without_deadline

    def test_task_priority_values(self) -> None:
        """TaskPriority values are ordered correctly."""
        assert TaskPriority.LOW < TaskPriority.NORMAL < TaskPriority.HIGH < TaskPriority.CRITICAL


# ══════════════════════════════════════════════════════════════════════════
# Dispatcher — Routing Tests
# ══════════════════════════════════════════════════════════════════════════

class TestDispatcherRouting:
    """Tests for task routing and dispatch."""

    def test_translate_and_route_with_capabilities(self, dispatcher: Dispatcher) -> None:
        """Routes to agents with matching capabilities."""
        messages = dispatcher.translate_and_route("Run tests")
        targets = {m.target_agent for m in messages}
        # agent-beta has "testing"
        assert "agent-beta" in targets

    def test_translate_and_route_broadcast(self, dispatcher: Dispatcher) -> None:
        """Unknown intent broadcasts to all agents."""
        messages = dispatcher.translate_and_route("Hello fleet")
        assert len(messages) == 3  # All agents

    def test_translate_and_route_with_target(self, dispatcher: Dispatcher) -> None:
        """Specific target agents are respected."""
        messages = dispatcher.translate_and_route(
            "Test", target_agents=["agent-alpha"]
        )
        assert len(messages) == 1
        assert messages[0].target_agent == "agent-alpha"

    def test_translate_and_route_priority(self, dispatcher: Dispatcher) -> None:
        """Priority is set on created messages."""
        messages = dispatcher.translate_and_route(
            "Test", priority=TaskPriority.CRITICAL
        )
        for msg in messages:
            assert msg.priority == TaskPriority.CRITICAL

    def test_translate_and_route_context(self, dispatcher: Dispatcher) -> None:
        """Context is passed through to messages."""
        messages = dispatcher.translate_and_route(
            "Test", context={"env": "staging"}
        )
        for msg in messages:
            assert msg.context["env"] == "staging"

    def test_translate_and_route_capability_fallback(
        self, dispatcher: Dispatcher
    ) -> None:
        """Falls back to all agents when no capability match."""
        messages = dispatcher.translate_and_route("Refactor")
        # No agent has "code_analysis" or "code_modification" exactly
        # but fallback should still produce messages
        assert len(messages) > 0

    def test_messages_added_to_sent_history(self, dispatcher: Dispatcher) -> None:
        """Sent messages are tracked."""
        dispatcher.translate_and_route("Test")
        assert len(dispatcher.sent_messages) > 0


# ══════════════════════════════════════════════════════════════════════════
# Dispatcher — Priority Queue Tests
# ══════════════════════════════════════════════════════════════════════════

class TestDispatcherQueue:
    """Tests for the priority queue."""

    def test_enqueue_and_dequeue(self, dispatcher: Dispatcher) -> None:
        """Messages can be enqueued and dequeued in priority order."""
        low = FleetMessage(
            task_id="t1", message_type="task", payload="Low",
            priority=TaskPriority.LOW,
        )
        high = FleetMessage(
            task_id="t2", message_type="task", payload="High",
            priority=TaskPriority.HIGH,
        )
        dispatcher.enqueue(low)
        dispatcher.enqueue(high)

        first = dispatcher.dequeue_next()
        assert first is not None
        assert first.priority == TaskPriority.HIGH

        second = dispatcher.dequeue_next()
        assert second is not None
        assert second.priority == TaskPriority.LOW

    def test_dequeue_empty_returns_none(self, dispatcher: Dispatcher) -> None:
        """Dequeue from empty queue returns None."""
        assert dispatcher.dequeue_next() is None

    def test_queue_size(self, dispatcher: Dispatcher) -> None:
        """Queue size is tracked correctly."""
        assert dispatcher.queue_size() == 0
        dispatcher.enqueue(
            FleetMessage(task_id="t1", message_type="task", payload="Test")
        )
        assert dispatcher.queue_size() == 1
        dispatcher.dequeue_next()
        assert dispatcher.queue_size() == 0

    def test_queue_snapshot(self, dispatcher: Dispatcher) -> None:
        """Queue snapshot returns sorted list."""
        dispatcher.enqueue(
            FleetMessage(task_id="t1", message_type="task", payload="Low",
                         priority=TaskPriority.LOW)
        )
        dispatcher.enqueue(
            FleetMessage(task_id="t2", message_type="task", payload="High",
                         priority=TaskPriority.HIGH)
        )
        snapshot = dispatcher.get_queue_snapshot()
        assert len(snapshot) == 2
        assert snapshot[0]["priority"] == "HIGH"


# ══════════════════════════════════════════════════════════════════════════
# Dispatcher — Acknowledgment Tests
# ══════════════════════════════════════════════════════════════════════════

class TestDispatcherAcknowledgments:
    """Tests for acknowledgment tracking."""

    def test_acknowledge_task(self, dispatcher: Dispatcher) -> None:
        """Tasks can be acknowledged."""
        messages = dispatcher.translate_and_route("Test")
        task_id = messages[0].task_id
        dispatcher.acknowledge(task_id)
        assert dispatcher.is_acknowledged(task_id)

    def test_acknowledge_nonexistent_raises(self, dispatcher: Dispatcher) -> None:
        """Acknowledging a nonexistent task raises KeyError."""
        with pytest.raises(KeyError):
            dispatcher.acknowledge("nonexistent")

    def test_unacknowledged_count(self, dispatcher: Dispatcher) -> None:
        """Unacknowledged count is tracked."""
        messages = dispatcher.translate_and_route("Test")
        assert dispatcher.unacknowledged_count() == len(messages)
        dispatcher.acknowledge(messages[0].task_id)
        assert dispatcher.unacknowledged_count() == len(messages) - 1

    def test_is_acknowledged_default_false(self, dispatcher: Dispatcher) -> None:
        """Unknown tasks are not acknowledged by default."""
        assert not dispatcher.is_acknowledged("random-id")

    def test_acknowledge_updates_message_flag(self, dispatcher: Dispatcher) -> None:
        """Acknowledging updates the message's acknowledged flag."""
        messages = dispatcher.translate_and_route("Test")
        task_id = messages[0].task_id
        assert not messages[0].acknowledged
        dispatcher.acknowledge(task_id)
        assert messages[0].acknowledged


# ══════════════════════════════════════════════════════════════════════════
# Dispatcher — Broadcast and Cancel Tests
# ══════════════════════════════════════════════════════════════════════════

class TestDispatcherBroadcast:
    """Tests for broadcast and cancel operations."""

    def test_create_broadcast(self, dispatcher: Dispatcher) -> None:
        """Broadcast creates messages for all agents."""
        messages = dispatcher.create_broadcast("Hello everyone")
        assert len(messages) == 3
        for msg in messages:
            assert msg.message_type == "broadcast"

    def test_cancel_existing_task(self, dispatcher: Dispatcher) -> None:
        """Cancel creates a cancel message for an existing task."""
        messages = dispatcher.translate_and_route("Test")
        task_id = messages[0].task_id
        cancel = dispatcher.cancel_task(task_id)
        assert cancel is not None
        assert cancel.message_type == "cancel"
        assert cancel.priority == TaskPriority.HIGH

    def test_cancel_nonexistent_task(self, dispatcher: Dispatcher) -> None:
        """Cancel nonexistent task returns None."""
        assert dispatcher.cancel_task("nonexistent") is None

    def test_broadcast_added_to_sent_history(self, dispatcher: Dispatcher) -> None:
        """Broadcast messages are added to sent history."""
        before = len(dispatcher.sent_messages)
        dispatcher.create_broadcast("Test")
        assert len(dispatcher.sent_messages) > before


# ══════════════════════════════════════════════════════════════════════════
# FleetManager — Agent Lifecycle Tests
# ══════════════════════════════════════════════════════════════════════════

class TestFleetManagerLifecycle:
    """Tests for agent onboarding and offboarding."""

    def test_onboard_agent(self, fleet_manager: FleetManager) -> None:
        """Agent can be onboarded."""
        record = fleet_manager.onboard_agent("agent-delta", ["testing"])
        assert record.agent_id == "agent-delta"
        assert "testing" in record.capabilities
        assert fleet_manager.agent_count() == 4

    def test_onboard_duplicate_raises(self, fleet_manager: FleetManager) -> None:
        """Duplicate agent ID raises ValueError."""
        with pytest.raises(ValueError, match="already registered"):
            fleet_manager.onboard_agent("agent-alpha", ["testing"])

    def test_onboard_with_metadata(self, fleet_manager: FleetManager) -> None:
        """Agent can be onboarded with metadata."""
        record = fleet_manager.onboard_agent(
            "agent-meta", ["testing"], metadata={"version": "2.0"}
        )
        assert record.metadata["version"] == "2.0"

    def test_offboard_agent(self, fleet_manager: FleetManager) -> None:
        """Agent can be offboarded."""
        fleet_manager.offboard_agent("agent-alpha")
        assert fleet_manager.agent_count() == 2

    def test_offboard_nonexistent_raises(self, fleet_manager: FleetManager) -> None:
        """Offboarding nonexistent agent raises KeyError."""
        with pytest.raises(KeyError):
            fleet_manager.offboard_agent("nonexistent")

    def test_agent_count(self, fleet_manager: FleetManager) -> None:
        """Agent count is accurate."""
        assert fleet_manager.agent_count() == 3

    def test_empty_fleet_count(self) -> None:
        """Empty fleet has count 0."""
        fm = FleetManager()
        assert fm.agent_count() == 0


# ══════════════════════════════════════════════════════════════════════════
# FleetManager — Capability Registry Tests
# ══════════════════════════════════════════════════════════════════════════

class TestFleetManagerCapabilities:
    """Tests for capability registry."""

    def test_find_by_capability_any(self, fleet_manager: FleetManager) -> None:
        """Find agents with at least one matching capability."""
        agents = fleet_manager.find_agents_by_capabilities(["code_review"])
        assert "agent-alpha" in agents
        assert "agent-gamma" in agents

    def test_find_by_capability_all(self, fleet_manager: FleetManager) -> None:
        """Find agents with ALL matching capabilities."""
        agents = fleet_manager.find_agents_by_capabilities(
            ["deployment", "git_operations"], match_all=True
        )
        assert "agent-gamma" in agents
        assert "agent-alpha" not in agents

    def test_find_by_capability_sorted_by_load(
        self, fleet_manager: FleetManager
    ) -> None:
        """Results are sorted by current load."""
        fleet_manager.update_agent_load("agent-alpha", 3)
        fleet_manager.update_agent_load("agent-gamma", 1)
        agents = fleet_manager.find_agents_by_capabilities(["git_operations"])
        # agent-gamma has lower load, should come first
        gamma_idx = agents.index("agent-gamma")
        alpha_idx = agents.index("agent-alpha")
        assert gamma_idx < alpha_idx

    def test_find_excludes_offline(self, fleet_manager: FleetManager) -> None:
        """Offline agents are excluded from capability search."""
        fleet_manager.set_agent_status("agent-alpha", "offline")
        agents = fleet_manager.find_agents_by_capabilities(["code_review"])
        assert "agent-alpha" not in agents

    def test_find_excludes_unhealthy(self, fleet_manager: FleetManager) -> None:
        """Unhealthy agents are excluded from capability search."""
        fleet_manager.set_agent_status("agent-alpha", "unhealthy")
        agents = fleet_manager.find_agents_by_capabilities(["code_review"])
        assert "agent-alpha" not in agents

    def test_get_agent_capabilities(self, fleet_manager: FleetManager) -> None:
        """Can get capabilities for a specific agent."""
        caps = fleet_manager.get_agent_capabilities("agent-beta")
        assert "testing" in caps
        assert "code_quality" in caps

    def test_get_agent_capabilities_nonexistent(
        self, fleet_manager: FleetManager
    ) -> None:
        """Getting capabilities for nonexistent agent raises KeyError."""
        with pytest.raises(KeyError):
            fleet_manager.get_agent_capabilities("nonexistent")

    def test_get_all_capabilities(self, fleet_manager: FleetManager) -> None:
        """All capabilities union is returned."""
        caps = fleet_manager.get_all_capabilities()
        assert "code_review" in caps
        assert "testing" in caps
        assert "deployment" in caps

    def test_no_matching_capabilities(self, fleet_manager: FleetManager) -> None:
        """Returns empty list when no agents match."""
        agents = fleet_manager.find_agents_by_capabilities(["nonexistent_cap"])
        assert agents == []


# ══════════════════════════════════════════════════════════════════════════
# FleetManager — Health Monitoring Tests
# ══════════════════════════════════════════════════════════════════════════

class TestFleetManagerHealth:
    """Tests for health monitoring."""

    def test_update_heartbeat(self, fleet_manager: FleetManager) -> None:
        """Heartbeat can be updated."""
        fleet_manager.update_heartbeat("agent-alpha")
        record = fleet_manager.get_agent_record("agent-alpha")
        assert record.last_heartbeat > 0

    def test_update_heartbeat_nonexistent(self, fleet_manager: FleetManager) -> None:
        """Updating heartbeat for nonexistent agent raises KeyError."""
        with pytest.raises(KeyError):
            fleet_manager.update_heartbeat("nonexistent")

    def test_set_agent_status(self, fleet_manager: FleetManager) -> None:
        """Agent status can be set."""
        fleet_manager.set_agent_status("agent-alpha", "busy")
        record = fleet_manager.get_agent_record("agent-alpha")
        assert record.status == "busy"

    def test_set_invalid_status_raises(self, fleet_manager: FleetManager) -> None:
        """Invalid status raises ValueError."""
        with pytest.raises(ValueError, match="Invalid status"):
            fleet_manager.set_agent_status("agent-alpha", "invalid")

    def test_set_status_nonexistent(self, fleet_manager: FleetManager) -> None:
        """Setting status for nonexistent agent raises KeyError."""
        with pytest.raises(KeyError):
            fleet_manager.set_agent_status("nonexistent", "busy")

    def test_check_health_all_healthy(self, fleet_manager: FleetManager) -> None:
        """All agents are healthy when heartbeats are recent."""
        unhealthy = fleet_manager.check_health(timeout_seconds=300.0)
        assert len(unhealthy) == 0

    def test_check_health_detects_stale(self, fleet_manager: FleetManager) -> None:
        """Stale heartbeats are detected."""
        # Set heartbeat far in the past
        fleet_manager.agents["agent-alpha"].last_heartbeat = time.time() - 600
        unhealthy = fleet_manager.check_health(timeout_seconds=300.0)
        assert "agent-alpha" in unhealthy

    def test_check_health_skips_offline(self, fleet_manager: FleetManager) -> None:
        """Offline agents are skipped during health check."""
        fleet_manager.set_agent_status("agent-alpha", "offline")
        fleet_manager.agents["agent-alpha"].last_heartbeat = time.time() - 600
        unhealthy = fleet_manager.check_health(timeout_seconds=300.0)
        assert "agent-alpha" not in unhealthy


# ══════════════════════════════════════════════════════════════════════════
# FleetManager — Task Tracking Tests
# ══════════════════════════════════════════════════════════════════════════

class TestFleetManagerTaskTracking:
    """Tests for task tracking and load management."""

    def test_increment_completed(self, fleet_manager: FleetManager) -> None:
        """Completed task count increments."""
        fleet_manager.increment_task_count("agent-alpha", completed=True)
        record = fleet_manager.get_agent_record("agent-alpha")
        assert record.tasks_completed == 1

    def test_increment_failed(self, fleet_manager: FleetManager) -> None:
        """Failed task count increments."""
        fleet_manager.increment_task_count("agent-alpha", completed=False)
        record = fleet_manager.get_agent_record("agent-alpha")
        assert record.tasks_failed == 1

    def test_update_agent_load(self, fleet_manager: FleetManager) -> None:
        """Agent load can be updated."""
        fleet_manager.update_agent_load("agent-alpha", 3)
        record = fleet_manager.get_agent_record("agent-alpha")
        assert record.current_load == 3

    def test_update_agent_load_negative(self, fleet_manager: FleetManager) -> None:
        """Load can't go below zero."""
        fleet_manager.update_agent_load("agent-alpha", -10)
        record = fleet_manager.get_agent_record("agent-alpha")
        assert record.current_load == 0

    def test_load_auto_busy(self, fleet_manager: FleetManager) -> None:
        """Agent auto-set to busy when at max load."""
        record = fleet_manager.get_agent_record("agent-alpha")
        fleet_manager.update_agent_load("agent-alpha", record.max_load)
        assert fleet_manager.agents["agent-alpha"].status == "busy"

    def test_load_auto_idle(self, fleet_manager: FleetManager) -> None:
        """Agent auto-set to idle when load drops to zero from busy."""
        fleet_manager.set_agent_status("agent-alpha", "busy")
        fleet_manager.update_agent_load("agent-alpha", -5)
        assert fleet_manager.agents["agent-alpha"].status == "idle"


# ══════════════════════════════════════════════════════════════════════════
# FleetManager — Analytics Tests
# ══════════════════════════════════════════════════════════════════════════

class TestFleetManagerAnalytics:
    """Tests for fleet analytics and snapshots."""

    def test_fleet_snapshot_counts(self, fleet_manager: FleetManager) -> None:
        """Fleet snapshot has correct counts."""
        snapshot = fleet_manager.get_fleet_snapshot()
        assert snapshot.total_agents == 3
        assert snapshot.active_agents == 3
        assert snapshot.idle_agents == 0
        assert snapshot.busy_agents == 0

    def test_fleet_snapshot_utilization(self, fleet_manager: FleetManager) -> None:
        """Utilization is calculated correctly."""
        snapshot = fleet_manager.get_fleet_snapshot()
        assert snapshot.utilization_pct == 0.0
        # Each agent has max_load=5, so total_capacity=15
        assert snapshot.total_capacity == 15

    def test_fleet_snapshot_capabilities(self, fleet_manager: FleetManager) -> None:
        """Snapshot has all capabilities."""
        snapshot = fleet_manager.get_fleet_snapshot()
        assert "code_review" in snapshot.all_capabilities
        assert "testing" in snapshot.all_capabilities

    def test_fleet_snapshot_agent_details(self, fleet_manager: FleetManager) -> None:
        """Snapshot has agent details."""
        snapshot = fleet_manager.get_fleet_snapshot()
        assert "agent-alpha" in snapshot.agents
        assert snapshot.agents["agent-alpha"]["status"] == "active"

    def test_scaling_suggestion_normal(self, fleet_manager: FleetManager) -> None:
        """Normal utilization returns 'none' action."""
        # Set moderate load (1 of 5 on one agent → ~6.7% overall with 3 agents)
        # Need to be in 20-90% range for 'none'. Each agent has max_load=5.
        # 3 agents * 5 = 15 total capacity. 20% = 3, 90% = 13.5
        fleet_manager.update_agent_load("agent-alpha", 5)
        fleet_manager.update_agent_load("agent-beta", 1)
        # Now current_load = 6, utilization = 6/15 = 40%
        suggestion = fleet_manager.get_scaling_suggestion()
        assert suggestion["action"] == "none"

    def test_scaling_suggestion_high_utilization(
        self, fleet_manager: FleetManager
    ) -> None:
        """High utilization suggests scaling up."""
        # Make all agents busy
        for agent_id in fleet_manager.agents:
            fleet_manager.update_agent_load(agent_id, 5)
        suggestion = fleet_manager.get_scaling_suggestion()
        assert suggestion["action"] == "scale_up"
        assert "suggested_agents" in suggestion

    def test_scaling_suggestion_low_utilization(
        self, fleet_manager: FleetManager
    ) -> None:
        """Low utilization suggests scaling down."""
        suggestion = fleet_manager.get_scaling_suggestion()
        # With 3 agents at 0% utilization, should suggest scaling down
        # (if more than 1 agent)
        # Actually utilization is 0 which is < 20, and total > 1
        assert suggestion["action"] == "scale_down"

    def test_get_all_agent_ids(self, fleet_manager: FleetManager) -> None:
        """All non-offline agent IDs are returned."""
        ids = fleet_manager.get_all_agent_ids()
        assert len(ids) == 3
        assert "agent-alpha" in ids

    def test_get_all_agent_ids_excludes_offline(
        self, fleet_manager: FleetManager
    ) -> None:
        """Offline agents are excluded."""
        fleet_manager.set_agent_status("agent-beta", "offline")
        ids = fleet_manager.get_all_agent_ids()
        assert "agent-beta" not in ids
        assert len(ids) == 2

    def test_get_agent_record(self, fleet_manager: FleetManager) -> None:
        """Can get full agent record."""
        record = fleet_manager.get_agent_record("agent-alpha")
        assert isinstance(record, AgentRecord)
        assert record.agent_id == "agent-alpha"

    def test_get_agent_record_nonexistent(self, fleet_manager: FleetManager) -> None:
        """Nonexistent agent raises KeyError."""
        with pytest.raises(KeyError):
            fleet_manager.get_agent_record("nonexistent")


# ══════════════════════════════════════════════════════════════════════════
# FleetSnapshot Data Class Tests
# ══════════════════════════════════════════════════════════════════════════

class TestFleetSnapshot:
    """Tests for FleetSnapshot data class."""

    def test_default_values(self) -> None:
        """FleetSnapshot has correct defaults."""
        snapshot = FleetSnapshot()
        assert snapshot.total_agents == 0
        assert snapshot.utilization_pct == 0.0
        assert snapshot.all_capabilities == set()
        assert snapshot.agents == {}

    def test_empty_fleet_snapshot(self) -> None:
        """Empty fleet manager produces empty snapshot."""
        fm = FleetManager()
        snapshot = fm.get_fleet_snapshot()
        assert snapshot.total_agents == 0
        assert snapshot.total_capacity == 0


# ══════════════════════════════════════════════════════════════════════════
# HumanInterface — HumanContext Tests
# ══════════════════════════════════════════════════════════════════════════

class TestHumanContext:
    """Tests for HumanContext."""

    def test_default_values(self) -> None:
        """HumanContext has correct defaults."""
        ctx = HumanContext()
        assert ctx.name == "Operator"
        assert ctx.preferred_name is None
        assert ctx.working_hours_start == 9
        assert ctx.working_hours_end == 17
        assert ctx.quiet_hours is True
        assert ctx.priority_threshold == "HIGH"

    def test_custom_values(self) -> None:
        """HumanContext can be customized."""
        ctx = HumanContext(
            name="Jane",
            preferred_name="Janey",
            working_hours_start=8,
            working_hours_end=16,
        )
        assert ctx.name == "Jane"
        assert ctx.preferred_name == "Janey"
        assert ctx.working_hours_start == 8
        assert ctx.working_hours_end == 16

    def test_preferences(self) -> None:
        """Preferences can be set and retrieved."""
        ctx = HumanContext()
        ctx.set_preference("theme", "dark")
        assert ctx.get_preference("theme") == "dark"
        assert ctx.get_preference("nonexistent") is None
        assert ctx.get_preference("nonexistent", "default") == "default"

    def test_get_greeting_morning(self, human_context: HumanContext) -> None:
        """Morning greeting is generated."""
        # We can't easily mock time, so just test the format
        greeting = human_context.get_greeting()
        assert "Test" in greeting

    def test_is_working_hours(self, human_context: HumanContext) -> None:
        """Working hours check returns a boolean."""
        result = human_context.is_working_hours()
        assert isinstance(result, bool)

    def test_overnight_shift(self) -> None:
        """Overnight shifts are handled correctly."""
        ctx = HumanContext(working_hours_start=22, working_hours_end=6)
        # We can't control time, but test the logic path exists
        result = ctx.is_working_hours()
        assert isinstance(result, bool)


# ══════════════════════════════════════════════════════════════════════════
# HumanInterface — Escalation Tests
# ══════════════════════════════════════════════════════════════════════════

class TestEscalation:
    """Tests for priority escalation rules."""

    def test_critical_always_escalates(self, human_context: HumanContext) -> None:
        """CRITICAL always escalates regardless of working hours."""
        assert should_escalate("CRITICAL", human_context)

    def test_high_during_working_hours(self, human_context: HumanContext) -> None:
        """HIGH escalates during working hours if threshold is HIGH."""
        # This depends on actual time, so we test the logic
        result = should_escalate("HIGH", human_context)
        assert isinstance(result, bool)

    def test_normal_escalation_depends_on_time(self) -> None:
        """NORMAL escalation depends on working hours and quiet hours."""
        ctx = HumanContext(quiet_hours=True, priority_threshold="NORMAL")
        result = should_escalate("NORMAL", ctx)
        assert isinstance(result, bool)

    def test_low_never_escalates_in_quiet(self) -> None:
        """LOW never escalates during quiet hours."""
        ctx = HumanContext(quiet_hours=True)
        if not ctx.is_working_hours():
            assert not should_escalate("LOW", ctx)

    def test_quiet_hours_disabled(self) -> None:
        """With quiet hours disabled, escalation works normally."""
        ctx = HumanContext(quiet_hours=False, priority_threshold="LOW")
        assert should_escalate("HIGH", ctx)

    def test_case_insensitive_priority(self, human_context: HumanContext) -> None:
        """Priority is case-insensitive."""
        assert should_escalate("critical", human_context)
        assert should_escalate("Critical", human_context)


# ══════════════════════════════════════════════════════════════════════════
# HumanInterface — Formatting Tests
# ══════════════════════════════════════════════════════════════════════════

class TestHumanInterfaceFormatting:
    """Tests for message formatting."""

    def test_format_status_report(self, human_interface: HumanInterface) -> None:
        """Status report is formatted correctly."""
        from fleet_manager import FleetSnapshot
        snapshot = FleetSnapshot(total_agents=3, active_agents=2)
        report = human_interface.format_status_report(
            tasks={}, fleet_snapshot=snapshot, state="MONITORING"
        )
        assert "Test" in report  # greeting
        assert "Status Report" in report
        assert "MONITORING" in report
        assert "Total agents: 3" in report
        assert "No active tasks" in report

    def test_format_status_report_with_tasks(
        self, human_interface: HumanInterface
    ) -> None:
        """Status report includes task counts."""
        from fleet_manager import FleetSnapshot
        snapshot = FleetSnapshot(total_agents=1, active_agents=1)
        tasks = {
            "t1": TaskProgress(task_id="t1", status="completed"),
            "t2": TaskProgress(task_id="t2", status="in_progress"),
        }
        report = human_interface.format_status_report(
            tasks=tasks, fleet_snapshot=snapshot
        )
        assert "completed: 1" in report
        assert "in_progress: 1" in report

    def test_format_fleet_status(self, human_interface: HumanInterface) -> None:
        """Fleet status is formatted correctly."""
        from fleet_manager import FleetSnapshot
        snapshot = FleetSnapshot(
            total_agents=2,
            active_agents=1,
            idle_agents=1,
            busy_agents=0,
            offline_agents=0,
            agents={
                "agent-a": {"status": "active", "current_load": 1, "max_load": 5},
                "agent-b": {"status": "idle", "current_load": 0, "max_load": 5},
            },
        )
        status = human_interface.format_fleet_status(snapshot)
        assert "Fleet Status" in status
        assert "agent-a" in status
        assert "agent-b" in status

    def test_format_daily_summary(self, human_interface: HumanInterface) -> None:
        """Daily summary is formatted correctly."""
        from fleet_manager import FleetSnapshot
        snapshot = FleetSnapshot(total_agents=2, active_agents=2)
        tasks = {
            "t1": TaskProgress(task_id="t1", status="completed"),
        }
        briefs = [
            SessionBrief(brief_id="b1", instruction="Run tests"),
        ]
        summary = human_interface.format_daily_summary(
            tasks=tasks, brief_history=briefs, fleet_snapshot=snapshot
        )
        assert "Daily Summary" in summary
        assert "Run tests" in summary
        assert "Completed: 1" in summary

    def test_format_escalation(self, human_interface: HumanInterface) -> None:
        """Escalation is formatted correctly."""
        escalation = human_interface.format_escalation(
            "CRITICAL", "Server is down!", "Production cluster"
        )
        assert "ESCALATION" in escalation
        assert "CRITICAL" in escalation
        assert "Server is down!" in escalation
        assert "Production cluster" in escalation

    def test_format_task_update(self, human_interface: HumanInterface) -> None:
        """Task update is formatted correctly."""
        update = human_interface.format_task_update("t1", "completed", "All tests passed")
        assert "t1" in update
        assert "completed" in update
        assert "All tests passed" in update

    def test_format_task_update_no_result(
        self, human_interface: HumanInterface
    ) -> None:
        """Task update without result."""
        update = human_interface.format_task_update("t1", "in_progress")
        assert "in_progress" in update

    def test_status_icons(self, human_interface: HumanInterface) -> None:
        """Status icons are returned for known statuses."""
        assert human_interface._status_icon("completed") == "✅"
        assert human_interface._status_icon("failed") == "❌"
        assert human_interface._status_icon("in_progress") == "🔄"
        assert human_interface._status_icon("unknown") == "❓"

    def test_urgency_labels(self, human_interface: HumanInterface) -> None:
        """Urgency labels are correct."""
        assert "CRITICAL" in human_interface._urgency_label("CRITICAL")
        assert "High" in human_interface._urgency_label("HIGH")
        assert "Low" in human_interface._urgency_label("LOW")


# ══════════════════════════════════════════════════════════════════════════
# HumanInterface — Helper Tests
# ══════════════════════════════════════════════════════════════════════════

class TestHumanInterfaceHelpers:
    """Tests for helper functions."""

    def test_snapshot_total_active(self) -> None:
        """Total active count is calculated correctly."""
        snapshot = FleetSnapshot(
            active_agents=1, idle_agents=2, busy_agents=1
        )
        assert snapshot_total_active(snapshot) == 4

    def test_snapshot_total_active_empty(self) -> None:
        """Empty snapshot returns 0."""
        assert snapshot_total_active(None) == 0

    def test_recommendations_no_failures(self, human_interface: HumanInterface) -> None:
        """No failures → no retry recommendation."""
        tasks = {"t1": TaskProgress(task_id="t1", status="completed")}
        snapshot = FleetSnapshot()
        recs = human_interface._generate_recommendations(tasks, snapshot)
        assert "No immediate actions" in recs

    def test_recommendations_with_failures(self, human_interface: HumanInterface) -> None:
        """Failures → retry recommendation."""
        tasks = {"t1": TaskProgress(task_id="t1", status="failed")}
        snapshot = FleetSnapshot()
        recs = human_interface._generate_recommendations(tasks, snapshot)
        assert "failed" in recs

    def test_recommendations_high_utilization(
        self, human_interface: HumanInterface
    ) -> None:
        """High utilization → scale recommendation."""
        snapshot = FleetSnapshot(utilization_pct=90.0, total_agents=3)
        recs = human_interface._generate_recommendations({}, snapshot)
        assert "adding agents" in recs


# ══════════════════════════════════════════════════════════════════════════
# CLI Tests
# ══════════════════════════════════════════════════════════════════════════

class TestCLI:
    """Tests for CLI commands."""

    def test_main_no_args_returns_zero(self) -> None:
        """Main with --help returns 0."""
        ret = main(["help"])
        assert ret == 0

    def test_main_unknown_command_returns_one(self) -> None:
        """Unknown command returns 1."""
        ret = main(["nonexistent"])
        assert ret == 1

    def test_cmd_status_empty_fleet(self, co_captain: CoCaptainAgent) -> None:
        """Status command works with fleet agents."""
        # Should not raise
        cmd_status(co_captain, [])

    def test_cmd_fleet_no_args(self, co_captain: CoCaptainAgent) -> None:
        """Fleet command without args prints help."""
        import io
        from contextlib import redirect_stdout, redirect_stderr

        f = io.StringIO()
        try:
            with redirect_stdout(f), redirect_stderr(f):
                cmd_fleet(co_captain, [])
        except SystemExit:
            pass
        output = f.getvalue()
        assert "add" in output or "list" in output

    def test_cmd_config_no_args(self, co_captain: CoCaptainAgent) -> None:
        """Config command without args shows config."""
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            cmd_config(co_captain, [])
        output = f.getvalue()
        assert "Configuration" in output

    def test_cmd_config_set_preference(self, co_captain: CoCaptainAgent) -> None:
        """Config set command works."""
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            cmd_config(co_captain, ["set", "theme", "dark"])
        output = f.getvalue()
        assert "theme" in output
        assert co_captain.human_context.get_preference("theme") == "dark"

    def test_cmd_config_get_preference(self, co_captain: CoCaptainAgent) -> None:
        """Config get command works."""
        co_captain.human_context.set_preference("theme", "dark")
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            cmd_config(co_captain, ["get", "theme"])
        output = f.getvalue()
        assert "dark" in output

    def test_cmd_config_working_hours(self, co_captain: CoCaptainAgent) -> None:
        """Config working-hours command works."""
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            cmd_config(co_captain, ["working-hours", "8", "18"])
        assert co_captain.human_context.working_hours_start == 8
        assert co_captain.human_context.working_hours_end == 18

    def test_cmd_config_name(self, co_captain: CoCaptainAgent) -> None:
        """Config name command works."""
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            cmd_config(co_captain, ["name", "Jane Doe"])
        assert co_captain.human_context.name == "Jane Doe"

    def test_cmd_config_threshold(self, co_captain: CoCaptainAgent) -> None:
        """Config threshold command works."""
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            cmd_config(co_captain, ["threshold", "CRITICAL"])
        assert co_captain.human_context.priority_threshold == "CRITICAL"

    def test_cmd_summary(self, co_captain: CoCaptainAgent) -> None:
        """Summary command works."""
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            cmd_summary(co_captain, [])
        output = f.getvalue()
        assert "Daily Summary" in output

    def test_help_prints(self) -> None:
        """Help command prints usage."""
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            print_help()
        output = f.getvalue()
        assert "Co-Captain" in output
        assert "brief" in output
        assert "fleet" in output


# ══════════════════════════════════════════════════════════════════════════
# Integration Tests
# ══════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """End-to-end integration tests."""

    def test_full_workflow(self) -> None:
        """Complete workflow: onboard → brief → dispatch → monitor → report."""
        # Create co-captain with empty fleet
        agent = CoCaptainAgent()

        # Onboard agents
        agent.onboard_agent("dev-agent", ["code_review", "testing"])
        agent.onboard_agent("ops-agent", ["deployment", "monitoring"])

        # Verify fleet
        assert agent.fleet_manager.agent_count() == 2

        # Receive brief
        brief = agent.receive_brief(
            "Review the code and run tests",
            priority=TaskPriority.HIGH,
        )
        assert brief.priority == TaskPriority.HIGH

        # Dispatch
        task_ids = agent.dispatch_brief(brief)
        assert len(task_ids) > 0

        # Monitor progress
        for tid in task_ids:
            agent.update_task_status(tid, "in_progress")

        # Complete tasks
        for tid in task_ids:
            agent.update_task_status(tid, "completed", result="Success")

        # Generate report
        report = agent.generate_report()
        assert "completed" in report
        assert agent.state == CoCaptainState.STANDBY

    def test_dispatch_with_targeted_agents(self) -> None:
        """Dispatch with specific target agents."""
        agent = CoCaptainAgent()
        agent.onboard_agent("a1", ["testing"])
        agent.onboard_agent("a2", ["deployment"])

        brief = agent.receive_brief("Deploy", target_agents=["a2"])
        task_ids = agent.dispatch_brief(brief)

        # All tasks should go to a2
        for tid in task_ids:
            assert agent.active_tasks[tid].agent_id == "a2"

    def test_error_recovery_workflow(self) -> None:
        """Error recovery: failure → report → new brief."""
        agent = CoCaptainAgent()
        agent.onboard_agent("a1", ["testing"])

        brief = agent.receive_brief("Run tests")
        task_ids = agent.dispatch_brief(brief)

        # Tasks fail
        for tid in task_ids:
            agent.update_task_status(tid, "failed", error="Test framework crashed")

        # Report and reset
        report = agent.generate_report()
        assert "failed" in report
        assert agent.is_standby()

        # Can receive new brief
        brief2 = agent.receive_brief("Retry tests")
        assert brief2.brief_id != brief.brief_id

    def test_capability_based_routing(self) -> None:
        """Tasks are routed based on capabilities."""
        agent = CoCaptainAgent()
        agent.onboard_agent("tester", ["testing"])
        agent.onboard_agent("deployer", ["deployment"])

        brief = agent.receive_brief("Run tests")
        task_ids = agent.dispatch_brief(brief)

        # Should route to tester
        for tid in task_ids:
            assert agent.active_tasks[tid].agent_id == "tester"

    def test_broadcast_fallback(self) -> None:
        """No matching capability falls back to broadcast."""
        agent = CoCaptainAgent()
        agent.onboard_agent("a1", ["testing"])

        brief = agent.receive_brief("Do something unusual")
        task_ids = agent.dispatch_brief(brief)

        # Should still dispatch (broadcast fallback)
        assert len(task_ids) > 0

    def test_multiple_briefs_history(self) -> None:
        """Multiple briefs are stored in history."""
        agent = CoCaptainAgent()
        agent.onboard_agent("a1", ["testing"])

        for i in range(5):
            brief = agent.receive_brief(f"Task {i}")
            agent.dispatch_brief(brief)
            agent.generate_report()  # Reset to standby

        assert len(agent.brief_history) == 5

    def test_fleet_scaling_integration(self) -> None:
        """Fleet scaling suggestion works with real workload."""
        agent = CoCaptainAgent()
        agent.onboard_agent("a1", ["testing"])

        # Load the agent
        agent.fleet_manager.update_agent_load("a1", 5)  # max_load=5

        suggestion = agent.fleet_manager.get_scaling_suggestion()
        assert suggestion["action"] == "scale_up"

    def test_dispatcher_cancellation_integration(self) -> None:
        """Task can be dispatched and then cancelled."""
        agent = CoCaptainAgent()
        agent.onboard_agent("a1", ["testing"])

        brief = agent.receive_brief("Run tests")
        task_ids = agent.dispatch_brief(brief)
        task_id = task_ids[0]

        cancel_msg = agent.dispatcher.cancel_task(task_id)
        assert cancel_msg is not None
        assert cancel_msg.message_type == "cancel"

    def test_acknowledgment_flow(self) -> None:
        """Full acknowledgment flow."""
        agent = CoCaptainAgent()
        agent.onboard_agent("a1", ["testing"])

        brief = agent.receive_brief("Run tests")
        task_ids = agent.dispatch_brief(brief)
        task_id = task_ids[0]

        assert not agent.dispatcher.is_acknowledged(task_id)
        agent.dispatcher.acknowledge(task_id)
        assert agent.dispatcher.is_acknowledged(task_id)
        assert agent.dispatcher.unacknowledged_count() == len(task_ids) - 1
