"""CLI — Command Line Interface for the Co-Captain Git-Agent.

Subcommands:
    brief    — Receive and process human instructions
    status   — Fleet status dashboard
    dispatch — Manually dispatch a task
    fleet    — Manage fleet membership
    summary  — Generate summary report
    config   — Manage human preferences
"""

from __future__ import annotations

import sys
from typing import Any

from co_captain import CoCaptainAgent, CoCaptainStateError, FleetEmptyError
from dispatcher import TaskPriority
from fleet_manager import FleetManager
from human_interface import HumanContext, HumanInterface


def cmd_brief(agent: CoCaptainAgent, args: list[str]) -> None:
    """Handle the 'brief' subcommand."""
    if not args:
        print("Usage: co-captain brief <instruction> [--priority HIGH] [--agents agent1,agent2]")
        print("")
        print("Receive a human instruction and prepare it for dispatch.")
        print("")
        print("Options:")
        print("  --priority <LEVEL>  Priority: LOW, NORMAL, HIGH, CRITICAL (default: NORMAL)")
        print("  --agents <LIST>     Comma-separated list of target agent IDs")
        sys.exit(1)

    # Parse options
    priority = TaskPriority.NORMAL
    target_agents: list[str] | None = None
    instruction_parts: list[str] = []

    i = 0
    while i < len(args):
        if args[i] == "--priority" and i + 1 < len(args):
            try:
                priority = TaskPriority[args[i + 1].upper()]
            except KeyError:
                print(f"Error: Invalid priority '{args[i + 1]}'. Use LOW, NORMAL, HIGH, or CRITICAL.")
                sys.exit(1)
            i += 2
        elif args[i] == "--agents" and i + 1 < len(args):
            target_agents = [a.strip() for a in args[i + 1].split(",")]
            i += 2
        else:
            instruction_parts.append(args[i])
            i += 1

    instruction = " ".join(instruction_parts)

    try:
        brief = agent.receive_brief(
            instruction=instruction,
            priority=priority,
            target_agents=target_agents,
        )
        print(f"✅ Brief received (ID: {brief.brief_id})")
        print(f"   Priority: {brief.priority.name}")
        print(f"   Instruction: {brief.instruction}")
        if brief.target_agents:
            print(f"   Target agents: {', '.join(brief.target_agents)}")
        print(f"   State: {agent.state.name}")
    except CoCaptainStateError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_status(agent: CoCaptainAgent, args: list[str]) -> None:
    """Handle the 'status' subcommand."""
    _ = args
    status = agent.get_fleet_status()
    print(status)
    print("")
    print(f"Co-Captain State: {agent.state.name}")
    print(f"Active Tasks: {len(agent.active_tasks)}")

    if agent.active_tasks:
        summary = agent.get_progress_summary()
        print("Task Summary:")
        for status_name, count in summary.items():
            print(f"  {status_name}: {count}")


def cmd_dispatch(agent: CoCaptainAgent, args: list[str]) -> None:
    """Handle the 'dispatch' subcommand."""
    if not args:
        print("Usage: co-captain dispatch <instruction>")
        sys.exit(1)

    instruction = " ".join(args)

    # Quick brief + dispatch
    try:
        brief = agent.receive_brief(instruction=instruction)
        task_ids = agent.dispatch_brief(brief)
        print(f"✅ Dispatched {len(task_ids)} task(s):")
        for tid in task_ids:
            print(f"   → {tid}")
    except CoCaptainStateError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except FleetEmptyError as e:
        print(f"❌ {e}")
        print("   Use 'co-captain fleet add <agent_id> [capabilities]' to add agents.")
        sys.exit(1)


def cmd_fleet(agent: CoCaptainAgent, args: list[str]) -> None:
    """Handle the 'fleet' subcommand."""
    if not args:
        print("Usage: co-captain fleet <add|remove|list|health|scaling>")
        print("")
        print("Subcommands:")
        print("  add <agent_id> [cap1,cap2,...]  Add an agent to the fleet")
        print("  remove <agent_id>                Remove an agent")
        print("  list                            List all agents")
        print("  health                          Check agent health")
        print("  scaling                         Get scaling suggestions")
        sys.exit(1)

    subcmd = args[0]
    rest = args[1:]

    if subcmd == "add":
        if not rest:
            print("Usage: co-captain fleet add <agent_id> [cap1,cap2,...]")
            sys.exit(1)
        agent_id = rest[0]
        capabilities = [c.strip() for c in rest[1].split(",")] if len(rest) > 1 else []
        try:
            agent.onboard_agent(agent_id, capabilities)
            print(f"✅ Agent '{agent_id}' added to fleet.")
            if capabilities:
                print(f"   Capabilities: {', '.join(capabilities)}")
        except ValueError as e:
            print(f"❌ {e}")
            sys.exit(1)

    elif subcmd == "remove":
        if not rest:
            print("Usage: co-captain fleet remove <agent_id>")
            sys.exit(1)
        try:
            agent.offboard_agent(rest[0])
            print(f"✅ Agent '{rest[0]}' removed from fleet.")
        except KeyError as e:
            print(f"❌ {e}")
            sys.exit(1)

    elif subcmd == "list":
        snapshot = agent.fleet_manager.get_fleet_snapshot()
        status = agent.get_fleet_status()
        print(status)
        print("")
        print(f"All capabilities: {', '.join(sorted(snapshot.all_capabilities)) or 'none'}")

    elif subcmd == "health":
        unhealthy = agent.fleet_manager.check_health()
        if unhealthy:
            print(f"⚠️  {len(unhealthy)} unhealthy agent(s): {', '.join(unhealthy)}")
        else:
            print("✅ All agents healthy.")

    elif subcmd == "scaling":
        suggestion = agent.fleet_manager.get_scaling_suggestion()
        print(f"Action: {suggestion['action']}")
        print(f"Utilization: {suggestion['current_utilization']:.1f}%")
        print(f"Reason: {suggestion['reason']}")
        if "suggested_agents" in suggestion:
            print(f"Suggested agents to add: {suggestion['suggested_agents']}")
        if "suggested_removal" in suggestion:
            print(f"Suggested agents to remove: {suggestion['suggested_removal']}")

    else:
        print(f"Unknown fleet subcommand: {subcmd}")
        sys.exit(1)


def cmd_summary(agent: CoCaptainAgent, args: list[str]) -> None:
    """Handle the 'summary' subcommand."""
    _ = args
    summary = agent.generate_daily_summary()
    print(summary)


def cmd_config(agent: CoCaptainAgent, args: list[str]) -> None:
    """Handle the 'config' subcommand."""
    if not args:
        ctx = agent.human_context
        print("Current Configuration:")
        print(f"  Name: {ctx.name}")
        print(f"  Preferred Name: {ctx.preferred_name or '(none)'}")
        print(f"  Working Hours: {ctx.working_hours_start:02d}:00 - {ctx.working_hours_end:02d}:00")
        print(f"  Timezone: {ctx.timezone}")
        print(f"  Communication Style: {ctx.communication_style}")
        print(f"  Priority Threshold: {ctx.priority_threshold}")
        print(f"  Quiet Hours: {'enabled' if ctx.quiet_hours else 'disabled'}")
        print(f"  Preferences: {ctx.preferences or '(none)'}")
        print("")
        print("Usage: co-captain config <set|get|working-hours>")
        print("  set <key> <value>          Set a preference")
        print("  get <key>                  Get a preference")
        print("  working-hours <start> <end>  Set working hours (0-23)")
        print("  name <name>                Set operator name")
        print("  threshold <LEVEL>          Set priority threshold")
        return

    subcmd = args[0]
    rest = args[1:]

    if subcmd == "set":
        if len(rest) < 2:
            print("Usage: co-captain config set <key> <value>")
            sys.exit(1)
        agent.human_context.set_preference(rest[0], rest[1])
        print(f"✅ Set {rest[0]} = {rest[1]}")

    elif subcmd == "get":
        if not rest:
            print("Usage: co-captain config get <key>")
            sys.exit(1)
        value = agent.human_context.get_preference(rest[0])
        if value is not None:
            print(f"{rest[0]} = {value}")
        else:
            print(f"{rest[0]} is not set.")

    elif subcmd == "working-hours":
        if len(rest) < 2:
            print("Usage: co-captain config working-hours <start> <end>")
            sys.exit(1)
        try:
            start = int(rest[0])
            end = int(rest[1])
            if not (0 <= start <= 23 and 0 <= end <= 23):
                raise ValueError
        except ValueError:
            print("Error: Hours must be integers between 0 and 23.")
            sys.exit(1)
        agent.human_context.working_hours_start = start
        agent.human_context.working_hours_end = end
        print(f"✅ Working hours set to {start:02d}:00 - {end:02d}:00")

    elif subcmd == "name":
        if not rest:
            print("Usage: co-captain config name <name>")
            sys.exit(1)
        agent.human_context.name = " ".join(rest)
        print(f"✅ Operator name set to: {agent.human_context.name}")

    elif subcmd == "threshold":
        if not rest:
            print("Usage: co-captain config threshold <LOW|NORMAL|HIGH|CRITICAL>")
            sys.exit(1)
        level = rest[0].upper()
        if level not in ("LOW", "NORMAL", "HIGH", "CRITICAL"):
            print("Error: Must be LOW, NORMAL, HIGH, or CRITICAL.")
            sys.exit(1)
        agent.human_context.priority_threshold = level
        print(f"✅ Priority threshold set to {level}")

    else:
        print(f"Unknown config subcommand: {subcmd}")
        sys.exit(1)


def print_help() -> None:
    """Print the help message."""
    print("Co-Captain Git-Agent — Human liaison to the SuperInstance fleet")
    print("")
    print("Usage: co-captain <command> [arguments]")
    print("")
    print("Commands:")
    print("  brief <instruction>    Receive and process a human instruction")
    print("  status                 Show fleet status dashboard")
    print("  dispatch <instruction> Brief and dispatch in one step")
    print("  fleet <subcommand>     Manage fleet membership")
    print("  summary                Generate daily summary report")
    print("  config <subcommand>    Manage human preferences")
    print("  help                   Show this help message")
    print("")
    print("The co-captain is the single point of contact between you")
    print("and the SuperInstance fleet of git-agents.")


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("help", "--help", "-h"):
        print_help()
        return 0

    # Initialize the co-captain
    fleet_manager = FleetManager()
    agent = CoCaptainAgent(fleet_manager=fleet_manager)

    command = argv[0]
    args = argv[1:]

    try:
        if command == "brief":
            cmd_brief(agent, args)
        elif command == "status":
            cmd_status(agent, args)
        elif command == "dispatch":
            cmd_dispatch(agent, args)
        elif command == "fleet":
            cmd_fleet(agent, args)
        elif command == "summary":
            cmd_summary(agent, args)
        elif command == "config":
            cmd_config(agent, args)
        else:
            print(f"Unknown command: {command}")
            print("Run 'co-captain help' for usage information.")
            return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
