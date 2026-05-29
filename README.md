# Co-Captain Git-Agent

> The human operator's liaison to the SuperInstance fleet — receives instructions, translates intent to fleet protocol, dispatches work, monitors progress, and gates everything through human approval.

## What This Gives You

- **Single point of contact** — One agent represents the human to the entire fleet
- **Fleet dispatch** — Route tasks to appropriate git-agents based on capabilities
- **State machine** — STANDBY → BRIEFED → DISPATCHING → MONITORING → REPORTING cycle
- **Fleet management** — Onboard/offboard agents, assign capabilities
- **Human context** — Preferences, priorities, working hours, escalation thresholds
- **Gatekeeper** — Nothing reaches the fleet without co-captain approval

## Architecture

```
┌──────────┐     ┌─────────────────┐     ┌──────────────────┐
│          │     │   Co-Captain    │     │  Fleet Protocol  │
│  Human   │────▶│  Git-Agent      │────▶│  Messages        │────┐
│ Operator │     │                 │     │                  │    │
│          │◀────│                 │◀────│                  │◀───┘
└──────────┘     └─────────────────┘     └──────────────────┘
     ▲                    │                        │
     │                    ▼                        ▼
     │           ┌──────────────────────────────────────┐
     │           │           SuperInstance Fleet        │
     │           │  ┌──────────┐ ┌──────────┐          │
     │           │  │ git-agent│ │ git-agent│  ...     │
     │           │  │   #1     │ │   #2     │          │
     │           │  └──────────┘ └──────────┘          │
     │           └──────────────────────────────────────┘
     │
     │  Status reports, escalations, summaries
     └──────────────────────────────────────────────────
```

## Quick Start

```bash
pip install -e .

# Add agents to your fleet
co-captain fleet add agent-dev code_review,testing
co-captain fleet add agent-ops deployment,monitoring

# Check fleet status
co-captain status

# Dispatch a task
co-captain dispatch "Run tests on the main branch"

# Or brief first, then dispatch
co-captain brief "Refactor the auth module" --priority HIGH --agents agent-dev

# Get a summary
co-captain summary

# Configure preferences
co-captain config name "Jane Doe"
co-captain config working-hours 9 17
co-captain config threshold CRITICAL
```

## API Reference

### CLI Commands

| Command | Description |
|---------|-------------|
| `co-captain status` | Current fleet status |
| `co-captain fleet add <agent> <caps>` | Register an agent with capabilities |
| `co-captain fleet remove <agent>` | Remove an agent |
| `co-captain brief <description>` | Create a briefing |
| `co-captain dispatch <task>` | Dispatch task to fleet |
| `co-captain summary` | Activity summary |
| `co-captain config <key> <value>` | Set preferences |

### Modules

| Module | Purpose |
|--------|---------|
| `co_captain.py` | Core agent with state machine |
| `dispatcher.py` | Task dispatch and routing |
| `fleet_manager.py` | Fleet membership management |
| `human_interface.py` | Human input/output handling |

## How It Fits

- **[fleet-cicd-agent](https://github.com/SuperInstance/fleet-cicd-agent)** — CI/CD tasks dispatched through co-captain
- **[cocapn-health-rs](https://github.com/SuperInstance/cocapn-health-rs)** — Health status fed back to co-captain for escalation decisions
- **[clark-agent](https://github.com/SuperInstance/clark-agent)** — The agent loop framework co-captain is built on
- **[commit-predictor](https://github.com/SuperInstance/commit-predictor)** — Predictions inform dispatch timing
- **[ccc-os](https://github.com/SuperInstance/ccc-os)** — Fleet monitoring data flows through co-captain

## Testing

398 tests covering state machine transitions, fleet management, dispatch routing, human interface, and CLI commands.

```bash
pip install -e ".[dev]"
pytest
```

## Installation

```bash
git clone https://github.com/SuperInstance/co-captain-git-agent.git
cd co-captain-git-agent
pip install -e .
```

Requires Python 3.11+.

## License

MIT

Part of the [SuperInstance OpenConstruct](https://github.com/SuperInstance) ecosystem.
