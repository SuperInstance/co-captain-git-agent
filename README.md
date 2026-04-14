# Co-Captain Git-Agent

> **The human's liaison to the SuperInstance fleet.**

The Co-Captain is NOT another worker agent. It's the human operator's representative inside the SuperInstance. It acts as the single point of contact between a human operator and the entire fleet of git-agents.

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

## Responsibilities

1. **Receive Instructions** — via CLI, chat, or API
2. **Translate** human intent → fleet protocol messages
3. **Dispatch** work to appropriate git-agents
4. **Monitor** progress and report back
5. **Manage Fleet** membership (onboard/offboard agents)
6. **Hold Human Context** — preferences, priorities, working hours
7. **Gatekeeper** — nothing reaches the fleet without co-captain approval

## State Machine

```
STANDBY ──▶ BRIEFED ──▶ DISPATCHING ──▶ MONITORING ──▶ REPORTING
   ▲                                                       │
   └───────────────────────────────────────────────────────┘
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

## Modules

| Module | Purpose |
|--------|---------|
| `co_captain.py` | Core agent with state machine |
| `dispatcher.py` | Task dispatch and routing |
| `fleet_manager.py` | Fleet membership and capabilities |
| `human_interface.py` | Human communication formatting |
| `cli.py` | Command-line interface |

## Running Tests

```bash
python -m pytest tests/ -v
```

## License

MIT
