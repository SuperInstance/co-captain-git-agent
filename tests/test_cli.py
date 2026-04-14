"""Tests for the CLI module (cli.py) — additional edge cases."""

from __future__ import annotations

import sys
import os
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
from co_captain import CoCaptainAgent
from fleet_manager import FleetManager


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def fleet() -> FleetManager:
    fm = FleetManager()
    fm.onboard_agent("agent-1", ["code_review"])
    fm.onboard_agent("agent-2", ["testing"])
    return fm


@pytest.fixture
def agent(fleet: FleetManager) -> CoCaptainAgent:
    return CoCaptainAgent(fleet_manager=fleet)


# ══════════════════════════════════════════════════════════════════════════
# main() — Entry Point
# ══════════════════════════════════════════════════════════════════════════

class TestMain:
    """Tests for the main CLI entry point."""

    def test_help_flag(self) -> int:
        rc = main(["--help"])
        assert rc == 0

    def test_h_flag(self) -> int:
        rc = main(["-h"])
        assert rc == 0

    def test_help_command(self) -> int:
        rc = main(["help"])
        assert rc == 0

    def test_no_args(self) -> int:
        rc = main([])
        assert rc == 0

    def test_unknown_command(self) -> int:
        rc = main(["nonexistent"])
        assert rc == 1

    def test_argv_defaults_to_sys_argv(self) -> None:
        """main() uses sys.argv when argv is None."""
        with patch.object(sys, "argv", ["co-captain", "help"]):
            rc = main(None)
            assert rc == 0


# ══════════════════════════════════════════════════════════════════════════
# cmd_brief — Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestCmdBrief:
    """Tests for cmd_brief."""

    def test_brief_no_args_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_brief(agent, [])

    def test_brief_with_priority_flag(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_brief(agent, ["Run tests", "--priority", "HIGH"])
        output = capsys.readouterr().out
        assert "HIGH" in output

    def test_brief_with_agents_flag(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_brief(agent, ["Review code", "--agents", "agent-1,agent-2"])
        output = capsys.readouterr().out
        assert "agent-1" in output

    def test_brief_invalid_priority_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_brief(agent, ["Test", "--priority", "INVALID"])

    def test_brief_instruction_with_flags(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_brief(agent, ["Deploy", "to", "production", "--priority", "CRITICAL"])
        output = capsys.readouterr().out
        assert "CRITICAL" in output
        assert "Brief received" in output

    def test_brief_state_error(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_brief(agent, ["First brief"])
        # Already in BRIEFED state
        with pytest.raises(SystemExit):
            cmd_brief(agent, ["Second brief"])


# ══════════════════════════════════════════════════════════════════════════
# cmd_status — Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestCmdStatus:
    """Tests for cmd_status."""

    def test_status_prints_fleet_info(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_status(agent, [])
        output = capsys.readouterr().out
        assert "Fleet Status" in output
        assert "Co-Captain State" in output

    def test_status_ignores_args(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_status(agent, ["ignored", "args"])
        output = capsys.readouterr().out
        assert "Fleet Status" in output

    def test_status_shows_active_tasks(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        brief = agent.receive_brief("Test")
        agent.dispatch_brief(brief)
        agent.reset_to_standby()
        cmd_status(agent, [])
        output = capsys.readouterr().out
        assert "Active Tasks:" in output


# ══════════════════════════════════════════════════════════════════════════
# cmd_dispatch — Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestCmdDispatch:
    """Tests for cmd_dispatch."""

    def test_dispatch_no_args_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_dispatch(agent, [])

    def test_dispatch_success(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_dispatch(agent, ["Run tests"])
        output = capsys.readouterr().out
        assert "Dispatched" in output

    def test_dispatch_empty_fleet_exits(self) -> None:
        empty_agent = CoCaptainAgent()
        with pytest.raises(SystemExit):
            cmd_dispatch(empty_agent, ["Test"])


# ══════════════════════════════════════════════════════════════════════════
# cmd_fleet — Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestCmdFleet:
    """Tests for cmd_fleet."""

    def test_fleet_no_args_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_fleet(agent, [])

    def test_fleet_add_no_id_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_fleet(agent, ["add"])

    def test_fleet_add_success(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_fleet(agent, ["add", "agent-3", "testing,review"])
        output = capsys.readouterr().out
        assert "agent-3" in output
        assert "testing" in output

    def test_fleet_add_duplicate_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_fleet(agent, ["add", "agent-1", "testing"])

    def test_fleet_remove_no_id_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_fleet(agent, ["remove"])

    def test_fleet_remove_success(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_fleet(agent, ["remove", "agent-1"])
        output = capsys.readouterr().out
        assert "agent-1" in output

    def test_fleet_remove_nonexistent_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_fleet(agent, ["remove", "nonexistent"])

    def test_fleet_list(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_fleet(agent, ["list"])
        output = capsys.readouterr().out
        assert "Fleet Status" in output
        assert "capabilities" in output

    def test_fleet_health_all_healthy(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_fleet(agent, ["health"])
        output = capsys.readouterr().out
        assert "All agents healthy" in output

    def test_fleet_scaling(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_fleet(agent, ["scaling"])
        output = capsys.readouterr().out
        assert "Action:" in output
        assert "Utilization:" in output

    def test_fleet_unknown_subcommand_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_fleet(agent, ["unknown"])


# ══════════════════════════════════════════════════════════════════════════
# cmd_summary — Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestCmdSummary:
    """Tests for cmd_summary."""

    def test_summary_empty(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_summary(agent, [])
        output = capsys.readouterr().out
        assert "Daily Summary" in output

    def test_summary_with_briefs(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        agent.receive_brief("Test task")
        agent.reset_to_standby()
        cmd_summary(agent, [])
        output = capsys.readouterr().out
        assert "Test task" in output


# ══════════════════════════════════════════════════════════════════════════
# cmd_config — Edge Cases
# ══════════════════════════════════════════════════════════════════════════

class TestCmdConfig:
    """Tests for cmd_config."""

    def test_config_no_args_shows_current(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_config(agent, [])
        output = capsys.readouterr().out
        assert "Current Configuration" in output

    def test_config_set_no_value_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_config(agent, ["set", "key"])

    def test_config_set_success(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_config(agent, ["set", "editor", "vim"])
        output = capsys.readouterr().out
        assert "editor" in output
        assert "vim" in output

    def test_config_get_no_key_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_config(agent, ["get"])

    def test_config_get_existing(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        agent.human_context.set_preference("editor", "vim")
        cmd_config(agent, ["get", "editor"])
        output = capsys.readouterr().out
        assert "vim" in output

    def test_config_get_missing(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_config(agent, ["get", "nonexistent"])
        output = capsys.readouterr().out
        assert "not set" in output

    def test_config_working_hours_invalid_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_config(agent, ["working-hours", "25", "17"])

    def test_config_working_hours_success(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_config(agent, ["working-hours", "8", "18"])
        output = capsys.readouterr().out
        assert "08:00" in output
        assert "18:00" in output

    def test_config_name_no_value_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_config(agent, ["name"])

    def test_config_name_success(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_config(agent, ["name", "Jane", "Doe"])
        output = capsys.readouterr().out
        assert "Jane Doe" in output

    def test_config_threshold_invalid_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_config(agent, ["threshold", "INVALID"])

    def test_config_threshold_success(self, agent: CoCaptainAgent, capsys: pytest.CaptureFixture) -> None:
        cmd_config(agent, ["threshold", "CRITICAL"])
        output = capsys.readouterr().out
        assert "CRITICAL" in output

    def test_config_threshold_all_levels(self, agent: CoCaptainAgent) -> None:
        for level in ["LOW", "NORMAL", "HIGH", "CRITICAL"]:
            cmd_config(agent, ["threshold", level])
            assert agent.human_context.priority_threshold == level

    def test_config_unknown_subcommand_exits(self, agent: CoCaptainAgent) -> None:
        with pytest.raises(SystemExit):
            cmd_config(agent, ["unknown"])


# ══════════════════════════════════════════════════════════════════════════
# print_help
# ══════════════════════════════════════════════════════════════════════════

class TestPrintHelp:
    """Tests for print_help."""

    def test_help_output(self, capsys: pytest.CaptureFixture) -> None:
        print_help()
        output = capsys.readouterr().out
        assert "Co-Captain" in output
        assert "brief" in output
        assert "status" in output
        assert "dispatch" in output
        assert "fleet" in output
        assert "summary" in output
        assert "config" in output

    def test_help_returns_none(self) -> None:
        assert print_help() is None
